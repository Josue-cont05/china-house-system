"""Tests del worker local de impresion de comandas (scripts_locales).

No abren COM6 ni hacen requests reales: `imprimir_comanda` y `requests.get`
se sustituyen siempre por mocks. Cubren exclusivamente la logica del worker
(deduplicacion persistente, manejo de errores, y que cada evento se pasa
al presentador exactamente como llega) - no la impresion fisica en si,
que ya esta fisicamente aprobada en NekoPrinterTest.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import script_comanda_cocina as worker  # noqa: E402  (import needs sys.path patch above)


class ComandaPrinterWorkerTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._archivo_original = worker.ARCHIVO_IMPRESAS
        worker.ARCHIVO_IMPRESAS = Path(self._tmpdir.name) / "comandas_impresas.txt"
        worker.impresos = set()

    def tearDown(self):
        worker.ARCHIVO_IMPRESAS = self._archivo_original
        self._tmpdir.cleanup()

    def _orden(self, evento_impresion, items, **overrides):
        base = {
            "id": 1,
            "numero": 1,
            "tipo": "Mesa",
            "referencia": "Mesa 1",
            "cliente": "Cliente",
            "usuario": "Mesonera",
            "estado": "en cocina",
            "reimpresion_token": None,
            "items": items,
            "evento_impresion": evento_impresion,
        }
        base.update(overrides)
        return base

    # 1. evento nuevo + impresion exitosa -> imprime y persiste
    def test_new_event_prints_and_persists(self):
        orden = self._orden("comanda-1-base", ["1x Neko Combo 2"])

        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(orden)

        mock_print.assert_called_once_with(orden)
        self.assertIn("comanda-1-base", worker.impresos)
        self.assertEqual(
            worker.ARCHIVO_IMPRESAS.read_text(encoding="utf-8").splitlines(),
            ["comanda-1-base"],
        )

    # 2. mismo evento de nuevo -> no imprime
    def test_same_event_again_does_not_reprint(self):
        orden = self._orden("comanda-1-base", ["1x Neko Combo 2"])

        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(orden)
            worker.procesar_comanda(orden)

        mock_print.assert_called_once_with(orden)

    # 3. nueva instancia/reinicio -> carga persistencia y no repite
    def test_restart_loads_persisted_events_and_does_not_repeat(self):
        orden = self._orden("comanda-1-base", ["1x Neko Combo 2"])
        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(orden)

        # Simula un reinicio del proceso: nueva instancia de `impresos`,
        # reconstruida solo desde el archivo persistido en disco.
        worker.impresos = worker.cargar_impresos()

        with mock.patch.object(worker, "imprimir_comanda") as mock_print_after_restart:
            worker.procesar_comanda(orden)

        mock_print_after_restart.assert_not_called()

    # 4. incremental con evento diferente -> imprime
    def test_incremental_event_with_different_id_prints(self):
        inicial = self._orden("comanda-1-base", ["1x Neko Combo 2"])
        incremental = self._orden("comanda-2-base", ["1x Frescolita"], id=2)

        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(inicial)
            worker.procesar_comanda(incremental)

        self.assertEqual(mock_print.call_count, 2)
        mock_print.assert_any_call(inicial)
        mock_print.assert_any_call(incremental)

    # 5. reimpresion con evento diferente -> imprime aunque la comanda base
    #    ya haya sido impresa (mismo comanda_id, evento_impresion distinto
    #    por el token de reimpresion)
    def test_reprint_with_different_event_prints_even_if_base_already_printed(self):
        original = self._orden("comanda-1-base", ["1x Neko Combo 2"], id=1)
        reimpresion = self._orden(
            "comanda-1-20260904201530000000",
            ["1x Neko Combo 2"],
            id=1,
            reimpresion_token="20260904201530000000",
        )

        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(original)
            worker.procesar_comanda(reimpresion)

        self.assertEqual(mock_print.call_count, 2)
        self.assertIn("comanda-1-base", worker.impresos)
        self.assertIn("comanda-1-20260904201530000000", worker.impresos)

    # 6. fallo del printer -> no persiste
    def test_printer_failure_does_not_persist(self):
        orden = self._orden("comanda-1-base", ["1x Neko Combo 2"])

        with mock.patch.object(
            worker, "imprimir_comanda", side_effect=worker.PrinterError("sin papel")
        ):
            worker.procesar_comanda(orden)

        self.assertNotIn("comanda-1-base", worker.impresos)
        self.assertFalse(worker.ARCHIVO_IMPRESAS.exists())

        # Debe poder reintentarse en el siguiente ciclo sin quedar bloqueado.
        with mock.patch.object(worker, "imprimir_comanda") as mock_print_retry:
            worker.procesar_comanda(orden)

        mock_print_retry.assert_called_once_with(orden)
        self.assertIn("comanda-1-base", worker.impresos)

    # 6b. una excepcion inesperada (no PrinterError) tampoco debe persistir
    # ni tirar abajo el worker.
    def test_unexpected_printer_exception_does_not_persist(self):
        orden = self._orden("comanda-1-base", ["1x Neko Combo 2"])

        with mock.patch.object(
            worker, "imprimir_comanda", side_effect=RuntimeError("puerto ocupado")
        ):
            worker.procesar_comanda(orden)

        self.assertNotIn("comanda-1-base", worker.impresos)

    # 7. inicial pasa exactamente sus items
    def test_initial_event_forwards_exact_items(self):
        orden = self._orden("comanda-1-base", ["1x Neko Combo 2", "2x Frescolita"])

        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(orden)

        items_recibidos = mock_print.call_args.args[0]["items"]
        self.assertEqual(items_recibidos, ["1x Neko Combo 2", "2x Frescolita"])

    # 8. incremental pasa exactamente sus items y no añade los anteriores
    def test_incremental_event_forwards_only_its_own_items(self):
        inicial = self._orden("comanda-1-base", ["1x Neko Combo 2"], id=1)
        incremental = self._orden("comanda-2-base", ["1x Frescolita"], id=1)

        with mock.patch.object(worker, "imprimir_comanda") as mock_print:
            worker.procesar_comanda(inicial)
            worker.procesar_comanda(incremental)

        primeros_items = mock_print.call_args_list[0].args[0]["items"]
        segundos_items = mock_print.call_args_list[1].args[0]["items"]
        self.assertEqual(primeros_items, ["1x Neko Combo 2"])
        self.assertEqual(segundos_items, ["1x Frescolita"])
        self.assertNotIn("1x Neko Combo 2", segundos_items)

    # 9. archivo de persistencia inexistente -> arranque normal
    def test_missing_persistence_file_starts_empty(self):
        self.assertFalse(worker.ARCHIVO_IMPRESAS.exists())
        self.assertEqual(worker.cargar_impresos(), set())

    # 10. archivo vacio -> arranque normal
    def test_empty_persistence_file_starts_empty(self):
        worker.ARCHIVO_IMPRESAS.write_text("", encoding="utf-8")
        self.assertEqual(worker.cargar_impresos(), set())

    def test_guardar_impreso_appends_one_event_per_line(self):
        worker.guardar_impreso("comanda-1-base")
        worker.guardar_impreso("comanda-2-base")

        self.assertEqual(
            worker.ARCHIVO_IMPRESAS.read_text(encoding="utf-8").splitlines(),
            ["comanda-1-base", "comanda-2-base"],
        )

    def test_obtener_comandas_returns_empty_list_on_non_200(self):
        respuesta = mock.Mock(status_code=500)
        with mock.patch.object(worker.requests, "get", return_value=respuesta):
            self.assertEqual(worker.obtener_comandas(), [])

    def test_obtener_comandas_returns_empty_list_on_invalid_json(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.side_effect = ValueError("invalid json")
        with mock.patch.object(worker.requests, "get", return_value=respuesta):
            self.assertEqual(worker.obtener_comandas(), [])

    def test_obtener_comandas_returns_empty_list_on_non_list_json(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.return_value = {"error": "not a list"}
        with mock.patch.object(worker.requests, "get", return_value=respuesta):
            self.assertEqual(worker.obtener_comandas(), [])

    def test_obtener_comandas_returns_empty_list_on_connection_error(self):
        with mock.patch.object(worker.requests, "get", side_effect=OSError("sin red")):
            self.assertEqual(worker.obtener_comandas(), [])

    def test_one_failing_comanda_does_not_block_the_rest_of_the_batch(self):
        buena_1 = self._orden("comanda-1-base", ["1x Neko Combo 2"], id=1)
        mala = self._orden("comanda-2-base", ["1x Frescolita"], id=2)
        buena_2 = self._orden("comanda-3-base", ["1x Familiar"], id=3)

        def falla_solo_la_mala(orden):
            if orden["id"] == 2:
                raise worker.PrinterError("bluetooth desconectado")

        with mock.patch.object(worker, "imprimir_comanda", side_effect=falla_solo_la_mala):
            for orden in (buena_1, mala, buena_2):
                worker.procesar_comanda(orden)

        self.assertIn("comanda-1-base", worker.impresos)
        self.assertNotIn("comanda-2-base", worker.impresos)
        self.assertIn("comanda-3-base", worker.impresos)


if __name__ == "__main__":
    unittest.main()
