"""Tests de launcher_core.py (scripts_locales): orquestacion de Neko Local
sin Tkinter, sin abrir puertos reales y sin requests reales.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import launcher_core  # noqa: E402
import port_detection  # noqa: E402


class ResolverYPersistirPuertoTest(unittest.TestCase):
    def test_ok_no_guarda_config(self):
        config = {"printer_port": "COM6", "printer_fingerprint": {}}
        resultado = port_detection.ResultadoResolucion("ok", "COM6", config, [])

        with mock.patch.object(launcher_core.port_detection, "resolver_puerto", return_value=resultado):
            with mock.patch.object(launcher_core.neko_config, "guardar_config") as mock_guardar:
                obtenido = launcher_core.resolver_y_persistir_puerto(config)

        mock_guardar.assert_not_called()
        self.assertEqual(obtenido.status, "ok")

    def test_rematched_persiste_la_nueva_config(self):
        config_nueva = {"printer_port": "COM8", "printer_fingerprint": {}}
        resultado = port_detection.ResultadoResolucion("rematched", "COM8", config_nueva, [])

        with mock.patch.object(launcher_core.port_detection, "resolver_puerto", return_value=resultado):
            with mock.patch.object(launcher_core.neko_config, "guardar_config") as mock_guardar:
                launcher_core.resolver_y_persistir_puerto({"printer_port": "COM6"})

        mock_guardar.assert_called_once_with(config_nueva)

    def test_usa_config_cargada_si_no_se_pasa_una(self):
        with mock.patch.object(launcher_core.neko_config, "cargar_config", return_value={}) as mock_cargar:
            with mock.patch.object(
                launcher_core.port_detection,
                "resolver_puerto",
                return_value=port_detection.ResultadoResolucion("sin_configurar", None, None, []),
            ):
                launcher_core.resolver_y_persistir_puerto()

        mock_cargar.assert_called_once()


class NekoposAccesibleTest(unittest.TestCase):
    def test_true_si_responde_200(self):
        respuesta = mock.Mock(status_code=200)
        with mock.patch.object(launcher_core.requests, "get", return_value=respuesta):
            self.assertTrue(launcher_core.nekopos_accesible())

    def test_false_si_responde_error(self):
        respuesta = mock.Mock(status_code=500)
        with mock.patch.object(launcher_core.requests, "get", return_value=respuesta):
            self.assertFalse(launcher_core.nekopos_accesible())

    def test_false_si_no_hay_conexion(self):
        with mock.patch.object(launcher_core.requests, "get", side_effect=OSError("sin red")):
            self.assertFalse(launcher_core.nekopos_accesible())

    def test_no_crashea_ante_excepcion_inesperada(self):
        with mock.patch.object(launcher_core.requests, "get", side_effect=RuntimeError("boom")):
            self.assertFalse(launcher_core.nekopos_accesible())


class GestorWorkerCocinaTest(unittest.TestCase):
    def setUp(self):
        self.gestor = launcher_core.GestorWorkerCocina(
            worker_path=SCRIPTS_LOCALES_DIR / "script_comanda_cocina.py",
            python_exe="python",
        )

    def test_no_esta_activo_antes_de_iniciar(self):
        self.assertFalse(self.gestor.activo)

    def test_iniciar_lanza_subprocess_con_puerto(self):
        proceso_falso = mock.Mock()
        proceso_falso.poll.return_value = None

        with mock.patch.object(launcher_core.subprocess, "Popen", return_value=proceso_falso) as mock_popen:
            self.gestor.iniciar("COM7")

        args_llamada = mock_popen.call_args.args[0]
        self.assertIn("--port", args_llamada)
        self.assertIn("COM7", args_llamada)
        self.assertTrue(self.gestor.activo)

    def test_iniciar_dos_veces_no_duplica_proceso(self):
        proceso_falso = mock.Mock()
        proceso_falso.poll.return_value = None

        with mock.patch.object(launcher_core.subprocess, "Popen", return_value=proceso_falso) as mock_popen:
            self.gestor.iniciar("COM7")
            self.gestor.iniciar("COM7")

        self.assertEqual(mock_popen.call_count, 1)

    def test_iniciar_sin_puerto_no_agrega_flag(self):
        proceso_falso = mock.Mock()
        proceso_falso.poll.return_value = None

        with mock.patch.object(launcher_core.subprocess, "Popen", return_value=proceso_falso) as mock_popen:
            self.gestor.iniciar(None)

        args_llamada = mock_popen.call_args.args[0]
        self.assertNotIn("--port", args_llamada)

    def test_detener_sin_proceso_propio_no_hace_nada(self):
        self.assertTrue(self.gestor.detener())

    def test_detener_termina_proceso_propio(self):
        proceso_falso = mock.Mock()
        proceso_falso.poll.side_effect = [None, 0]  # activo, luego terminado

        with mock.patch.object(launcher_core.subprocess, "Popen", return_value=proceso_falso):
            self.gestor.iniciar("COM7")

        self.gestor.detener()

        proceso_falso.terminate.assert_called_once()
        self.assertFalse(self.gestor.activo)

    def test_detener_usa_kill_si_terminate_no_alcanza(self):
        proceso_falso = mock.Mock()
        proceso_falso.poll.return_value = None
        proceso_falso.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=5), None]

        with mock.patch.object(launcher_core.subprocess, "Popen", return_value=proceso_falso):
            self.gestor.iniciar("COM7")

        self.gestor.detener()

        proceso_falso.terminate.assert_called_once()
        proceso_falso.kill.assert_called_once()

    def test_activo_es_false_si_el_proceso_ya_termino_solo(self):
        proceso_falso = mock.Mock()
        proceso_falso.poll.return_value = 1  # ya termino por su cuenta

        with mock.patch.object(launcher_core.subprocess, "Popen", return_value=proceso_falso):
            self.gestor.iniciar("COM7")

        self.assertFalse(self.gestor.activo)


class GestorWorkerCocinaAliasTest(unittest.TestCase):
    """GestorWorkerCocina es un alias retrocompatible de GestorWorkerProceso
    tras generalizar la clase para tambien arrancar el worker de recibos."""

    def test_alias_apunta_a_la_misma_clase(self):
        self.assertIs(launcher_core.GestorWorkerCocina, launcher_core.GestorWorkerProceso)


class DosWorkersIndependientesTest(unittest.TestCase):
    """Cocina y recibos son instancias independientes de GestorWorkerProceso:
    arrancar/detener una no afecta el estado de la otra."""

    def test_cada_worker_gestiona_su_propio_proceso_por_separado(self):
        gestor_cocina = launcher_core.GestorWorkerProceso(worker_path=launcher_core.WORKER_COCINA_PATH)
        gestor_recibos = launcher_core.GestorWorkerProceso(worker_path=launcher_core.WORKER_FACTURA_PATH)

        proceso_cocina = mock.Mock()
        proceso_cocina.poll.return_value = None
        proceso_recibos = mock.Mock()
        proceso_recibos.poll.return_value = None

        with mock.patch.object(launcher_core.subprocess, "Popen", side_effect=[proceso_cocina, proceso_recibos]):
            gestor_cocina.iniciar("COM7")
            gestor_recibos.iniciar("COM7")

        self.assertTrue(gestor_cocina.activo)
        self.assertTrue(gestor_recibos.activo)

        gestor_cocina.detener()

        self.assertFalse(gestor_cocina.activo)
        self.assertTrue(gestor_recibos.activo)
        proceso_recibos.terminate.assert_not_called()

    def test_worker_factura_path_apunta_a_script_factura(self):
        self.assertEqual(launcher_core.WORKER_FACTURA_PATH.name, "script_factura.py")


if __name__ == "__main__":
    unittest.main()
