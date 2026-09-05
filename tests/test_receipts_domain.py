"""Tests unitarios (sin Flask, sin DB) de app/domain/sales/receipts.py:
la unica autoridad sobre subtotal/descuento/delivery/total/total_bs del
recibo del cliente. Cubren especificamente los tres casos de compatibilidad
historica descritos en la migracion (legacy, explicito sin snapshot Bs,
explicito nuevo) y la regla de "nunca tasa viva cuando hay snapshot".
"""

import unittest

from app.domain.sales.item_descriptions import agrupar_items_recibo
from app.domain.sales.receipts import (
    construir_recibo_cobrado,
    construir_recibo_provisional,
)


class AgruparItemsReciboTest(unittest.TestCase):
    def test_agrupa_por_nombre_sumando_cantidad_y_total(self):
        items = [("Neko Combo 2", 8.0, ""), ("Neko Combo 2", 8.0, "")]
        self.assertEqual(
            agrupar_items_recibo(items),
            [{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}],
        )

    def test_ignora_indicacion_al_agrupar(self):
        items = [("Pollo Agridulce", 8.0, "sin cebolla"), ("Pollo Agridulce", 8.0, "con salsa extra")]
        resultado = agrupar_items_recibo(items)
        self.assertEqual(resultado, [{"cantidad": 2, "nombre": "Pollo Agridulce", "total": 16.0}])

    def test_no_incluye_indicacion_ni_descripcion_de_combo(self):
        items = [("2x Neko Combo 2", 16.0, '{"version":1,"tipo":"combo","producto":"combo2"}')]
        resultado = agrupar_items_recibo(items)
        self.assertEqual(resultado, [{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}])
        # nada de "•" ni texto de acompanantes/bebida en el nombre
        self.assertNotIn("•", resultado[0]["nombre"])

    def test_items_distintos_no_se_mezclan(self):
        items = [("Neko Combo 2", 8.0, ""), ("Frescolita", 1.5, "")]
        resultado = agrupar_items_recibo(items)
        self.assertEqual(
            resultado,
            [
                {"cantidad": 1, "nombre": "Neko Combo 2", "total": 8.0},
                {"cantidad": 1, "nombre": "Frescolita", "total": 1.5},
            ],
        )

    def test_lista_vacia(self):
        self.assertEqual(agrupar_items_recibo([]), [])


class ReciboProvisionalTest(unittest.TestCase):
    def test_cobrada_false(self):
        recibo = construir_recibo_provisional(
            [("Neko Combo 2", 16.0, "")], delivery_usd=0, descuento_bs=0, tasa_actual=100
        )
        self.assertFalse(recibo["cobrada"])

    def test_usa_tasa_vigente_para_total_bs(self):
        recibo = construir_recibo_provisional(
            [("Neko Combo 2", 16.0, "")], delivery_usd=0, descuento_bs=0, tasa_actual=100
        )
        self.assertEqual(recibo["total"], 16.0)
        self.assertEqual(recibo["total_bs"], 1600.0)

        recibo_tasa_distinta = construir_recibo_provisional(
            [("Neko Combo 2", 16.0, "")], delivery_usd=0, descuento_bs=0, tasa_actual=200
        )
        self.assertEqual(recibo_tasa_distinta["total_bs"], 3200.0)

    def test_incluye_delivery_explicito(self):
        recibo = construir_recibo_provisional(
            [("Neko Combo 2", 20.0, "")], delivery_usd=3.0, descuento_bs=0, tasa_actual=100
        )
        self.assertEqual(recibo["delivery"], 3.0)
        self.assertEqual(recibo["total"], 23.0)
        self.assertEqual(recibo["total_bs"], 2300.0)

    def test_descuento_bs_se_convierte_a_usd_con_tasa_vigente(self):
        recibo = construir_recibo_provisional(
            [("Neko Combo 2", 20.0, "")], delivery_usd=0, descuento_bs=500, tasa_actual=100
        )
        self.assertEqual(recibo["descuento"], 5.0)
        self.assertEqual(recibo["subtotal"], 20.0)
        self.assertEqual(recibo["total"], 15.0)

    def test_items_sin_detalle_interno(self):
        recibo = construir_recibo_provisional(
            [("2x Neko Combo 2", 16.0, '{"version":1,"tipo":"combo","producto":"combo2"}')],
            delivery_usd=0,
            descuento_bs=0,
            tasa_actual=100,
        )
        self.assertEqual(recibo["items"], [{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}])


