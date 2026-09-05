"""
release_check.py

Verifica que una carpeta candidata a release de Neko Local NO contenga
nada que nunca deberia llegar a la PC de un socio: codigo/datos del
backend NekoPOS, bases de datos, credenciales, o config/estado REALES de
esta maquina de desarrollo.

Puro (no borra nada): solo reporta rutas problematicas. Quien construye
el release (BUILD_NEKO_LOCAL.bat) decide que hacer si hay problemas -
normalmente, detener el build.
"""

import re
from pathlib import Path

# Patrones de ruta (relativa a la raiz de la carpeta evaluada,
# comparados en minusculas, con "/" como separador) que NUNCA deben
# aparecer en un release de Neko Local.
_PATRONES_PROHIBIDOS = [
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)\.git(/|$)"),
    re.compile(r"(^|/)\.worktrees(/|$)"),
    re.compile(r"(^|/)__pycache__(/|$)"),
    re.compile(r"\.pyc$"),
    re.compile(r"\.sqlite3?$"),
    re.compile(r"\.db$"),
    re.compile(r"(^|/)china_house"),
    re.compile(r"(^|/)web_app\.py$"),
    re.compile(r"(^|/)tests(/|$)"),
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"(^|/)config\.json$"),
    re.compile(r"(^|/)comandas_impresas\.txt$"),
    re.compile(r"(^|/)facturas_impresas\.txt$"),
    re.compile(r"(^|/)pendientes_ack\.txt$"),
    re.compile(r"(^|/)tasa_cache\.txt$"),
    re.compile(r"(^|/)\.credentials?(/|$)"),
    re.compile(r"secret"),
    re.compile(r"token"),
]

# Excepciones explicitas: rutas que coincidirian con algun patron de
# arriba por casualidad pero SI deben ir en el release (documentacion
# legitima, nunca datos ni codigo). Comparadas igual que los patrones.
_EXCEPCIONES = {
    "leeme_primero.txt",
}


def archivo_prohibido(ruta_relativa):
    """True si `ruta_relativa` (string, acepta '/' o '\\\\') no deberia
    estar en un release de Neko Local. Pura: no toca disco, facil de
    testear con nombres de archivo de ejemplo sin necesitar un build."""
    texto = str(ruta_relativa).replace("\\", "/").lower()
    if texto in _EXCEPCIONES:
        return False
    return any(patron.search(texto) for patron in _PATRONES_PROHIBIDOS)


def validar_carpeta(carpeta):
    """Recorre `carpeta` recursivamente y devuelve la lista de rutas
    relativas problematicas encontradas (lista vacia = todo bien)."""
    carpeta = Path(carpeta)
    problemas = []
    if not carpeta.exists():
        return problemas
    for ruta in carpeta.rglob("*"):
        if ruta.is_dir():
            continue
        relativa = ruta.relative_to(carpeta).as_posix()
        if archivo_prohibido(relativa):
            problemas.append(relativa)
    return problemas
