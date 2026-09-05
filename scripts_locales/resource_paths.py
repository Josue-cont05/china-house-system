"""
resource_paths.py

Localiza assets (logos ESC/POS) de forma identica en dos contextos:

- SOURCE: ejecutando `python neko_local.py` / `python script_*.py` desde
  el repositorio -> los assets viven junto a este archivo
  (scripts_locales/).
- FROZEN (PyInstaller): `sys.frozen` es True -> los assets (ver
  NekoLocal.spec, seccion `datas`) se localizan via `sys._MEIPASS`, la
  ubicacion OFICIAL de PyInstaller para datos empaquetados. Verificado
  con un build real: en onedir (PyInstaller >= 6) los datos NO quedan
  junto al .exe sino en una subcarpeta interna (`_internal/` en esta
  version) - asumir "junto al .exe" sin `_MEIPASS` rompe en produccion.
  `_MEIPASS` apunta al lugar correcto tanto en onedir como en onefile,
  sin depender de un detalle de estructura interna de una version dada
  de PyInstaller.

Ningun otro modulo debe calcular su propio BASE_DIR para assets: todos
deben pasar por `recurso()` para que source y frozen se comporten igual.
"""

import sys
from pathlib import Path


def es_frozen():
    return bool(getattr(sys, "frozen", False))


def directorio_base():
    if es_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # Defensivo: en teoria PyInstaller siempre fija _MEIPASS cuando
        # frozen es True; si por algun motivo no estuviera, se cae a la
        # carpeta del .exe en vez de fallar con AttributeError.
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def recurso(nombre_archivo):
    """Ruta absoluta a un asset (ej. 'mini_logo_neko_thermal_01.png')."""
    return directorio_base() / nombre_archivo
