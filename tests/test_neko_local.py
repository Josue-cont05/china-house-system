"""Tests del entrypoint unico de Neko Local (neko_local.main): despacho
por argumentos hacia GUI / --kitchen-worker / --receipt-worker /
--version / --diagnostics, sin abrir Tkinter, Bluetooth, COM ni hacer
requests reales. Es el mismo entrypoint que usara NekoLocal.exe una vez
empaquetado (ver launcher_core.GestorWorkerProceso, seccion 4 de la
mision de empaquetado).
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import neko_local  # noqa: E402
import neko_version  # noqa: E402


class VersionYAyudaTest(unittest.TestCase):
    def test_version_imprime_y_no_abre_gui(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            with mock.patch("builtins.print") as mock_print:
                resultado = neko_local.main(["--version"])

        MockApp.assert_not_called()
        self.assertEqual(resultado, 0)
        mock_print.assert_called_once_with(neko_version.version_texto())

    def test_diagnostics_no_abre_gui_ni_hardware(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            with mock.patch.object(neko_local, "_mostrar_diagnostics") as mock_diag:
                resultado = neko_local.main(["--diagnostics"])

        MockApp.assert_not_called()
        mock_diag.assert_called_once()
        self.assertEqual(resultado, 0)

    def test_diagnostics_no_imprime_secretos_y_cubre_las_rutas_clave(self):
        salida = []
        with mock.patch("builtins.print", side_effect=lambda *a: salida.append(" ".join(str(x) for x in a))):
            neko_local._mostrar_diagnostics()

        texto = "\n".join(salida)
        self.assertIn("frozen:", texto)
        self.assertIn("config_path:", texto)
        self.assertIn("state_dir:", texto)
        self.assertIn("logs_dir:", texto)
        self.assertNotIn("printer_fingerprint", texto)  # no vuelca la huella completa

    def test_help_no_abre_gui(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            with self.assertRaises(SystemExit) as ctx:
                neko_local.main(["--help"])

        MockApp.assert_not_called()
        self.assertEqual(ctx.exception.code, 0)

    def test_sin_argumentos_abre_la_gui(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            instancia = MockApp.return_value
            resultado = neko_local.main([])

        MockApp.assert_called_once()
        instancia.run.assert_called_once()
        self.assertEqual(resultado, 0)


class DespachoWorkerTest(unittest.TestCase):
    def test_kitchen_worker_delega_en_script_comanda_cocina(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_comanda_cocina": modulo_falso}):
            with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
                resultado = neko_local.main(["--kitchen-worker"])

        MockApp.assert_not_called()
        modulo_falso.main.assert_called_once_with([])
        self.assertEqual(resultado, 0)

    def test_kitchen_worker_reenvia_override_de_puerto(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_comanda_cocina": modulo_falso}):
            neko_local.main(["--kitchen-worker", "--port", "COM9"])

        modulo_falso.main.assert_called_once_with(["--port", "COM9"])

    def test_receipt_worker_delega_en_script_factura(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_factura": modulo_falso}):
            with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
                resultado = neko_local.main(["--receipt-worker"])

        MockApp.assert_not_called()
        modulo_falso.main.assert_called_once_with([])
        self.assertEqual(resultado, 0)

    def test_receipt_worker_reenvia_override_de_puerto(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_factura": modulo_falso}):
            neko_local.main(["--receipt-worker", "--port", "COM9"])

        modulo_falso.main.assert_called_once_with(["--port", "COM9"])


class GuiConAmbosWorkersTest(unittest.TestCase):
    """La app arranca con los dos GestorWorkerProceso ya configurados con
    su modo_frozen correcto, sin necesitar abrir Tkinter de verdad para
    inspeccionarlo (se construye la app real: Tk se crea igual que en
    los tests existentes de neko_local en la mision anterior)."""

    def test_gestores_tienen_worker_path_y_modo_frozen_distintos(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertNotEqual(app.gestor_cocina.worker_path, app.gestor_recibos.worker_path)
            self.assertNotEqual(app.gestor_cocina.modo_frozen, app.gestor_recibos.modo_frozen)
            self.assertEqual(app.gestor_cocina.modo_frozen, neko_local.MODO_FROZEN_COCINA)
            self.assertEqual(app.gestor_recibos.modo_frozen, neko_local.MODO_FROZEN_FACTURA)
        finally:
            app.root.destroy()

    def test_titulo_incluye_la_version(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertIn(neko_version.APP_VERSION, app.root.title())
        finally:
            app.root.destroy()


if __name__ == "__main__":
    unittest.main()
