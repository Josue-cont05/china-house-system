"""
neko_config.py

Configuracion local de Neko Local (launcher + worker de cocina), UNICA por
computadora: nunca se guarda en el repositorio ni se sube a git.

Ubicacion:
    %LOCALAPPDATA%\\NekoWok\\config.json   (Windows normal)
Fallback si LOCALAPPDATA no existe (ej. entorno de pruebas):
    ~/.nekowok/config.json

Tambien centraliza la URL base de NekoPOS para que scripts_locales no la
repita en cada archivo (script_factura.py queda fuera por ahora: es del
Bloque de facturas, no se toca en este bloque).
"""

import json
import os
import shutil
from pathlib import Path

NEKOPOS_BASE_URL = "https://neko-wok-system.onrender.com"

_APP_DIR_NAME = "NekoWok"
_CONFIG_FILE_NAME = "config.json"

DEFAULT_BAUDRATE = 9600


def config_dir():
    """Directorio de configuracion de esta computadora. No lo crea."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / _APP_DIR_NAME
    # Fallback seguro si LOCALAPPDATA no existe (SO distinto, entorno de
    # pruebas, usuario con perfil atipico): carpeta oculta en el home.
    return Path.home() / ".nekowok"


def config_path():
    return config_dir() / _CONFIG_FILE_NAME


def _config_por_defecto():
    return {
        "printer_port": None,
        "baudrate": DEFAULT_BAUDRATE,
        "printer_fingerprint": None,
    }


def cargar_config():
    """Carga la configuracion local. Nunca lanza: si el archivo no existe
    devuelve los valores por defecto; si esta corrupto, lo respalda
    (config.json.bak) y devuelve los valores por defecto en vez de tronar."""
    ruta = config_path()
    if not ruta.exists():
        return _config_por_defecto()

    try:
        contenido = ruta.read_text(encoding="utf-8")
        datos = json.loads(contenido)
        if not isinstance(datos, dict):
            raise ValueError("El config.json no contiene un objeto JSON")
    except Exception as e:
        print(f"ADVERTENCIA: config.json invalido ({e}). Se respalda y se reinicia.")
        _respaldar_config_corrupta(ruta)
        return _config_por_defecto()

    config = _config_por_defecto()
    config.update(datos)
    return config


def _respaldar_config_corrupta(ruta):
    try:
        respaldo = ruta.with_suffix(ruta.suffix + ".bak")
        shutil.copy2(ruta, respaldo)
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo respaldar config.json corrupto: {e}")


def guardar_config(config):
    """Guarda la configuracion local, creando el directorio si hace falta.
    No guarda secretos: solo puerto, baudrate y huella de la impresora."""
    directorio = config_dir()
    directorio.mkdir(parents=True, exist_ok=True)

    ruta = config_path()
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)


def tiene_impresora_configurada(config):
    return bool(config.get("printer_port")) and bool(config.get("printer_fingerprint"))
