import unittest

from app.application.cxc.abonos import distribuir_pago_automatico


class DistribuirPagoAutomaticoTest(unittest.TestCase):
    def test_example_from_mission_301_305_309(self):
        cuentas = [(301, 8.0), (305, 12.0), (309, 20.0)]
        distribucion, sobrante = distribuir_pago_automatico(cuentas, 25.0)

        self.assertEqual(distribucion, [(301, 8.0), (305, 12.0), (309, 5.0)])
        self.assertEqual(sobrante, 0.0)

    def test_payment_exactly_covers_all_debts_leaves_no_remainder(self):
        cuentas = [(1, 10.0), (2, 10.0)]
        distribucion, sobrante = distribuir_pago_automatico(cuentas, 20.0)
        self.assertEqual(distribucion, [(1, 10.0), (2, 10.0)])
        self.assertEqual(sobrante, 0.0)

    def test_payment_exceeds_total_debt_leaves_remainder(self):
        cuentas = [(1, 5.0)]
        distribucion, sobrante = distribuir_pago_automatico(cuentas, 20.0)
        self.assertEqual(distribucion, [(1, 5.0)])
        self.assertEqual(sobrante, 15.0)

    def test_empty_accounts_returns_empty_distribution_and_full_remainder(self):
        distribucion, sobrante = distribuir_pago_automatico([], 25.0)
        self.assertEqual(distribucion, [])
        self.assertEqual(sobrante, 25.0)

    def test_zero_payment_returns_empty_distribution(self):
        distribucion, sobrante = distribuir_pago_automatico([(1, 10.0)], 0.0)
        self.assertEqual(distribucion, [])
        self.assertEqual(sobrante, 0.0)

    def test_never_assigns_more_than_each_accounts_balance(self):
        cuentas = [(1, 3.0), (2, 3.0), (3, 3.0)]
        distribucion, _sobrante = distribuir_pago_automatico(cuentas, 100.0)
        for _cuenta_id, monto in distribucion:
            self.assertLessEqual(monto, 3.0)

    def test_respects_order_of_input_list(self):
        """El orden lo decide el caller (listar_cuentas_pendientes_cliente,
        ya ordenado por fecha_generacion ASC) -- esta funcion solo debe
        respetarlo, nunca reordenar por su cuenta."""
        cuentas = [(99, 5.0), (1, 5.0), (50, 5.0)]
        distribucion, _sobrante = distribuir_pago_automatico(cuentas, 10.0)
        self.assertEqual([cuenta_id for cuenta_id, _ in distribucion], [99, 1])


if __name__ == "__main__":
    unittest.main()
