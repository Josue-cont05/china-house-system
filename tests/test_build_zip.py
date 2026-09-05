"""Tests de build_zip.py (raiz del repo): empaquetado del release con
verificacion de integridad. No requiere un build real de PyInstaller.
"""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import build_zip  # noqa: E402


class EmpaquetarTest(unittest.TestCase):
    def test_zip_contiene_todos_los_archivos_incluyendo_subcarpetas(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            (release / "_internal").mkdir(parents=True)
            (release / "NekoLocal.exe").write_text("stub-exe")
            (release / "LEEME_PRIMERO.txt").write_text("hola")
            (release / "_internal" / "base_library.zip").write_bytes(b"fake-zip-bytes")
            zip_destino = Path(tmp) / "out.zip"

            ok = build_zip.empaquetar(release, zip_destino, intentos=1, espera_seg=0)

            self.assertTrue(ok)
            with zipfile.ZipFile(zip_destino) as zf:
                nombres = set(zf.namelist())
            self.assertEqual(
                nombres,
                {"NekoLocal.exe", "LEEME_PRIMERO.txt", "_internal/base_library.zip"},
            )

    def test_carpeta_vacia_produce_zip_vacio_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            release.mkdir()
            zip_destino = Path(tmp) / "out.zip"

            ok = build_zip.empaquetar(release, zip_destino, intentos=1, espera_seg=0)

            self.assertTrue(ok)
            with zipfile.ZipFile(zip_destino) as zf:
                self.assertEqual(zf.namelist(), [])

    def test_reintenta_si_zipfile_lanza_oserror_y_luego_funciona(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            release.mkdir()
            (release / "a.txt").write_text("x")
            zip_destino = Path(tmp) / "out.zip"

            llamadas = {"n": 0}
            zip_real = zipfile.ZipFile

            def zip_con_fallo_en_primer_intento(*args, **kwargs):
                llamadas["n"] += 1
                es_escritura = len(args) >= 2 and args[1] == "w"
                if llamadas["n"] == 1 and es_escritura:
                    raise OSError("archivo bloqueado")
                return zip_real(*args, **kwargs)

            with mock.patch("build_zip.zipfile.ZipFile", side_effect=zip_con_fallo_en_primer_intento):
                ok = build_zip.empaquetar(release, zip_destino, intentos=3, espera_seg=0)

            self.assertTrue(ok)
            self.assertGreaterEqual(llamadas["n"], 2)

    def test_zip_incompleto_agota_intentos_y_devuelve_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            release.mkdir()
            (release / "a.txt").write_text("x")
            (release / "b.txt").write_text("y")
            zip_destino = Path(tmp) / "out.zip"

            zip_real = zipfile.ZipFile

            def zip_lectura_incompleta(*args, **kwargs):
                es_escritura = len(args) >= 2 and args[1] == "w"
                if es_escritura:
                    return zip_real(*args, **kwargs)
                zf = mock.MagicMock()
                zf.__enter__.return_value = zf
                zf.__exit__.return_value = False
                zf.namelist.return_value = ["a.txt"]
                return zf

            with mock.patch("build_zip.zipfile.ZipFile", side_effect=zip_lectura_incompleta):
                ok = build_zip.empaquetar(release, zip_destino, intentos=2, espera_seg=0)

            self.assertFalse(ok)

    def test_main_exit_code_1_si_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("build_zip.empaquetar", return_value=False):
                with mock.patch.object(sys, "argv", ["build_zip.py", tmp, str(Path(tmp) / "o.zip")]):
                    with self.assertRaises(SystemExit) as ctx:
                        build_zip.main_para_test()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
