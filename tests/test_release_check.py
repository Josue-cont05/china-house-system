"""Tests de release_check.py (scripts_locales): validador de contenido
prohibido en el paquete entregable de Neko Local. No requiere un build
real de PyInstaller para la mayoria de los casos (archivo_prohibido() es
pura); validar_carpeta() se prueba contra una carpeta temporal.
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import release_check  # noqa: E402


class ArchivoProhibidoTest(unittest.TestCase):
    def test_env_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido(".env"))

    def test_git_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido(".git/config"))

    def test_worktrees_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido(".worktrees/algo/x.py"))

    def test_pycache_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("scripts_locales/__pycache__/x.pyc"))

    def test_pyc_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("modulo.pyc"))

    def test_sqlite_y_db_prohibidos(self):
        self.assertTrue(release_check.archivo_prohibido("china_house.db"))
        self.assertTrue(release_check.archivo_prohibido("datos.sqlite3"))

    def test_china_house_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("china_house_test.db"))

    def test_web_app_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("web_app.py"))

    def test_tests_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("tests/test_algo.py"))
        self.assertTrue(release_check.archivo_prohibido("test_suelto.py"))

    def test_config_real_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("config.json"))
        self.assertTrue(release_check.archivo_prohibido("NekoWok/config.json"))

    def test_dedup_real_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("comandas_impresas.txt"))
        self.assertTrue(release_check.archivo_prohibido("facturas_impresas.txt"))
        self.assertTrue(release_check.archivo_prohibido("pendientes_ack.txt"))

    def test_tasa_cache_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("tasa_cache.txt"))

    def test_secreto_o_token_prohibido(self):
        self.assertTrue(release_check.archivo_prohibido("api_secret.txt"))
        self.assertTrue(release_check.archivo_prohibido("auth_token.json"))

    def test_backslash_se_normaliza_igual_que_forward_slash(self):
        self.assertTrue(release_check.archivo_prohibido("tests\\test_algo.py"))

    def test_leeme_primero_es_excepcion_explicita(self):
        self.assertFalse(release_check.archivo_prohibido("LEEME_PRIMERO.txt"))

    # "pueden existir archivos con nombres parecidos que no sean DB":
    # nombres legitimos del release que NO deben dispararse por parecido.
    def test_archivos_legitimos_no_se_marcan(self):
        legitimos = [
            "NekoLocal.exe",
            "_internal/base_library.zip",
            "_internal/logo_neko_thermal.png",
            "_internal/mini_logo_neko_thermal_01.png",
            "INSTALAR_NEKO.bat",
            "DESINSTALAR_NEKO.bat",
            "LEEME_PRIMERO.txt",
            "_internal/comanda_presentacion.pyd",
        ]
        for ruta in legitimos:
            with self.subTest(ruta=ruta):
                self.assertFalse(release_check.archivo_prohibido(ruta))

    def test_nombre_parecido_a_prohibido_pero_no_exacto_no_bloquea_indebidamente(self):
        # "config.json" esta prohibido, pero un nombre que solo CONTIENE
        # "config" (no es exactamente config.json) es codigo legitimo
        # del propio proyecto (neko_config.py) y no debe bloquearse.
        self.assertFalse(release_check.archivo_prohibido("_internal/neko_config.pyd"))


class ValidarCarpetaTest(unittest.TestCase):
    def test_carpeta_inexistente_no_lanza_y_devuelve_vacio(self):
        self.assertEqual(release_check.validar_carpeta("/ruta/que/no/existe/nunca"), [])

    def test_carpeta_limpia_no_reporta_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "NekoLocal.exe").write_text("stub")
            (Path(tmp) / "LEEME_PRIMERO.txt").write_text("hola")
            self.assertEqual(release_check.validar_carpeta(tmp), [])

    def test_detecta_archivo_prohibido_anidado(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "NekoLocal.exe").write_text("stub")
            sub = Path(tmp) / "_internal" / "tests"
            sub.mkdir(parents=True)
            (sub / "test_algo.py").write_text("x")

            problemas = release_check.validar_carpeta(tmp)

        self.assertEqual(len(problemas), 1)
        self.assertIn("test_algo.py", problemas[0])

    def test_reporta_config_real_copiada_por_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "config.json").write_text('{"printer_port": "COM6"}')

            problemas = release_check.validar_carpeta(tmp)

        self.assertEqual(problemas, ["config.json"])

    def test_no_borra_nada_solo_reporta(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / "china_house.db"
            archivo.write_text("dato")

            release_check.validar_carpeta(tmp)

            self.assertTrue(archivo.exists())


if __name__ == "__main__":
    unittest.main()
