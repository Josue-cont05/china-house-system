"""Tests de app/domain/sales/kitchen_ticket_times.py: formato de horas
en el papel de cocina, incluyendo la conversion America/Caracas y la
recuperacion tras apagon (hora historica, nunca la hora actual)."""

import unittest

from app.domain.sales.kitchen_ticket_times import (
    ETIQUETA_AGREGADO,
    ETIQUETA_HORA,
    ETIQUETA_PEDIDO,
    encabezado_horas_comanda,
    formatear_hora_visible,
    parsear_como_caracas,
)


class FormatearHoraVisibleTest(unittest.TestCase):
    def test_hora_pm_sin_cero_a_la_izquierda(self):
        self.assertEqual(formatear_hora_visible("2026-09-05 19:12:00"), "7:12 PM")

    def test_hora_am(self):
        self.assertEqual(formatear_hora_visible("2026-09-05 07:05:00"), "7:05 AM")

    def test_mediodia(self):
        self.assertEqual(formatear_hora_visible("2026-09-05 12:00:00"), "12:00 PM")

    def test_medianoche(self):
        self.assertEqual(formatear_hora_visible("2026-09-05 00:30:00"), "12:30 AM")

    def test_vacio_no_lanza(self):
        self.assertEqual(formatear_hora_visible(""), "")
        self.assertEqual(formatear_hora_visible(None), "")

    def test_conversion_america_caracas_zona_correcta(self):
        dt = parsear_como_caracas("2026-09-05 19:12:00")
        self.assertEqual(str(dt.tzinfo), "America/Caracas")
        # America/Caracas es UTC-4 (sin horario de verano).
        self.assertEqual(dt.utcoffset().total_seconds(), -4 * 3600)


class EncabezadoHorasComandaTest(unittest.TestCase):
    def test_comanda_inicial_normal_usa_etiqueta_hora(self):
        lineas = encabezado_horas_comanda(
            secuencia=0, es_reimpresion=False, hora_pedido_texto="2026-09-05 19:12:00"
        )
        self.assertEqual(lineas, [(ETIQUETA_HORA, "7:12 PM")])

    def test_incremental_normal_usa_pedido_y_agregado(self):
        lineas = encabezado_horas_comanda(
            secuencia=1,
            es_reimpresion=False,
            hora_pedido_texto="2026-09-05 19:12:00",
            hora_agregado_texto="2026-09-05 19:24:00",
        )
        self.assertEqual(lineas, [(ETIQUETA_PEDIDO, "7:12 PM"), (ETIQUETA_AGREGADO, "7:24 PM")])

    def test_segundo_incremental_usa_su_propia_hora_agregado_no_la_anterior(self):
        lineas = encabezado_horas_comanda(
            secuencia=2,
            es_reimpresion=False,
            hora_pedido_texto="2026-09-05 19:12:00",
            hora_agregado_texto="2026-09-05 19:40:00",
        )
        self.assertEqual(dict(lineas)[ETIQUETA_PEDIDO], "7:12 PM")
        self.assertEqual(dict(lineas)[ETIQUETA_AGREGADO], "7:40 PM")

    def test_reimpresion_de_comanda_base_usa_pedido_sin_agregado(self):
        lineas = encabezado_horas_comanda(
            secuencia=0, es_reimpresion=True, hora_pedido_texto="2026-09-05 19:12:00"
        )
        self.assertEqual(lineas, [(ETIQUETA_PEDIDO, "7:12 PM")])

    def test_reimpresion_de_incremental_usa_pedido_y_agregado(self):
        lineas = encabezado_horas_comanda(
            secuencia=1,
            es_reimpresion=True,
            hora_pedido_texto="2026-09-05 19:12:00",
            hora_agregado_texto="2026-09-05 19:24:00",
        )
        self.assertEqual(lineas, [(ETIQUETA_PEDIDO, "7:12 PM"), (ETIQUETA_AGREGADO, "7:24 PM")])

    def test_recuperacion_tras_apagon_conserva_hora_historica(self):
        # La comanda se envio a las 7:12 PM pero el papel sale a las
        # 7:39 PM (apagon). El ticket DEBE decir 7:12 PM, nunca 7:39 PM;
        # esta funcion ni siquiera recibe la hora "actual", solo la
        # historica - por diseno no puede sustituirla.
        lineas = encabezado_horas_comanda(
            secuencia=0, es_reimpresion=False, hora_pedido_texto="2026-09-05 19:12:00"
        )
        self.assertEqual(lineas, [(ETIQUETA_HORA, "7:12 PM")])
        self.assertNotIn("7:39 PM", dict(lineas).values())


if __name__ == "__main__":
    unittest.main()
