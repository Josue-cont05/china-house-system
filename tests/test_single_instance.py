"""Tests de single_instance.py (scripts_locales).

En Windows (donde corre este proyecto) usa el mutex real del sistema
operativo -- no hay nada que mockear para probar la garantia real: dos
objetos con el MISMO nombre en el mismo proceso de test ya demuestran que
el segundo `acquire()` falla, exactamente como pasaria con dos procesos.
"""

import sys
import unittest
import uuid
from pathlib import Path

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

from single_instance import SingleInstanceLock  # noqa: E402


def _nombre_unico():
    # Nombre unico por test para que no interfieran entre si ni con un
    # worker real que pudiera estar corriendo en la maquina.
    return f"NekoWok_Test_{uuid.uuid4().hex}"


@unittest.skipUnless(sys.platform == "win32", "El mutex real solo aplica en Windows")
class SingleInstanceLockWindowsTest(unittest.TestCase):
    def test_primer_lock_se_adquiere(self):
        lock = SingleInstanceLock(_nombre_unico())
        try:
            self.assertTrue(lock.acquire())
            self.assertTrue(lock.acquired)
        finally:
            lock.release()

    def test_segundo_lock_con_mismo_nombre_falla(self):
        nombre = _nombre_unico()
        primero = SingleInstanceLock(nombre)
        segundo = SingleInstanceLock(nombre)
        try:
            self.assertTrue(primero.acquire())
            self.assertFalse(segundo.acquire())
            self.assertFalse(segundo.acquired)
        finally:
            primero.release()
            segundo.release()

    def test_lock_liberado_permite_uno_nuevo(self):
        nombre = _nombre_unico()
        primero = SingleInstanceLock(nombre)
        self.assertTrue(primero.acquire())
        primero.release()

        segundo = SingleInstanceLock(nombre)
        try:
            self.assertTrue(segundo.acquire())
        finally:
            segundo.release()

    def test_context_manager_libera_al_salir(self):
        nombre = _nombre_unico()
        with SingleInstanceLock(nombre) as lock:
            self.assertTrue(lock.acquired)

        otro = SingleInstanceLock(nombre)
        try:
            self.assertTrue(otro.acquire())
        finally:
            otro.release()

    def test_nombres_distintos_no_interfieren(self):
        primero = SingleInstanceLock(_nombre_unico())
        segundo = SingleInstanceLock(_nombre_unico())
        try:
            self.assertTrue(primero.acquire())
            self.assertTrue(segundo.acquire())
        finally:
            primero.release()
            segundo.release()

    def test_release_sin_acquire_no_lanza(self):
        lock = SingleInstanceLock(_nombre_unico())
        lock.release()  # no debe lanzar aunque nunca se haya adquirido


if __name__ == "__main__":
    unittest.main()
