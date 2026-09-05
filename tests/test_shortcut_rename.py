"""Tests de la migracion de nombre del acceso directo de Escritorio:
"INICIAR NEKO" -> "NekoWok Printer".

release_templates/INSTALAR_NEKO.bat y DESINSTALAR_NEKO.bat son scripts
de PowerShell/batch que corren en la PC del socio (sin Python): no se
pueden probar creando accesos directos reales en un Escritorio real
durante los tests (efecto secundario invasivo e innecesario). En su
lugar, estas pruebas verifican ESTATICAMENTE el contenido de los
templates: que el nombre nuevo se usa para crear/actualizar el acceso
directo, que el nombre viejo solo aparece dentro de la logica de
migracion seguida de una comprobacion de TargetPath (nunca un borrado
incondicional), y que la documentacion para el socio ya no menciona el
nombre viejo para el acceso directo.
"""

import re
import unittest
from pathlib import Path

RELEASE_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "release_templates"

NOMBRE_NUEVO = "NekoWok Printer"
NOMBRE_VIEJO = "INICIAR NEKO"


class InstalarNekoBatTest(unittest.TestCase):
    def setUp(self):
        self.texto = (RELEASE_TEMPLATES_DIR / "INSTALAR_NEKO.bat").read_text(encoding="utf-8")

    def test_crea_el_acceso_directo_con_el_nombre_nuevo(self):
        self.assertIn(f"{NOMBRE_NUEVO}.lnk", self.texto)

    def test_el_mensaje_final_menciona_el_nombre_nuevo_no_el_viejo(self):
        pie = self.texto.split("Instalacion terminada")[-1]
        self.assertIn(NOMBRE_NUEVO, pie)
        self.assertNotIn(NOMBRE_VIEJO, pie)

    def test_conserva_el_target_del_exe_portable(self):
        self.assertIn(r"%DEST%\NekoLocal.exe", self.texto)

    def test_menciona_el_nombre_viejo_solo_para_migrarlo_no_para_crearlo(self):
        # El nombre viejo debe aparecer UNICAMENTE en la ruta que se
        # comprueba/borra (migracion), nunca como el .lnk que se crea o
        # actualiza con CreateShortcut(...).Save().
        self.assertIn(f"{NOMBRE_VIEJO}.lnk", self.texto)
        # La linea de creacion real (la que termina en .Save()) debe
        # colgar del atajo NUEVO, no del viejo.
        bloque_creacion = re.search(r'\$s = \$shell\.CreateShortcut\((.*?)\);', self.texto)
        self.assertIsNotNone(bloque_creacion)
        self.assertIn("nuevo", bloque_creacion.group(1))

    def test_el_borrado_del_atajo_viejo_esta_condicionado_al_targetpath(self):
        # Requisito explicito de la mision: "no borrar accesos directos
        # ajenos". El Remove-Item del atajo viejo debe estar dentro de un
        # if que compare TargetPath contra nuestro exe, nunca suelto.
        indice_viejo = self.texto.index(f"{NOMBRE_VIEJO}.lnk")
        alrededor = self.texto[indice_viejo : indice_viejo + 400]
        self.assertIn("TargetPath", alrededor)
        self.assertIn("Remove-Item", alrededor)
        # El Remove-Item aparece DESPUES de la comprobacion de TargetPath,
        # no antes (si no, borraria incondicionalmente).
        self.assertLess(alrededor.index("TargetPath"), alrededor.index("Remove-Item"))

    def test_el_borrado_esta_protegido_con_try_catch(self):
        # Un .lnk viejo corrupto o inaccesible no debe tronar el instalador.
        indice_viejo = self.texto.index(f"{NOMBRE_VIEJO}.lnk")
        alrededor = self.texto[indice_viejo : indice_viejo + 400]
        self.assertIn("try", alrededor)
        self.assertIn("catch", alrededor)


class DesinstalarNekoBatTest(unittest.TestCase):
    def setUp(self):
        self.texto = (RELEASE_TEMPLATES_DIR / "DESINSTALAR_NEKO.bat").read_text(encoding="utf-8")

    def test_apunta_al_acceso_directo_con_el_nombre_nuevo(self):
        self.assertIn(f"{NOMBRE_NUEVO}.lnk", self.texto)

    def test_ya_no_referencia_el_nombre_viejo(self):
        self.assertNotIn(NOMBRE_VIEJO, self.texto)


class LeemePrimeroTest(unittest.TestCase):
    def setUp(self):
        self.texto = (RELEASE_TEMPLATES_DIR / "LEEME_PRIMERO.txt").read_text(encoding="utf-8")

    def test_instruye_abrir_el_acceso_directo_con_el_nombre_nuevo(self):
        self.assertIn(f'Abre "{NOMBRE_NUEVO}" desde el Escritorio', self.texto)

    def test_ya_no_instruye_abrir_el_nombre_viejo_desde_el_escritorio(self):
        self.assertNotIn(f'"{NOMBRE_VIEJO}" desde el Escritorio', self.texto)


if __name__ == "__main__":
    unittest.main()
