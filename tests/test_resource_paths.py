"""Tests de resource_paths.py (scripts_locales): localizacion de assets
identica en SOURCE y FROZEN (PyInstaller), sin necesitar un build real.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import resource_paths  # noqa: E402


class EsFrozenTest(unittest.TestCase):
    def test_false_en_source(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertFalse(resource_paths.es_frozen())

    def test_true_cuando_pyinstaller_lo_fija(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertTrue(resource_paths.es_frozen())

    def test_false_si_el_atributo_no_existe(self):
        # sys.frozen normalmente ni existe fuera de un build PyInstaller.
        if hasattr(sys, "frozen"):
            with mock.patch.object(sys, "frozen", False, create=True):
                self.assertFalse(resource_paths.es_frozen())
        else:
            self.assertFalse(resource_paths.es_frozen())


class DirectorioBaseTest(unittest.TestCase):
    def test_source_es_la_carpeta_de_scripts_locales(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(resource_paths.directorio_base(), SCRIPTS_LOCALES_DIR)

    def test_frozen_usa_meipass_no_la_carpeta_del_exe(self):
        # Regresion de un bug real: en PyInstaller >= 6 onedir, los datos
        # NO quedan junto al .exe sino en una subcarpeta interna
        # (_internal/ en la version usada) - _MEIPASS es la unica fuente
        # de verdad correcta en ambos casos (onedir y onefile).
        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.object(sys, "_MEIPASS", r"C:\NekoLocal\_internal", create=True):
                with mock.patch.object(sys, "executable", r"C:\NekoLocal\NekoLocal.exe"):
                    base = resource_paths.directorio_base()

        self.assertEqual(base, Path(r"C:\NekoLocal\_internal"))
        self.assertNotEqual(base, Path(r"C:\NekoLocal"))

    def test_frozen_sin_meipass_cae_a_carpeta_del_exe(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.object(sys, "executable", r"C:\NekoLocal\NekoLocal.exe"):
                if hasattr(sys, "_MEIPASS"):
                    with mock.patch.object(sys, "_MEIPASS", None, create=True):
                        base = resource_paths.directorio_base()
                else:
                    base = resource_paths.directorio_base()

        self.assertEqual(base, Path(r"C:\NekoLocal"))


class RecursoTest(unittest.TestCase):
    def test_recurso_source_apunta_a_un_archivo_real(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            ruta = resource_paths.recurso("mini_logo_neko_thermal_01.png")
        self.assertTrue(ruta.exists())

    def test_recurso_frozen_usa_meipass(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.object(sys, "_MEIPASS", r"C:\NekoLocal\_internal", create=True):
                ruta = resource_paths.recurso("logo_neko_thermal.png")
        self.assertEqual(ruta, Path(r"C:\NekoLocal\_internal\logo_neko_thermal.png"))

    def test_ambos_logos_existen_en_source(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertTrue(resource_paths.recurso("mini_logo_neko_thermal_01.png").exists())
            self.assertTrue(resource_paths.recurso("logo_neko_thermal.png").exists())


if __name__ == "__main__":
    unittest.main()
