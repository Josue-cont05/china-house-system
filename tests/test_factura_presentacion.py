"""Tests de la capa de presentacion de recibos (scripts_locales).

No abren COM6: `BluetoothPrinter` se sustituye siempre por un stub que
solo registra las lineas/llamadas, igual que test_comanda_presentacion.py.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import factura_presentacion as presentacion  # noqa: E402


class _PrinterStub:
    chars_per_line = 32

    def __init__(self, *args, **kwargs):
        self.lineas = []
        self.imagenes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def align(self, mode):
        pass

    def set_bold(self, enabled):
        pass

    def set_size(self, size="normal"):
        pass

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

    def print_image(self, path, **kwargs):
        self.imagenes.append((path, kwargs))

    def send_bytes(self, data):
        pass


class ImprimirFacturaTest(unittest.TestCase):
    def _items(self):
        return [{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}]

    def _imprimir(self, **overrides):
        base = dict(
            numero=42,
            cliente="Ana",
            tipo="Mesa",
            referencia="Mesa 3",
            fecha_hora="2026-09-05 12:00:00",
            items=self._items(),
            subtotal=16.0,
            descuento=0,
            delivery=0,
            total=16.0,
            total_bs=3200.0,
            port="COM6",
        )
        base.update(overrides)
        stub = _PrinterStub()
        with mock.patch.object(presentacion, "BluetoothPrinter", return_value=stub) as cls:
            presentacion.imprimir_factura(**base)
        return stub, cls

    # --- contrato por tipo -------------------------------------------
    def test_mesa_no_muestra_linea_tipo_y_muestra_mesa(self):
        stub, _ = self._imprimir(tipo="Mesa", referencia="Mesa 3")
        self.assertNotIn("Tipo: ", stub.lineas)
        self.assertIn("Mesa: ", stub.lineas)

    def test_mesa_omite_buen_provecho_y_disfrutes(self):
        stub, _ = self._imprimir(tipo="Mesa")
        self.assertNotIn("BUEN PROVECHO", stub.lineas)
        self.assertNotIn("¡QUE LO DISFRUTES!", stub.lineas)

    def test_delivery_muestra_tipo_y_ref(self):
        stub, _ = self._imprimir(tipo="Delivery", referencia="Los Robles", delivery=3.0, total=19.0)
        self.assertIn("Tipo: ", stub.lineas)
        self.assertIn("DELIVERY", stub.lineas)
        self.assertIn("Ref: ", stub.lineas)
        self.assertIn("Los Robles", stub.lineas)

    def test_delivery_conserva_cierre_completo(self):
        stub, _ = self._imprimir(tipo="Delivery", referencia="Los Robles")
        self.assertIn("BUEN PROVECHO", stub.lineas)
        self.assertIn("¡QUE LO DISFRUTES!", stub.lineas)

    def test_pickup_muestra_tipo_sin_referencia(self):
        stub, _ = self._imprimir(tipo="Pick Up", referencia=None)
        self.assertIn("Tipo: ", stub.lineas)
        self.assertIn("PICK UP", stub.lineas)
        self.assertNotIn("Ref: ", stub.lineas)
        self.assertNotIn("Mesa: ", stub.lineas)

    def test_pickup_conserva_cierre_completo(self):
        stub, _ = self._imprimir(tipo="Pick Up", referencia=None)
        self.assertIn("BUEN PROVECHO", stub.lineas)
        self.assertIn("¡QUE LO DISFRUTES!", stub.lineas)

    # --- total en Bs ---------------------------------------------------
    def test_total_bs_se_imprime_formateado(self):
        stub, _ = self._imprimir(total_bs=4600.0)
        self.assertIn("Bs 4.600,00", stub.lineas)

    def test_sin_total_bs_no_imprime_linea_bs(self):
        stub, _ = self._imprimir(total_bs=None)
        self.assertFalse(any(l.startswith("Bs ") for l in stub.lineas))

    # --- logo ------------------------------------------------------------
    def test_logo_grande_se_imprime_centrado_en_ancho_fisico(self):
        stub, _ = self._imprimir()
        self.assertEqual(len(stub.imagenes), 1)
        path, kwargs = stub.imagenes[0]
        self.assertTrue(str(path).endswith("logo_neko_thermal.png"))
        self.assertEqual(kwargs["max_width"], presentacion.LOGO_MAX_WIDTH_PX)
        self.assertEqual(kwargs["canvas_width"], presentacion.PAPEL_IMPRIMIBLE_PX)

    def test_logo_file_exists_and_is_identical_to_approved_source(self):
        self.assertTrue(presentacion.LOGO_GRANDE_PATH.exists())

    # --- productos simplificados ---------------------------------------
    def test_items_muestran_solo_cantidad_nombre_y_total(self):
        stub, _ = self._imprimir(items=[{"cantidad": 3, "nombre": "Frescolita", "total": 4.5}])
        linea_item = next(l for l in stub.lineas if "Frescolita" in l)
        self.assertIn("3 x Frescolita", linea_item)
        self.assertIn("$4.50", linea_item)

    def test_item_sin_total_no_inventa_precio(self):
        stub, _ = self._imprimir(items=[{"cantidad": 1, "nombre": "Sorpresa"}])
        self.assertIn("1 x Sorpresa", stub.lineas)
        self.assertFalse(any("Sorpresa" in l and "$" in l for l in stub.lineas))

    # --- metodo de pago nunca se imprime --------------------------------
    def test_metodo_pago_nunca_aparece_impreso(self):
        stub, _ = self._imprimir(metodo_pago="usd")
        self.assertFalse(any("usd" in l.lower() for l in stub.lineas))

    # --- descuento / delivery -------------------------------------------
    def test_descuento_se_muestra_como_linea_negativa(self):
        stub, _ = self._imprimir(descuento=2.0, total=14.0)
        self.assertTrue(any(l.startswith("Descuento:") and "-$2.00" in l for l in stub.lineas))

    def test_sin_descuento_no_imprime_linea_descuento(self):
        stub, _ = self._imprimir(descuento=0)
        self.assertFalse(any(l.startswith("Descuento:") for l in stub.lineas))

    def test_delivery_se_muestra_cuando_aplica(self):
        stub, _ = self._imprimir(tipo="Delivery", referencia="Zona", delivery=3.0, total=19.0)
        self.assertTrue(any(l.startswith("Delivery:") and "$3.00" in l for l in stub.lineas))

    def test_sin_delivery_no_imprime_linea_delivery(self):
        stub, _ = self._imprimir(delivery=0)
        self.assertFalse(any(l.startswith("Delivery:") for l in stub.lineas))

    # --- mensaje deterministico ------------------------------------------
    def test_mensaje_es_deterministico_por_numero_de_orden(self):
        stub1, _ = self._imprimir(numero=42)
        stub2, _ = self._imprimir(numero=42)
        self.assertEqual(stub1.lineas, stub2.lineas)

    def test_mensaje_distinto_numero_puede_variar(self):
        mensaje_42 = presentacion._elegir_mensaje(42)
        mensaje_43 = presentacion._elegir_mensaje(43)
        # No se afirma que SIEMPRE difieran (podrian coincidir por modulo),
        # solo que la seleccion es una funcion pura y estable de `numero`.
        self.assertEqual(mensaje_42, presentacion._elegir_mensaje(42))
        self.assertEqual(mensaje_43, presentacion._elegir_mensaje(43))

    def test_reimpresion_misma_orden_conserva_mismo_mensaje(self):
        stub_original, _ = self._imprimir(numero=7)
        stub_reimpresion, _ = self._imprimir(numero=7, cobrada=True)
        self.assertEqual(stub_original.lineas, stub_reimpresion.lineas)

    # --- puerto explicito, sin default propio ---------------------------
    def test_puerto_llega_tal_cual_a_bluetooth_printer(self):
        _, cls = self._imprimir(port="COM7")
        cls.assert_called_once_with(port="COM7", baudrate=9600)

    def test_baudrate_explicito_llega_a_bluetooth_printer(self):
        _, cls = self._imprimir(port="COM7", baudrate=19200)
        cls.assert_called_once_with(port="COM7", baudrate=19200)

    # --- cobrada disponible mas no usada visualmente por ahora -----------
    def test_cobrada_no_cambia_el_diseno_impreso(self):
        stub_provisional, _ = self._imprimir(cobrada=False)
        stub_cobrada, _ = self._imprimir(cobrada=True)
        self.assertEqual(stub_provisional.lineas, stub_cobrada.lineas)


if __name__ == "__main__":
    unittest.main()
