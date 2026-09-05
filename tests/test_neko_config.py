"""Tests de neko_config.py (scripts_locales): config local por computadora.

Nunca toca el %LOCALAPPDATA% real del usuario: cada test redirige
`config_dir()` a un directorio temporal propio.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import neko_config  # noqa: E402


class NekoConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            neko_config, "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    # 1. config inexistente
    def test_config_inexistente_devuelve_valores_por_defecto(self):
        config = neko_config.cargar_config()
        self.assertIsNone(config["printer_port"])
        self.assertIsNone(config["printer_fingerprint"])
        self.assertEqual(config["baudrate"], neko_config.DEFAULT_BAUDRATE)

    # 4. guardar/cargar
    def test_guardar_y_cargar_config_valida(self):
        config = {
            "printer_port": "COM7",
            "baudrate": 9600,
            "printer_fingerprint": {"hwid": "BTHENUM\\...", "serial_number": "ABC123"},
        }
        neko_config.guardar_config(config)

        cargada = neko_config.cargar_config()

        self.assertEqual(cargada["printer_port"], "COM7")
        self.assertEqual(cargada["printer_fingerprint"]["serial_number"], "ABC123")

    def test_guardar_crea_el_directorio_si_no_existe(self):
        self.assertFalse(neko_config.config_dir().exists())
        neko_config.guardar_config(neko_config.cargar_config())
        self.assertTrue(neko_config.config_path().exists())

    # 2. config valida (round-trip con valores tipicos)
    def test_config_valida_con_todos_los_campos(self):
        neko_config.guardar_config(
            {
                "printer_port": "COM6",
                "baudrate": 9600,
                "printer_fingerprint": {
                    "hwid": "BTHENUM\\{...}",
                    "serial_number": None,
                    "description": "Standard Serial over Bluetooth link (COM6)",
                    "manufacturer": "Microsoft",
                    "product": None,
                    "vid": None,
                    "pid": None,
                },
            }
        )
        config = neko_config.cargar_config()
        self.assertTrue(neko_config.tiene_impresora_configurada(config))

    # 3. config corrupta
    def test_config_corrupta_no_crashea_y_se_respalda(self):
        neko_config.config_dir().mkdir(parents=True, exist_ok=True)
        ruta = neko_config.config_path()
        ruta.write_text("{esto no es json valido", encoding="utf-8")

        config = neko_config.cargar_config()

        self.assertIsNone(config["printer_port"])
        respaldo = ruta.with_suffix(ruta.suffix + ".bak")
        self.assertTrue(respaldo.exists())

    def test_config_json_valido_pero_no_es_objeto_se_trata_como_corrupta(self):
        neko_config.config_dir().mkdir(parents=True, exist_ok=True)
        neko_config.config_path().write_text("[1, 2, 3]", encoding="utf-8")

        config = neko_config.cargar_config()

        self.assertIsNone(config["printer_port"])

    def test_config_parcial_se_completa_con_defaults(self):
        neko_config.config_dir().mkdir(parents=True, exist_ok=True)
        neko_config.config_path().write_text('{"printer_port": "COM9"}', encoding="utf-8")

        config = neko_config.cargar_config()

        self.assertEqual(config["printer_port"], "COM9")
        self.assertEqual(config["baudrate"], neko_config.DEFAULT_BAUDRATE)

    def test_tiene_impresora_configurada_false_sin_datos(self):
        self.assertFalse(neko_config.tiene_impresora_configurada(neko_config.cargar_config()))

    def test_url_base_nekopos_no_esta_vacia(self):
        self.assertTrue(neko_config.NEKOPOS_BASE_URL.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
