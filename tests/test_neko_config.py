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

    def test_state_dir_y_logs_dir_son_subcarpetas_de_config_dir(self):
        self.assertEqual(neko_config.state_dir(), neko_config.config_dir() / "state")
        self.assertEqual(neko_config.logs_dir(), neko_config.config_dir() / "logs")


class MigrarDedupLegacyTest(unittest.TestCase):
    """Migracion de dedup legacy (comandas_impresas.txt / facturas_impresas.txt
    junto al script) hacia %LOCALAPPDATA%\\NekoWok\\state\\. Nunca debe
    perder un evento ya conocido, sin importar el orden ni la combinacion
    de archivos presentes."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            neko_config, "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()
        self._legacy_dir = Path(self._tmpdir.name) / "legacy_scripts_locales"
        self._legacy_dir.mkdir()
        self._ruta_legacy = self._legacy_dir / "comandas_impresas.txt"

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def _eventos(self, ruta):
        return set(ruta.read_text(encoding="utf-8").splitlines()) if ruta.exists() else set()

    # 1. archivo nuevo ya existe, sin legacy -> se mantiene
    def test_solo_nuevo_existente_se_mantiene(self):
        nuevo = neko_config.state_dir() / "comandas_impresas.txt"
        neko_config.state_dir().mkdir(parents=True)
        nuevo.write_text("comanda-1-base\n", encoding="utf-8")

        resultado = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)

        self.assertEqual(resultado, nuevo)
        self.assertEqual(self._eventos(nuevo), {"comanda-1-base"})

    # 2. solo legacy -> se copia integro al nuevo
    def test_solo_legacy_se_copia_al_nuevo(self):
        self._ruta_legacy.write_text("comanda-1-base\ncomanda-2-base\n", encoding="utf-8")

        resultado = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)

        self.assertEqual(self._eventos(resultado), {"comanda-1-base", "comanda-2-base"})

    # 3. ambos existen con eventos distintos -> union, nunca reemplazo
    def test_ambos_existentes_se_unen_sin_perder_eventos(self):
        neko_config.state_dir().mkdir(parents=True)
        nuevo = neko_config.state_dir() / "comandas_impresas.txt"
        nuevo.write_text("comanda-1-base\n", encoding="utf-8")
        self._ruta_legacy.write_text("comanda-2-base\n", encoding="utf-8")

        resultado = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)

        self.assertEqual(self._eventos(resultado), {"comanda-1-base", "comanda-2-base"})

    # 4. ninguno existe -> arranque normal, archivo vacio creado
    def test_ninguno_existe_crea_archivo_vacio(self):
        resultado = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)

        self.assertTrue(resultado.exists())
        self.assertEqual(self._eventos(resultado), set())

    # 5. idempotencia: correrla dos veces da el mismo resultado
    def test_es_idempotente(self):
        self._ruta_legacy.write_text("comanda-1-base\n", encoding="utf-8")

        primera = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)
        eventos_primera = self._eventos(primera)
        segunda = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)

        self.assertEqual(primera, segunda)
        self.assertEqual(self._eventos(segunda), eventos_primera)

    # 6. legacy inexistente (ruta None) no rompe nada
    def test_ruta_legacy_none_no_rompe(self):
        resultado = neko_config.migrar_dedup_legacy("comandas_impresas.txt", None)
        self.assertTrue(resultado.exists())

    # 7. tras migrar, agregar un nuevo evento y volver a migrar no lo pierde
    def test_evento_nuevo_tras_migracion_persiste_en_siguiente_migracion(self):
        self._ruta_legacy.write_text("comanda-1-base\n", encoding="utf-8")
        nuevo = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)

        with nuevo.open("a", encoding="utf-8") as f:
            f.write("comanda-2-base\n")

        resultado = neko_config.migrar_dedup_legacy("comandas_impresas.txt", self._ruta_legacy)
        self.assertEqual(self._eventos(resultado), {"comanda-1-base", "comanda-2-base"})

    # 8. funciona igual para el archivo de recibos (mismo mecanismo)
    def test_funciona_igual_para_facturas_impresas(self):
        ruta_legacy_facturas = self._legacy_dir / "facturas_impresas.txt"
        ruta_legacy_facturas.write_text("1-base\n", encoding="utf-8")

        resultado = neko_config.migrar_dedup_legacy("facturas_impresas.txt", ruta_legacy_facturas)

        self.assertEqual(resultado.name, "facturas_impresas.txt")
        self.assertEqual(self._eventos(resultado), {"1-base"})


if __name__ == "__main__":
    unittest.main()
