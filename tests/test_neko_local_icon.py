"""Tests del icono de NekoWok Printer:

- build_icon.py genera un .ico multi-resolucion sin deformar el arte
  fuente (pura, con imagenes sinteticas: no depende de
  NekoWokPrinter.png ni de nada del Escritorio real).
- el asset versionado scripts_locales/neko_local.ico existe y tiene
  todos los tamanos requeridos.
- NekoLocal.spec referencia ese asset como icono del EXE.
- release_templates/INSTALAR_NEKO.bat fija IconLocation al icono
  EMBEBIDO en NekoLocal.exe (nunca a una ruta del Escritorio ni al PNG
  origen): la instalacion final no depende de NekoWokPrinter.png.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_LOCALES_DIR = ROOT_DIR / "scripts_locales"
RELEASE_TEMPLATES_DIR = ROOT_DIR / "release_templates"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import build_icon  # noqa: E402

TAMANOS_REQUERIDOS = {16, 24, 32, 48, 64, 128, 256}


def _png_sintetico(ancho, alto, color=(20, 30, 40, 255)):
    return Image.new("RGBA", (ancho, alto), color)


class GenerarIcoTest(unittest.TestCase):
    def test_genera_todos_los_tamanos_requeridos(self):
        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "fuente.png"
            _png_sintetico(400, 400).save(origen)
            destino = Path(tmp) / "salida.ico"

            build_icon.generar_ico(origen, destino, recorte=None)

            with Image.open(destino) as ico:
                tamanos = {t[0] for t in ico.info["sizes"]}
            self.assertEqual(tamanos, TAMANOS_REQUERIDOS)

    def test_imagen_no_cuadrada_no_se_deforma_se_rellena(self):
        # 400x200 (2:1): si se deformara, un pixel de color en el borde
        # horizontal terminaria desplazado; con padding transparente el
        # contenido original mantiene su proporcion 2:1 centrado.
        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "fuente.png"
            imagen = _png_sintetico(400, 200, color=(255, 0, 0, 255))
            imagen.save(origen)
            destino = Path(tmp) / "salida.ico"

            build_icon.generar_ico(origen, destino, recorte=None, tamanos=(64,))

            with Image.open(destino) as ico:
                ico.size = (64, 64)
                ico.load()
                # El contenido rojo debe ocupar la franja central
                # (proporcional), y las esquinas superior/inferior deben
                # quedar transparentes (padding), no rojas ni deformadas.
                esquina_superior = ico.getpixel((5, 5))
                centro = ico.getpixel((32, 32))
            self.assertEqual(esquina_superior[3], 0)  # alpha 0 = transparente
            self.assertEqual(centro[:3], (255, 0, 0))

    def test_preserva_transparencia_del_origen(self):
        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "fuente.png"
            imagen = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
            imagen.paste((10, 20, 30, 255), (25, 25, 75, 75))
            imagen.save(origen)
            destino = Path(tmp) / "salida.ico"

            build_icon.generar_ico(origen, destino, recorte=None, tamanos=(64,))

            with Image.open(destino) as ico:
                ico.size = (64, 64)
                ico.load()
                esquina = ico.getpixel((2, 2))
            self.assertEqual(esquina[3], 0)

    def test_imagen_ya_cuadrada_no_se_le_agrega_padding_innecesario(self):
        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "fuente.png"
            _png_sintetico(300, 300, color=(0, 255, 0, 255)).save(origen)
            destino = Path(tmp) / "salida.ico"

            build_icon.generar_ico(origen, destino, recorte=None, tamanos=(64,))

            with Image.open(destino) as ico:
                ico.size = (64, 64)
                ico.load()
                esquina = ico.getpixel((1, 1))
            # Sin padding: la esquina tambien deberia ser del color
            # original (la imagen cubre todo el lienzo), no transparente.
            self.assertEqual(esquina[3], 255)

    def test_recorte_se_aplica_antes_de_cuadrar(self):
        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "fuente.png"
            imagen = Image.new("RGBA", (200, 200), (0, 0, 0, 255))
            imagen.paste((255, 255, 0, 255), (50, 50, 150, 150))
            imagen.save(origen)
            destino = Path(tmp) / "salida.ico"

            build_icon.generar_ico(origen, destino, recorte=(50, 50, 150, 150), tamanos=(64,))

            with Image.open(destino) as ico:
                ico.size = (64, 64)
                ico.load()
                centro = ico.getpixel((32, 32))
            self.assertEqual(centro[:3], (255, 255, 0))


class AssetVersionadoTest(unittest.TestCase):
    """El .ico final debe vivir en scripts_locales/ (junto a los otros
    assets versionados de Neko Local), no depender del PNG del
    Escritorio, y tener todos los tamanos requeridos por la mision."""

    def test_neko_local_ico_existe_en_scripts_locales(self):
        ruta = SCRIPTS_LOCALES_DIR / "neko_local.ico"
        self.assertTrue(ruta.exists(), f"Falta {ruta}")

    def test_neko_local_ico_tiene_todos_los_tamanos_requeridos(self):
        ruta = SCRIPTS_LOCALES_DIR / "neko_local.ico"
        with Image.open(ruta) as ico:
            tamanos = {t[0] for t in ico.info["sizes"]}
        self.assertEqual(tamanos, TAMANOS_REQUERIDOS)

    def test_ningun_archivo_versionado_referencia_el_png_del_escritorio(self):
        # La instalacion final no puede depender de NekoWokPrinter.png:
        # tras generar neko_local.ico, ningun script/spec/test debe
        # seguir apuntando al PNG original (solo build_icon.py lo
        # menciona en su propio docstring explicativo, lo cual es
        # aceptable: es documentacion de como se genero, no una
        # dependencia en tiempo de instalacion/ejecucion).
        candidatos = list(SCRIPTS_LOCALES_DIR.glob("*.py")) + [
            ROOT_DIR / "NekoLocal.spec",
            RELEASE_TEMPLATES_DIR / "INSTALAR_NEKO.bat",
            RELEASE_TEMPLATES_DIR / "DESINSTALAR_NEKO.bat",
        ]
        for archivo in candidatos:
            texto = archivo.read_text(encoding="utf-8")
            self.assertNotIn("NekoWokPrinter.png", texto, f"{archivo} referencia el PNG del Escritorio")


class SpecReferenciaIconoTest(unittest.TestCase):
    def setUp(self):
        self.texto = (ROOT_DIR / "NekoLocal.spec").read_text(encoding="utf-8")

    def test_spec_referencia_neko_local_ico_como_icono_del_exe(self):
        self.assertRegex(self.texto, r'icon\s*=.*neko_local\.ico')


class InstaladorIconoTest(unittest.TestCase):
    def setUp(self):
        self.texto = (RELEASE_TEMPLATES_DIR / "INSTALAR_NEKO.bat").read_text(encoding="utf-8")

    def test_fija_iconlocation_al_exe_embebido_no_a_una_ruta_externa(self):
        self.assertIn("IconLocation", self.texto)
        self.assertIn("$destino,0", self.texto)

    def test_iconlocation_no_referencia_el_png_ni_el_escritorio_del_desarrollador(self):
        self.assertNotIn("NekoWokPrinter.png", self.texto)
        self.assertNotIn(".ico", self.texto)  # no depende de un .ico externo instalado aparte

    def test_shortcut_sigue_llamandose_nekowok_printer_con_target_correcto(self):
        self.assertIn("NekoWok Printer.lnk", self.texto)
        self.assertIn(r"%DEST%\NekoLocal.exe", self.texto)


if __name__ == "__main__":
    unittest.main()
