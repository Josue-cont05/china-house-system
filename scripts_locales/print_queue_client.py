"""
print_queue_client.py

Cliente HTTP de la cola central de impresion (/api/printing/*). No
decide dinero, formato ni logica de negocio: solo llama al backend y
devuelve respuestas ya interpretadas. Nunca lanza por errores de red/
timeout/JSON invalido -- se degrada a None/False, igual que el resto de
scripts_locales (ver script_factura.py/script_comanda_cocina.py)."""

import requests

import neko_config

URL_STATUS = f"{neko_config.NEKOPOS_BASE_URL}/api/printing/status"
URL_CLAIM = f"{neko_config.NEKOPOS_BASE_URL}/api/printing/claim"
URL_BASE_JOB = f"{neko_config.NEKOPOS_BASE_URL}/api/printing"


def consultar_status(roles, timeout=5, sesion=None):
    """{"pendientes": N, "por_rol": {...}} o None si no se pudo
    consultar (red caida, error del servidor, etc.)."""
    if not roles:
        return {"pendientes": 0, "por_rol": {}}
    peticion = sesion or requests
    try:
        respuesta = peticion.get(URL_STATUS, params={"roles": ",".join(roles)}, timeout=timeout)
        if respuesta.status_code != 200:
            return None
        datos = respuesta.json()
        if not isinstance(datos, dict) or not datos.get("ok"):
            return None
        return {"pendientes": datos.get("pendientes", 0), "por_rol": datos.get("por_rol", {})}
    except Exception:
        return None


def reclamar(station_id, roles, timeout=8, sesion=None):
    """El dict del job reclamado, o None si no hay nada elegible o
    hubo un error (nunca hace claim si `roles` esta vacio: eso
    significaria que la estacion no deberia estar consultando en
    absoluto)."""
    if not roles:
        return None
    peticion = sesion or requests
    try:
        respuesta = peticion.post(
            URL_CLAIM, json={"station_id": station_id, "roles": list(roles)}, timeout=timeout
        )
        if respuesta.status_code != 200:
            return None
        datos = respuesta.json()
        if not isinstance(datos, dict) or not datos.get("ok"):
            return None
        return datos.get("job")
    except Exception:
        return None


def confirmar(job_id, station_id, lease_token, timeout=8, sesion=None):
    """True si el backend confirmo el ACK (o ya estaba confirmado --
    idempotente). False si hay que reintentar mas tarde."""
    peticion = sesion or requests
    try:
        respuesta = peticion.post(
            f"{URL_BASE_JOB}/{job_id}/ack",
            json={"station_id": station_id, "lease_token": lease_token},
            timeout=timeout,
        )
        if respuesta.status_code != 200:
            return False
        datos = respuesta.json()
        return bool(isinstance(datos, dict) and datos.get("ok"))
    except Exception:
        return False


def reportar_fallo(job_id, station_id, lease_token, error, timeout=8, sesion=None):
    """True si el backend libero el job (vuelve a PENDING). El error se
    recorta antes de enviarlo: nunca un stacktrace completo."""
    peticion = sesion or requests
    try:
        respuesta = peticion.post(
            f"{URL_BASE_JOB}/{job_id}/fail",
            json={"station_id": station_id, "lease_token": lease_token, "error": str(error)[:200]},
            timeout=timeout,
        )
        if respuesta.status_code != 200:
            return False
        datos = respuesta.json()
        return bool(isinstance(datos, dict) and datos.get("ok"))
    except Exception:
        return False
