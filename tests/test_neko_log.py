"""Tests de neko_log.py (scripts_locales): logger de diagnostico en
%LOCALAPPDATA%\\NekoWok\\logs\\, sin tocar la carpeta real de esta maquina.
"""

import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import neko_config  # noqa: E402
import neko_log  # noqa: E402


class NekoLogTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            neko_config, "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        # Cerrar los handlers de archivo ANTES de borrar el tmpdir: en
        # Windows no se puede eliminar un archivo todavia abierto.
        for nombre in list(logging.root.manager.loggerDict):
            if nombre.startswith("nekowok.test_"):
                logger = logging.getLogger(nombre)
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)
                del logging.root.manager.loggerDict[nombre]
        self._tmpdir.cleanup()

    def test_crea_el_archivo_de_log_en_logs_dir(self):
        logger = neko_log.obtener_logger("test_crea_archivo")
        logger.info("hola")
        for handler in logger.handlers:
            handler.flush()

        archivo = neko_config.logs_dir() / "test_crea_archivo.log"
        self.assertTrue(archivo.exists())
        self.assertIn("hola", archivo.read_text(encoding="utf-8"))

    def test_mismo_nombre_no_duplica_handlers(self):
        primero = neko_log.obtener_logger("test_no_duplica")
        segundo = neko_log.obtener_logger("test_no_duplica")

        self.assertIs(primero, segundo)
        self.assertEqual(len(primero.handlers), 1)

    def test_no_propaga_al_logger_raiz(self):
        logger = neko_log.obtener_logger("test_no_propaga")
        self.assertFalse(logger.propagate)

    def test_no_lanza_si_no_se_puede_crear_el_directorio(self):
        with mock.patch.object(
            neko_config, "logs_dir", return_value=Path(self._tmpdir.name) / "no\0valido"
        ):
            logger = neko_log.obtener_logger("test_dir_invalido")
        # No debe lanzar; debe seguir siendo un logger usable.
        logger.info("esto no debe romper nada")


if __name__ == "__main__":
    unittest.main()
