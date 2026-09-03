import unittest

from app.domain.sales.order_totals import calcular_totales_visuales_orden


class SalesOrderTotalsTest(unittest.TestCase):
    def test_normal_items_without_delivery_or_discount(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 10.0), ("Producto B", 5.25)],
            0,
            100,
            0,
        )

        self.assertEqual(totals["total_usd"], 15.25)
        self.assertEqual(totals["total_bs"], 1525.0)
        self.assertEqual(totals["total_cliente_usd"], 15.25)
        self.assertEqual(totals["total_cliente_bs"], 1525.0)
        self.assertEqual(totals["delivery_legacy_usd"], 0.0)
        self.assertFalse(totals["tiene_delivery_legacy"])
        self.assertEqual(totals["total_bs_final"], 1525.0)
        self.assertEqual(totals["total_delivery_bs"], 0.0)
        self.assertEqual(totals["total_orden_bs"], 1525.0)
        self.assertEqual(totals["total_orden_usd"], 15.25)

    def test_legacy_delivery_item_is_split_from_restaurant_total(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0), ("Delivery 3", 3.0)],
            0,
            100,
            0,
        )

        self.assertEqual(totals["total_usd"], 20.0)
        self.assertEqual(totals["delivery_legacy_usd"], 3.0)
        self.assertTrue(totals["tiene_delivery_legacy"])
        self.assertEqual(totals["total_cliente_usd"], 23.0)
        self.assertEqual(totals["total_delivery_bs"], 300.0)
        self.assertEqual(totals["total_orden_bs"], 2300.0)

    def test_explicit_delivery_is_added_to_customer_total(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            2.5,
            100,
            0,
        )

        self.assertEqual(totals["total_usd"], 20.0)
        self.assertEqual(totals["delivery_legacy_usd"], 0.0)
        self.assertEqual(totals["total_cliente_usd"], 22.5)
        self.assertEqual(totals["total_delivery_bs"], 250.0)
        self.assertEqual(totals["total_orden_bs"], 2250.0)
        self.assertEqual(totals["total_orden_usd"], 22.5)

    def test_legacy_and_explicit_delivery_are_both_in_visual_total(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0), ("Delivery 3", 3.0)],
            2.5,
            100,
            0,
        )

        self.assertEqual(totals["total_usd"], 20.0)
        self.assertEqual(totals["delivery_legacy_usd"], 3.0)
        self.assertEqual(totals["total_cliente_usd"], 25.5)
        self.assertEqual(totals["total_delivery_bs"], 550.0)
        self.assertEqual(totals["total_orden_bs"], 2550.0)

    def test_discount_in_bs_reduces_restaurant_before_delivery(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            3.0,
            100,
            500,
        )

        self.assertEqual(totals["total_bs"], 2000.0)
        self.assertEqual(totals["total_bs_final"], 1500.0)
        self.assertEqual(totals["total_delivery_bs"], 300.0)
        self.assertEqual(totals["total_orden_bs"], 1800.0)
        self.assertEqual(totals["total_orden_usd"], 18.0)

    def test_discount_larger_than_subtotal_leaves_restaurant_at_zero(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 2.0)],
            3.0,
            100,
            500,
        )

        self.assertEqual(totals["total_bs"], 200.0)
        self.assertEqual(totals["total_bs_final"], 0)
        self.assertEqual(totals["total_delivery_bs"], 300.0)
        self.assertEqual(totals["total_orden_bs"], 300.0)
        self.assertEqual(totals["total_orden_usd"], 3.0)

    def test_zero_rate_uses_customer_total_for_order_total_usd(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            3.0,
            0,
            0,
        )

        self.assertEqual(totals["total_cliente_usd"], 23.0)
        self.assertEqual(totals["total_orden_bs"], 0.0)
        self.assertEqual(totals["total_orden_usd"], 23.0)

    def test_item_tuple_category_at_index_four_marks_legacy_delivery(self):
        totals = calcular_totales_visuales_orden(
            [
                ("Producto A", 20.0, 1, "", None),
                ("Delivery Especial", 4.0, 2, "", "Delivery"),
            ],
            0,
            100,
            0,
        )

        self.assertEqual(totals["total_usd"], 20.0)
        self.assertEqual(totals["delivery_legacy_usd"], 4.0)
        self.assertEqual(totals["total_cliente_usd"], 24.0)

    def test_none_delivery_is_treated_as_zero(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            None,
            100,
            0,
        )

        self.assertEqual(totals["total_cliente_usd"], 20.0)
        self.assertEqual(totals["total_delivery_bs"], 0.0)

    def test_numeric_string_delivery_is_supported(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            "2.50",
            100,
            0,
        )

        self.assertEqual(totals["total_cliente_usd"], 22.5)
        self.assertEqual(totals["total_delivery_bs"], 250.0)

    def test_customer_total_and_delivery_bs_use_unrounded_delivery_value(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            "1.235",
            100,
            0,
        )

        self.assertEqual(totals["total_cliente_usd"], 21.23)
        self.assertEqual(totals["total_delivery_bs"], 123.5)
        self.assertEqual(totals["total_orden_bs"], 2123.5)
        self.assertEqual(totals["total_orden_usd"], 21.23)

    def test_zero_rate_fallback_uses_historical_unrounded_delivery_total(self):
        totals = calcular_totales_visuales_orden(
            [("Producto A", 20.0)],
            "1.235",
            0,
            0,
        )

        self.assertEqual(totals["total_cliente_usd"], 21.23)
        self.assertEqual(totals["total_orden_usd"], 21.23)


if __name__ == "__main__":
    unittest.main()
