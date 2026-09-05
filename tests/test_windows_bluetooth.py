"""Tests de windows_bluetooth.py (scripts_locales): consulta de solo
lectura, oculta y con timeout al inventario Bluetooth de Windows.
Nunca ejecuta un powershell.exe real: `ejecutor` siempre se inyecta con
un doble de prueba.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import windows_bluetooth  # noqa: E402


def _proceso(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class ListarDispositivosBluetoothTest(unittest.TestCase):
    def test_lista_json_de_varios_dispositivos(self):
        salida = '[{"FriendlyName":"POS58DCE9B","Status":"OK","InstanceId":"BTHENUM\\\\X"}]'
        ejecutor = mock.Mock(return_value=_proceso(0, salida))

        dispositivos = windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor)

        self.assertEqual(dispositivos, [{"FriendlyName": "POS58DCE9B", "Status": "OK", "InstanceId": "BTHENUM\\X"}])

    def test_un_solo_dispositivo_powershell_devuelve_objeto_no_lista(self):
        # ConvertTo-Json con un unico resultado devuelve un objeto plano,
        # no un array de un elemento: hay que normalizarlo igual.
        salida = '{"FriendlyName":"POS58DCE9B","Status":"OK","InstanceId":"X"}'
        ejecutor = mock.Mock(return_value=_proceso(0, salida))

        dispositivos = windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor)

        self.assertEqual(len(dispositivos), 1)
        self.assertEqual(dispositivos[0]["FriendlyName"], "POS58DCE9B")

    def test_salida_vacia_significa_sin_dispositivos_no_error(self):
        ejecutor = mock.Mock(return_value=_proceso(0, ""))

        dispositivos = windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor)

        self.assertEqual(dispositivos, [])

    def test_returncode_distinto_de_cero_es_desconocido(self):
        ejecutor = mock.Mock(return_value=_proceso(1, ""))

        self.assertIsNone(windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor))

    def test_json_invalido_es_desconocido(self):
        ejecutor = mock.Mock(return_value=_proceso(0, "no es json{"))

        self.assertIsNone(windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor))

    def test_json_de_tipo_inesperado_es_desconocido(self):
        ejecutor = mock.Mock(return_value=_proceso(0, "42"))

        self.assertIsNone(windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor))

    def test_timeout_es_desconocido(self):
        ejecutor = mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=5))

        self.assertIsNone(windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor))

    def test_powershell_no_encontrado_es_desconocido(self):
        ejecutor = mock.Mock(side_effect=FileNotFoundError("powershell no existe"))

        self.assertIsNone(windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor))

    def test_excepcion_generica_es_desconocida_nunca_se_propaga(self):
        ejecutor = mock.Mock(side_effect=RuntimeError("algo raro"))

        self.assertIsNone(windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor))

    def test_nunca_abre_ventana_y_usa_timeout(self):
        ejecutor = mock.Mock(return_value=_proceso(0, "[]"))

        windows_bluetooth.listar_dispositivos_bluetooth(ejecutor=ejecutor)

        _, kwargs = ejecutor.call_args
        self.assertIn("timeout", kwargs)
        self.assertGreater(kwargs["timeout"], 0)
        comando = ejecutor.call_args[0][0]
        self.assertIn("-WindowStyle", comando)
        self.assertIn("Hidden", comando)


class BluetoothDisponibleTest(unittest.TestCase):
    def test_true_si_hay_dispositivos(self):
        self.assertTrue(windows_bluetooth.bluetooth_disponible(dispositivos=[{"FriendlyName": "X"}]))

    def test_false_si_lista_vacia(self):
        self.assertFalse(windows_bluetooth.bluetooth_disponible(dispositivos=[]))

    def test_none_si_no_se_pudo_determinar(self):
        self.assertIsNone(windows_bluetooth.bluetooth_disponible(dispositivos=None, ejecutor=mock.Mock(
            side_effect=RuntimeError("x")
        )))


class BuscarDispositivoPos58Test(unittest.TestCase):
    def test_encuentra_por_nombre_pos58(self):
        dispositivos = [{"FriendlyName": "Mouse generico"}, {"FriendlyName": "POS58DCE9B"}]

        encontrado = windows_bluetooth.buscar_dispositivo_pos58(dispositivos=dispositivos)

        self.assertEqual(encontrado["FriendlyName"], "POS58DCE9B")

    def test_encuentra_por_nombre_generico_bluetooth_spp(self):
        dispositivos = [{"FriendlyName": "Standard Serial over Bluetooth link"}]

        self.assertIsNotNone(windows_bluetooth.buscar_dispositivo_pos58(dispositivos=dispositivos))

    def test_no_encuentra_dispositivo_no_relacionado(self):
        dispositivos = [{"FriendlyName": "Auriculares X"}, {"FriendlyName": "Mouse Y"}]

        self.assertIsNone(windows_bluetooth.buscar_dispositivo_pos58(dispositivos=dispositivos))

    def test_lista_vacia_no_encuentra_nada(self):
        self.assertIsNone(windows_bluetooth.buscar_dispositivo_pos58(dispositivos=[]))

    def test_friendlyname_ausente_no_lanza(self):
        dispositivos = [{"Status": "OK"}]

        self.assertIsNone(windows_bluetooth.buscar_dispositivo_pos58(dispositivos=dispositivos))


class EvaluarBluetoothTest(unittest.TestCase):
    def test_bluetooth_ok_y_pos58_pareada(self):
        ejecutor = mock.Mock(return_value=_proceso(0, '[{"FriendlyName":"POS58DCE9B"}]'))

        bt_ok, pos58 = windows_bluetooth.evaluar_bluetooth(ejecutor=ejecutor)

        self.assertTrue(bt_ok)
        self.assertTrue(pos58)

    def test_bluetooth_ok_pero_pos58_no_encontrada(self):
        ejecutor = mock.Mock(return_value=_proceso(0, '[{"FriendlyName":"Auriculares"}]'))

        bt_ok, pos58 = windows_bluetooth.evaluar_bluetooth(ejecutor=ejecutor)

        self.assertTrue(bt_ok)
        self.assertFalse(pos58)

    def test_sin_bluetooth(self):
        ejecutor = mock.Mock(return_value=_proceso(0, "[]"))

        bt_ok, pos58 = windows_bluetooth.evaluar_bluetooth(ejecutor=ejecutor)

        self.assertFalse(bt_ok)
        self.assertFalse(pos58)

    def test_desconocido_nunca_afirma_no_emparejada(self):
        ejecutor = mock.Mock(side_effect=RuntimeError("x"))

        bt_ok, pos58 = windows_bluetooth.evaluar_bluetooth(ejecutor=ejecutor)

        self.assertIsNone(bt_ok)
        self.assertIsNone(pos58)


if __name__ == "__main__":
    unittest.main()
