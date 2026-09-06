import unittest

from app.domain.sales.service_alerts import (
    agrupar_items_alerta,
    debe_evaluar_alerta,
    separar_cantidad,
)


class SepararCantidadTest(unittest.TestCase):
    def test_con_prefijo(self):
        self.assertEqual(separar_cantidad("2x Coca-Cola"), (2, "Coca-Cola"))

    def test_sin_prefijo(self):
        self.assertEqual(separar_cantidad("Cerveza"), (1, "Cerveza"))

    def test_vacio(self):
        self.assertEqual(separar_cantidad(""), (1, ""))
        self.assertEqual(separar_cantidad(None), (1, ""))


class AgruparItemsAlertaTest(unittest.TestCase):
    def test_suma_cantidades_del_mismo_nombre(self):
        resultado = agrupar_items_alerta(["Coca-Cola", "Coca-Cola", "Cerveza"])
        self.assertEqual(resultado, ["2x Coca-Cola", "1x Cerveza"])

    def test_respeta_prefijos_ya_presentes(self):
        resultado = agrupar_items_alerta(["2x Coca-Cola", "1x Cerveza"])
        self.assertEqual(resultado, ["2x Coca-Cola", "1x Cerveza"])

    def test_lista_vacia(self):
        self.assertEqual(agrupar_items_alerta([]), [])


class DebeEvaluarAlertaTest(unittest.TestCase):
    def test_mesa_incremental_true(self):
        self.assertTrue(debe_evaluar_alerta("Mesa", 1))

    def test_mesa_primer_lote_false(self):
        self.assertFalse(debe_evaluar_alerta("Mesa", 0))

    def test_pickup_incremental_false(self):
        self.assertFalse(debe_evaluar_alerta("Para llevar", 1))

    def test_delivery_incremental_false(self):
        self.assertFalse(debe_evaluar_alerta("Delivery", 1))

    def test_case_insensitive(self):
        self.assertTrue(debe_evaluar_alerta("MESA", 2))


if __name__ == "__main__":
    unittest.main()
