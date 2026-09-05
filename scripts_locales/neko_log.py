"""
neko_log.py

Log de diagnostico de Neko Local, en %LOCALAPPDATA%\\NekoWok\\logs\\.
No registra secretos (este sistema no maneja ninguno: solo puerto,
fingerprint de hardware no sensible, y eventos de impresion/arranque).
Rotacion simple por tamano para no crecer indefinidamente.

Uso:
    import neko_log
    log = neko_log.obtener_logger("neko_local")   # o "cocina" / "recibos"
    log.info("Neko Local %s iniciado (frozen=%s)", version, frozen)
"""

import logging
import logging.handlers

import neko_config

_MAX_BYTES = 512 * 1024  # 512 KB por archivo antes de rotar
_BACKUPS = 3


def obtener_logger(nombre):
    """Logger que escribe en %LOCALAPPDATA%\\NekoWok\\logs\\<nombre>.log
    (rota a <nombre>.log.1, .2, .3). Si por algun motivo no se puede
    escribir en disco (permiso, disco lleno), NO lanza: registra la
    advertencia por consola y sigue devolviendo un logger utilizable
    (sin handler de archivo) para no romper al llamador.
    """
    logger = logging.getLogger(f"nekowok.{nombre}")
    if logger.handlers:
        return logger  # ya configurado en esta misma ejecucion

    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        neko_config.logs_dir().mkdir(parents=True, exist_ok=True)
        archivo = neko_config.logs_dir() / f"{nombre}.log"
        handler = logging.handlers.RotatingFileHandler(
            archivo, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo abrir el log de '{nombre}': {e}")

    return logger