class ReciboCobradoTest(unittest.TestCase):
    def _base_cobrado(self, **overrides):
        base = dict(
            tasa_cobro=100,
            subtotal_usd=20.0,
            descuento_bs=0,
            total_usd=20.0,
            total_bs=2000.0,
            venta_restaurante_usd=20.0,
            delivery_usd=3.0,
            total_cliente_usd=23.0,
            total_cliente_bs=2300.0,
        )
        base.update(overrides)
        return base

    def test_cobrada_true(self):
        recibo = construir_recibo_cobrado([("Neko Combo 2", 20.0, "")], **self._base_cobrado())
        self.assertTrue(recibo["cobrada"])

    def test_explicito_nuevo_usa_total_cliente_bs_persistido_directo(self):
        recibo = construir_recibo_cobrado([("Neko Combo 2", 20.0, "")], **self._base_cobrado())
        self.assertEqual(recibo["total"], 23.0)
        self.assertEqual(recibo["total_bs"], 2300.0)
        self.assertEqual(recibo["delivery"], 3.0)
        self.assertEqual(recibo["subtotal"], 20.0)

    def test_total_cliente_bs_coincide_exactamente_con_el_dominio(self):
        # No debe recalcularse con otra estrategia de redondeo: debe ser
        # EXACTAMENTE el valor que ya devolvio calcular_totales_financieros_delivery.
        from app.domain.sales.calculations import calcular_totales_financieros_delivery

        items_cobro = [("Neko Combo 2", 19.99, None)]
        totales = calcular_totales_financieros_delivery(items_cobro, 137.42, 0, 4.33)

        recibo = construir_recibo_cobrado(
            [("Neko Combo 2", 19.99, "")],
            tasa_cobro=totales["tasa"],
            subtotal_usd=totales["subtotal_restaurante_usd"],
            descuento_bs=totales["descuento_bs"],
            total_usd=totales["total_usd"],
            total_bs=totales["total_bs"],
            venta_restaurante_usd=totales["venta_restaurante_usd"],
            delivery_usd=totales["delivery_usd"],
            total_cliente_usd=totales["total_cliente_usd"],
            total_cliente_bs=totales["total_cliente_bs"],
        )

        self.assertEqual(recibo["total_bs"], totales["total_cliente_bs"])
        self.assertEqual(recibo["total"], totales["total_cliente_usd"])

    def test_legacy_delivery_como_item_usa_total_bs_historico(self):
        recibo = construir_recibo_cobrado(
            [("Neko Combo 2", 20.0, ""), ("Delivery 3", 3.0, "")],
            tasa_cobro=100,
            subtotal_usd=23.0,
            descuento_bs=0,
            total_usd=23.0,
            total_bs=2300.0,
            venta_restaurante_usd=None,
            delivery_usd=None,
            total_cliente_usd=None,
            total_cliente_bs=None,
        )
        self.assertEqual(recibo["total"], 23.0)
        self.assertEqual(recibo["total_bs"], 2300.0)
        self.assertEqual(recibo["delivery"], 0.0)
        # El item de delivery legacy SI aparece como producto normal.
        nombres = [item["nombre"] for item in recibo["items"]]
        self.assertIn("Delivery 3", nombres)

    def test_explicito_historico_sin_total_cliente_bs_reconstruye_con_tasa_cobro(self):
        recibo = construir_recibo_cobrado(
            [("Neko Combo 2", 20.0, "")],
            **self._base_cobrado(total_cliente_bs=None),
        )
        # 23.0 (total_cliente_usd) * 100 (tasa_cobro) = 2300.0, reconstruido
        # con datos 100% historicos, nunca con una tasa "viva" distinta.
        self.assertEqual(recibo["total_bs"], 2300.0)
        self.assertEqual(recibo["total"], 23.0)

    def test_reimpresion_no_cambia_aunque_la_tasa_actual_cambie(self):
        """construir_recibo_cobrado ni siquiera recibe una tasa actual:
        demuestra que el resultado es identico sin importar cuantas veces
        se llame ni que otra cosa haya cambiado en el sistema mientras
        tanto (no hay parametro de tasa viva que pueda colarse)."""
        entrada = self._base_cobrado()
        primera = construir_recibo_cobrado([("Neko Combo 2", 20.0, "")], **entrada)
        segunda = construir_recibo_cobrado([("Neko Combo 2", 20.0, "")], **entrada)
        self.assertEqual(primera, segunda)

    def test_descuento_se_convierte_con_tasa_cobro_no_con_tasa_viva(self):
        recibo = construir_recibo_cobrado(
            [("Neko Combo 2", 20.0, "")],
            **self._base_cobrado(descuento_bs=1000, tasa_cobro=200),
        )
        self.assertEqual(recibo["descuento"], 5.0)

    def test_items_sin_detalle_interno_en_orden_cobrada(self):
        recibo = construir_recibo_cobrado(
            [("2x Neko Combo 2", 16.0, '{"version":1,"tipo":"combo","producto":"combo2"}')],
            **self._base_cobrado(),
        )
        self.assertEqual(recibo["items"], [{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}])


if __name__ == "__main__":
    unittest.main()
