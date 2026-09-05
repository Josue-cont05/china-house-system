"""Tests del worker local de impresion de recibos (scripts_locales).

No abren COM6 ni hacen requests reales: `imprimir_factura` y
`session_http.get` se sustituyen siempre por mocks. Cubren exclusivamente
la logica del worker (deduplicacion persistente, orden de confirmacion,
manejo de errores) - nunca calculo financiero, que no existe en este
archivo (ver app/domain/sales/receipts.py, la unica autoridad).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import script_factura as worker  # noqa: E402


class FacturaPrinterWorkerTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._archivo_original = worker.ARCHIVO_IMPRESAS
        worker.ARCHIVO_IMPRESAS = Path(self._tmpdir.name) / "facturas_impresas.txt"
        worker.impresos = set()
        worker.eventos_duplicados_reportados = set()

    def tearDown(self):
        worker.ARCHIVO_IMPRESAS = self._archivo_original
        self._tmpdir.cleanup()

    def _factura(self, evento_impresion, **overrides):
        base = {
            "id": 1,
            "numero": 42,
            "cliente": "Juan",
            "tipo": "Mesa",
            "referencia": "Mesa 3",
            "fecha_hora": "2026-09-05 12:00:00",
            "cobrada": True,
            "items": [{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}],
            "subtotal": 16.0,
            "descuento": 0.0,
            "delivery": 0.0,
            "total": 16.0,
            "total_bs": 3360.0,
            "evento_impresion": evento_impresion,
        }
        base.update(overrides)
        return base

    # --- deduplicacion basica --------------------------------------
    def test_new_event_prints_and_persists(self):
        factura = self._factura("1-base")
        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=True) as mock_desact:
                worker.procesar_factura(factura, "COM6")

        mock_print.assert_called_once()
        mock_desact.assert_called_once_with(1)
        self.assertIn("1-base", worker.impresos)
        self.assertEqual(
            worker.ARCHIVO_IMPRESAS.read_text(encoding="utf-8").splitlines(), ["1-base"]
        )

    def test_repeated_event_does_not_reprint(self):
        factura = self._factura("1-base")
        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(factura, "COM6")
                worker.procesar_factura(factura, "COM6")

        mock_print.assert_called_once()

    def test_restart_loads_persisted_events_and_does_not_reprint(self):
        factura = self._factura("1-base")
        with mock.patch.object(worker, "imprimir_factura"):
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(factura, "COM6")

        worker.impresos = worker.cargar_impresos()

        with mock.patch.object(worker, "imprimir_factura") as mock_print_after_restart:
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(factura, "COM6")

        mock_print_after_restart.assert_not_called()

    def test_reprint_with_new_event_prints_even_if_base_already_printed(self):
        original = self._factura("1-base")
        reimpresion = self._factura("1-20260905120500000000")

        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(original, "COM6")
                worker.procesar_factura(reimpresion, "COM6")

        self.assertEqual(mock_print.call_count, 2)
        self.assertIn("1-base", worker.impresos)
        self.assertIn("1-20260905120500000000", worker.impresos)

    # --- orden de confirmacion: imprimir -> persistir -> desactivar --
    def test_printer_failure_does_not_persist_or_deactivate(self):
        factura = self._factura("1-base")
        with mock.patch.object(worker, "imprimir_factura", side_effect=worker.PrinterError("sin papel")):
            with mock.patch.object(worker, "desactivar_factura") as mock_desact:
                worker.procesar_factura(factura, "COM6")

        self.assertNotIn("1-base", worker.impresos)
        self.assertFalse(worker.ARCHIVO_IMPRESAS.exists())
        mock_desact.assert_not_called()

    def test_unexpected_printer_exception_does_not_persist_or_deactivate(self):
        factura = self._factura("1-base")
        with mock.patch.object(worker, "imprimir_factura", side_effect=RuntimeError("puerto ocupado")):
            with mock.patch.object(worker, "desactivar_factura") as mock_desact:
                worker.procesar_factura(factura, "COM6")

        self.assertNotIn("1-base", worker.impresos)
        mock_desact.assert_not_called()

    def test_success_persists_before_calling_desactivar(self):
        factura = self._factura("1-base")
        orden_llamadas = []

        def fake_print(*args, **kwargs):
            orden_llamadas.append("imprimir")

        def fake_desactivar(factura_id):
            orden_llamadas.append("desactivar")
            self.assertIn("1-base", worker.impresos)  # ya persistido ANTES de desactivar
            return True

        with mock.patch.object(worker, "imprimir_factura", side_effect=fake_print):
            with mock.patch.object(worker, "desactivar_factura", side_effect=fake_desactivar):
                worker.procesar_factura(factura, "COM6")

        self.assertEqual(orden_llamadas, ["imprimir", "desactivar"])

    def test_desactivar_failure_does_not_cause_double_printing(self):
        factura = self._factura("1-base")

        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=False):
                worker.procesar_factura(factura, "COM6")

        # El evento ya quedo marcado como impreso pese a que desactivar fallo.
        self.assertIn("1-base", worker.impresos)

        # El siguiente poll ve la MISMA factura (el backend nunca la
        # desactivo) pero NO debe reimprimir - solo reintentar desactivar.
        with mock.patch.object(worker, "imprimir_factura") as mock_print_retry:
            with mock.patch.object(worker, "desactivar_factura", return_value=True) as mock_desact_retry:
                worker.procesar_factura(factura, "COM6")

        mock_print_retry.assert_not_called()
        mock_desact_retry.assert_called_once_with(1)
        self.assertEqual(mock_print.call_count, 1)

    # --- puerto explicito --------------------------------------------
    def test_configured_port_reaches_imprimir_factura(self):
        factura = self._factura("1-base")
        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(factura, "COM7", baudrate=19200)

        self.assertEqual(mock_print.call_args.kwargs["port"], "COM7")
        self.assertEqual(mock_print.call_args.kwargs["baudrate"], 19200)

    def test_total_bs_passed_through_intact(self):
        factura = self._factura("1-base", total_bs=12345.67)
        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(factura, "COM6")

        self.assertEqual(mock_print.call_args.kwargs["total_bs"], 12345.67)

    def test_items_passed_through_intact(self):
        items = [{"cantidad": 3, "nombre": "Frescolita", "total": 4.5}]
        factura = self._factura("1-base", items=items)
        with mock.patch.object(worker, "imprimir_factura") as mock_print:
            with mock.patch.object(worker, "desactivar_factura", return_value=True):
                worker.procesar_factura(factura, "COM6")

        self.assertEqual(mock_print.call_args.kwargs["items"], items)

    # --- nunca calcula dinero ni consulta tasa ------------------------
    def test_worker_module_has_no_tasa_functions_or_urls(self):
        for atributo_prohibido in ("obtener_tasa", "URL_TASA", "cargar_tasa_cache", "guardar_tasa_cache"):
            self.assertFalse(
                hasattr(worker, atributo_prohibido),
                f"script_factura.py no debe definir '{atributo_prohibido}'",
            )
        self.assertNotIn("api/tasa", worker.URL_FACTURAS)
        self.assertNotIn("api/tasa", worker.URL_DESACTIVAR)

    def test_worker_never_calls_requests_get_to_tasa_endpoint(self):
        llamadas = []
        original_get = worker.session_http.get

        def fake_get(url, *args, **kwargs):
            llamadas.append(url)
            respuesta = mock.Mock(status_code=200)
            respuesta.json.return_value = []
            return respuesta

        with mock.patch.object(worker.session_http, "get", side_effect=fake_get):
            worker.obtener_facturas()

        self.assertTrue(all("tasa" not in url for url in llamadas))

    # --- manejo de red -------------------------------------------------
    def test_obtener_facturas_returns_empty_on_non_200(self):
        respuesta = mock.Mock(status_code=500)
        with mock.patch.object(worker.session_http, "get", return_value=respuesta):
            self.assertEqual(worker.obtener_facturas(), [])

    def test_obtener_facturas_returns_empty_on_invalid_json(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.side_effect = ValueError("bad json")
        with mock.patch.object(worker.session_http, "get", return_value=respuesta):
            self.assertEqual(worker.obtener_facturas(), [])

    def test_obtener_facturas_returns_empty_on_connection_error(self):
        with mock.patch.object(worker.session_http, "get", side_effect=OSError("sin red")):
            self.assertEqual(worker.obtener_facturas(), [])

    def test_missing_persistence_file_starts_empty(self):
        self.assertEqual(worker.cargar_impresos(), set())

    def test_empty_persistence_file_starts_empty(self):
        worker.ARCHIVO_IMPRESAS.write_text("", encoding="utf-8")
        self.assertEqual(worker.cargar_impresos(), set())


class WorkerPortResolutionTest(unittest.TestCase):
    def test_override_port_skips_config_lookup(self):
        with mock.patch.object(worker.neko_config, "cargar_config") as mock_cargar:
            puerto, baudrate = worker.resolver_puerto_worker("COM9")

        mock_cargar.assert_not_called()
        self.assertEqual(puerto, "COM9")

    def test_config_ok_uses_saved_port(self):
        config = {"printer_port": "COM6", "baudrate": 9600, "printer_fingerprint": {}}
        resultado = worker.port_detection.ResultadoResolucion("ok", "COM6", config, [])

        with mock.patch.object(worker.neko_config, "cargar_config", return_value=config):
            with mock.patch.object(worker.port_detection, "resolver_puerto", return_value=resultado):
                puerto, baudrate = worker.resolver_puerto_worker(None)

        self.assertEqual((puerto, baudrate), ("COM6", 9600))

    def test_sin_configurar_returns_none(self):
        resultado = worker.port_detection.ResultadoResolucion("sin_configurar", None, None, [])
        with mock.patch.object(worker.neko_config, "cargar_config", return_value={}):
            with mock.patch.object(worker.port_detection, "resolver_puerto", return_value=resultado):
                puerto, baudrate = worker.resolver_puerto_worker(None)
        self.assertIsNone(puerto)


class WorkerMainSingleInstanceTest(unittest.TestCase):
    def test_main_does_not_poll_when_port_unresolved(self):
        with mock.patch.object(worker, "resolver_puerto_worker", return_value=(None, None)):
            with mock.patch.object(worker, "ejecutar_polling") as mock_poll:
                resultado = worker.main([])

        mock_poll.assert_not_called()
        self.assertEqual(resultado, 1)

    def test_main_does_not_poll_when_lock_not_acquired(self):
        with mock.patch.object(worker, "resolver_puerto_worker", return_value=("COM6", 9600)):
            with mock.patch.object(worker, "SingleInstanceLock") as MockLock:
                MockLock.return_value.acquire.return_value = False
                with mock.patch.object(worker, "ejecutar_polling") as mock_poll:
                    resultado = worker.main([])

        mock_poll.assert_not_called()
        self.assertEqual(resultado, 0)

    def test_main_polls_and_releases_lock_when_acquired(self):
        with mock.patch.object(worker, "resolver_puerto_worker", return_value=("COM6", 9600)):
            with mock.patch.object(worker, "SingleInstanceLock") as MockLock:
                instancia = MockLock.return_value
                instancia.acquire.return_value = True
                with mock.patch.object(worker, "ejecutar_polling") as mock_poll:
                    worker.main([])

        mock_poll.assert_called_once_with("COM6", baudrate=9600)
        instancia.release.assert_called_once()

    def test_main_forwards_override_port_argument(self):
        with mock.patch.object(
            worker, "resolver_puerto_worker", return_value=("COM9", 9600)
        ) as mock_resolver:
            with mock.patch.object(worker, "SingleInstanceLock") as MockLock:
                MockLock.return_value.acquire.return_value = True
                with mock.patch.object(worker, "ejecutar_polling"):
                    worker.main(["--port", "COM9"])

        mock_resolver.assert_called_once_with("COM9")

    def test_uses_a_different_mutex_name_than_kitchen_worker(self):
        import script_comanda_cocina as cocina_worker

        self.assertNotEqual(worker.NOMBRE_MUTEX_FACTURAS, cocina_worker.NOMBRE_MUTEX_COCINA)


if __name__ == "__main__":
    unittest.main()
