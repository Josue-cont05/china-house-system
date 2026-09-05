"""
neko_config.py

Configuracion local de Neko Local (launcher + worker de cocina), UNICA por
computadora: nunca se guarda en el repositorio ni se sube a git.

Ubicacion:
    %LOCALAPPDATA%\\NekoWok\\config.json           (config, unica por PC)
    %LOCALAPPDATA%\\NekoWok\\state\\*.txt          (dedup persistente)
    %LOCALAPPDATA%\\NekoWok\\logs\\*.log           (diagnostico)
Fallback si LOCALAPPDATA no existe (ej. entorno de pruebas):
    ~/.nekowok/...

Esta carpeta sobrevive actualizaciones/reinstalaciones de la app (que
viven en otra ubicacion, ver INSTALAR_NEKO.bat): actualizar Neko Local
NUNCA debe perder config ni el historial de deduplicacion.

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


def state_dir():
    """Carpeta de estado persistente (dedup de comandas/recibos). Separada
    de config_dir() en un subdirectorio propio para poder crecer sin
    ensuciar la raiz (logs, futuros estados). No la crea."""
    return config_dir() / "state"


def logs_dir():
    """Carpeta de logs de diagnostico. No la crea."""
    return config_dir() / "logs"


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


def _leer_eventos(ruta):
    if not ruta or not Path(ruta).exists():
        return set()
    try:
        return {
            linea.strip()
            for linea in Path(ruta).read_text(encoding="utf-8").splitlines()
            if linea.strip()
        }
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo leer {ruta} durante la migracion de dedup: {e}")
        return set()


def migrar_dedup_legacy(nombre_archivo, ruta_legacy=None):
    """Asegura que exista `state_dir()/nombre_archivo` con TODOS los
    eventos de deduplicacion ya conocidos, uniendo lo que ya hubiera en la
    ubicacion nueva con lo que exista en `ruta_legacy` (la ubicacion
    anterior, junto al script, de antes de esta migracion).

    Idempotente y nunca destructivo: es una UNION de eventos, nunca un
    reemplazo -- correrla muchas veces, en cualquier orden, con cualquier
    combinacion de archivos presentes/ausentes, jamas hace perder un
    evento ya conocido (eso evitaria una reimpresion fisica accidental).
    Si no hace falta escribir nada (la union ya coincide con lo que habia
    en destino), no reescribe el archivo.

    Devuelve la Path del archivo nuevo (ya migrado), para usar como
    ARCHIVO_IMPRESAS/ARCHIVO_FACTURAS a partir de ahi.
    """
    destino = state_dir() / nombre_archivo
    existentes_destino = _leer_eventos(destino) if destino.exists() else None
    eventos = set(existentes_destino or set())
    eventos |= _leer_eventos(ruta_legacy)

    if existentes_destino is not None and eventos == existentes_destino:
        return destino  # nada nuevo que migrar, no tocar el archivo

    state_dir().mkdir(parents=True, exist_ok=True)
    contenido = "".join(f"{evento}\n" for evento in sorted(eventos))
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text(contenido, encoding="utf-8")
    tmp.replace(destino)
    return destino
