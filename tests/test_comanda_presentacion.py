"""Tests de la capa de presentacion de comandas (scripts_locales).

No abren COM6: `BluetoothPrinter` se sustituye siempre por un stub que
solo registra las lineas impresas, igual que test_facturas_sin_papel.py
en NekoPrinterTest hace con `facturas_cliente.py`.

IMPORTANTE sobre `secuencia`: en la BD real, `orden_comandas.secuencia` es
0-INDEXADA (primer lote de una orden = secuencia 0, segundo = 1, tercero =
2, ...). Confirmado en
app/infrastructure/database/kitchen_comandas.py::_reservar_secuencia_comanda
y en tests/test_self_ordering_routes.py,
test_mixed_manual_and_self_ordering_batches_share_one_sequence_by_item_id
([0, 1, 2, 3] para 4 lotes). Estos tests usan esos mismos valores reales,
no una numeracion inventada empezando en 1.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import comanda_presentacion as presentacion  # noqa: E402


class _PrinterStub:
    """Stub minimo de BluetoothPrinter: no abre ningun puerto, solo
    registra el texto que se le pide imprimir para poder inspeccionarlo."""

    def __init__(self, *args, **kwargs):
        self.lineas = []
        self._bold = False
        self._size = "normal"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def connect(self):
        pass

    def disconnect(self):
        pass

    def align(self, mode):
        pass

    def set_bold(self, enabled):
        self._bold = enabled

    def set_size(self, size="normal"):
        self._size = size

    def print_line(self, text=""):
        self.lineas.append(text)

    def print_text(self, text):
        self.lineas.append(text)

    def print_wrapped(self, text, width=None):
        self.lineas.append(text)

    def wrap_text(self, text, width=None):
        return [text]

    def feed(self, lines=1):
        pass

    def print_image(self, *args, **kwargs):
        pass

    def send_bytes(self, data):
        pass


class NumeroComandaVisibleTest(unittest.TestCase):
    def test_primer_envio_secuencia_0_muestra_solo_numero(self):
        self.assertEqual(presentacion.numero_comanda_visible(38, 0), "38")

    def test_segundo_envio_secuencia_1_agrega_punto_1(self):
        self.assertEqual(presentacion.numero_comanda_visible(38, 1), "38.1")

    def test_tercer_envio_secuencia_2_agrega_punto_2(self):
        self.assertEqual(presentacion.numero_comanda_visible(38, 2), "38.2")

    def test_cuarto_envio_secuencia_3_agrega_punto_3(self):
        self.assertEqual(presentacion.numero_comanda_visible(38, 3), "38.3")

    def test_sin_secuencia_muestra_solo_numero(self):
        self.assertEqual(presentacion.numero_comanda_visible(38, None), "38")

    def test_secuencia_no_numerica_muestra_solo_numero(self):
        self.assertEqual(presentacion.numero_comanda_visible(38, "no-es-numero"), "38")

    def test_secuencia_negativa_no_genera_sufijo_negativo(self):
        # Nunca deberia ocurrir en datos reales, pero no debe romperse ni
        # producir un sufijo sin sentido como "38.-1".
        self.assertEqual(presentacion.numero_comanda_visible(38, -1), "38")


class ImprimirComandaHeaderTest(unittest.TestCase):
    def _orden(self, **overrides):
        base = {
            "id": 1,
            "comanda_id": 1,
            "numero": 38,
            "secuencia": 0,
            "tipo": "Mesa",
            "referencia": "Mesa 1",
            "cliente": "Cliente",
            "usuario": "Mesonera",
            "estado": "en cocina",
            "reimpresion_token": None,
            "items": ["1x Producto"],
        }
        base.update(overrides)
        return base

    def _imprimir_y_capturar(self, orden):
        stub = _PrinterStub()
        with mock.patch.object(presentacion, "BluetoothPrinter", return_value=stub):
            with mock.patch.object(presentacion.winsound, "Beep"):
                presentacion.imprimir_comanda(orden)
        return stub.lineas

    def test_primer_envio_muestra_comanda_numero_sin_sufijo(self):
        lineas = self._imprimir_y_capturar(self._orden(numero=38, secuencia=0))
        self.assertIn("COMANDA #38", lineas)

    def test_segundo_envio_muestra_comanda_numero_punto_1(self):
        lineas = self._imprimir_y_capturar(self._orden(numero=38, secuencia=1))
        self.assertIn("COMANDA #38.1", lineas)
        self.assertNotIn("COMANDA #38", lineas)

    def test_tercer_envio_muestra_comanda_numero_punto_2(self):
        lineas = self._imprimir_y_capturar(self._orden(numero=38, secuencia=2))
        self.assertIn("COMANDA #38.2", lineas)
        self.assertNotIn("COMANDA #38.1", lineas)

    def test_cuarto_envio_muestra_comanda_numero_punto_3(self):
        lineas = self._imprimir_y_capturar(self._orden(numero=38, secuencia=3))
        self.assertIn("COMANDA #38.3", lineas)

    def test_dos_envios_consecutivos_no_repiten_el_mismo_numero_visible(self):
        primero = self._imprimir_y_capturar(self._orden(numero=38, secuencia=0))
        segundo = self._imprimir_y_capturar(self._orden(numero=38, secuencia=1))

        encabezado_primero = next(l for l in primero if l.startswith("COMANDA #"))
        encabezado_segundo = next(l for l in segundo if l.startswith("COMANDA #"))
        self.assertNotEqual(encabezado_primero, encabezado_segundo)

    def test_legacy_sin_secuencia_muestra_comanda_numero_sin_sufijo(self):
        orden = self._orden(numero=38)
        del orden["secuencia"]
        lineas = self._imprimir_y_capturar(orden)
        self.assertIn("COMANDA #38", lineas)

    def test_reimpresion_muestra_siempre_numero_base_no_el_del_ultimo_lote(self):
        """La reimpresion es el acumulado de TODA la orden (ver backend:
        obtener_items_enviados_de_orden), no un lote puntual - el encabezado
        debe mostrar el numero base de la orden, nunca "<numero>.<secuencia>"
        del ultimo lote que disparo el reimpresion_token."""
        lineas = self._imprimir_y_capturar(
            self._orden(numero=38, secuencia=2, reimpresion_token="tok-123")
        )
        self.assertIn("COMANDA #38", lineas)
        self.assertNotIn("COMANDA #38.2", lineas)
        self.assertIn("REIMPRESION", lineas)
        self.assertIn("DE COCINA", lineas)

    def test_reimpresion_indicador_aparece_junto_con_numero_base(self):
        lineas = self._imprimir_y_capturar(
            self._orden(numero=38, secuencia=3, reimpresion_token="tok-456")
        )
        self.assertIn("REIMPRESION", lineas)
        self.assertIn("DE COCINA", lineas)
        self.assertIn("COMANDA #38", lineas)


if __name__ == "__main__":
    unittest.main()
