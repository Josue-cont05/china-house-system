"""
print_queue_client.py

Cliente HTTP de la cola central de impresion (/api/printing/*). No
decide dinero, formato ni logica de negocio: solo llama al backend.

Dos estilos de funcion, a proposito:
- `consultar_status()`/`reclamar()`/`confirmar()`/`reportar_fallo()`:
  contrato simple (dict/None, bool) para el uso normal del dispatcher/
  GUI, igual que antes.
- `evaluar_status()`/`evaluar_claim()`: version "diagnostica" que NUNCA
  oculta el motivo de un fallo (util para logs, --diagnostics, y el
  solucionador de problemas). Antes, un fallo de conectividad (incluida
  una respuesta HTTP inesperada, ver ESTADO_ERROR_BACKEND mas abajo) se
  reducia siempre a None: eso fue exactamente lo que oculto, durante la
  primera prueba real en produccion, que el backend estaba devolviendo
  la pagina de login (no JSON) a un cliente sin sesion -- ver
  web_app.py::proteger_sistema, que ahora si incluye estos endpoints en
  `rutas_publicas`.

ESTADO_SIN_CONEXION: no se pudo ni siquiera completar la peticion HTTP
(red caida, timeout, DNS, TLS...) o el backend respondio un status
inesperado (que no sea 200 ni 5xx) -- indistinguible de "no hay
internet" para el usuario.
ESTADO_ERROR_BACKEND: el HTTP SI se completo pero el backend fallo del
lado servidor (5xx) o devolvio algo que no es el JSON esperado (p. ej.
una pagina HTML en vez del endpoint -- exactamente el bug real).
ESTADO_CONECTADA: todo bien.
"""

import requests

import neko_config

URL_STATUS = f"{neko_config.NEKOPOS_BASE_URL}/api/printing/status"
URL_CLAIM = f"{neko_config.NEKOPOS_BASE_URL}/api/printing/claim"
URL_BASE_JOB = f"{neko_config.NEKOPOS_BASE_URL}/api/printing"

ESTADO_CONECTADA = "CONECTADA"
ESTADO_SIN_CONEXION = "SIN_CONEXION"
ESTADO_ERROR_BACKEND = "ERROR_BACKEND"


def _clasificar_respuesta(respuesta):
    """Comun a evaluar_status()/evaluar_claim(): decide el estado y,
    si CONECTADA, devuelve los datos ya parseados. `detalle` es un
    resumen corto (nunca un stacktrace) apto para logs."""
    if respuesta.status_code >= 500:
        return ESTADO_ERROR_BACKEND, None, f"HTTP {respuesta.status_code}"
    if respuesta.status_code != 200:
        return ESTADO_SIN_CONEXION, None, f"HTTP {respuesta.status_code}"

    content_type = (respuesta.headers.get("Content-Type") or "").split(";")[0].strip()
    if content_type and content_type != "application/json":
        # HTTP 200 pero no es JSON: tipicamente una pagina HTML (login,
        # error 404 bonito, etc.) en vez del endpoint esperado.
        return ESTADO_ERROR_BACKEND, None, f"content-type inesperado: {content_type}"

    try:
        datos = respuesta.json()
    except ValueError as e:
        return ESTADO_ERROR_BACKEND, None, f"respuesta no es JSON valido: {e}"

    if not isinstance(datos, dict) or not datos.get("ok"):
        return ESTADO_ERROR_BACKEND, None, "respuesta sin ok=true"

    return ESTADO_CONECTADA, datos, None


def _peticion_segura(peticion_fn, *args, **kwargs):
    """Ejecuta `peticion_fn(*args, **kwargs)`; si la peticion HTTP ni
    siquiera se completa (red, timeout, TLS, DNS...), devuelve
    (ESTADO_SIN_CONEXION, None, detalle) en vez de propagar la
    excepcion. Nunca None silencioso: siempre hay un `detalle` breve."""
    try:
        return peticion_fn(*args, **kwargs)
    except requests.exceptions.Timeout as e:
        return ESTADO_SIN_CONEXION, None, f"timeout: {e}"
    except requests.exceptions.SSLError as e:
        return ESTADO_SIN_CONEXION, None, f"error SSL: {e}"
    except requests.exceptions.ConnectionError as e:
        return ESTADO_SIN_CONEXION, None, f"error de conexion: {e}"
    except Exception as e:
        return ESTADO_SIN_CONEXION, None, f"{type(e).__name__}: {e}"


def evaluar_status(roles, timeout=5, sesion=None):
    """(estado, datos, detalle). `datos` = {"pendientes":N,"por_rol":{...}}
    solo si estado==ESTADO_CONECTADA; si no, es None y `detalle` trae un
    resumen corto (para logs/diagnostico, nunca un stacktrace)."""
    if not roles:
        return ESTADO_CONECTADA, {"pendientes": 0, "por_rol": {}}, None

    peticion = sesion or requests

    def _hacer():
        respuesta = peticion.get(URL_STATUS, params={"roles": ",".join(roles)}, timeout=timeout)
        estado, datos, detalle = _clasificar_respuesta(respuesta)
        if estado != ESTADO_CONECTADA:
            return estado, None, detalle
        return estado, {"pendientes": datos.get("pendientes", 0), "por_rol": datos.get("por_rol", {})}, None

    return _peticion_segura(_hacer)


def evaluar_claim(station_id, roles, timeout=8, sesion=None):
    """(estado, job). `job` (el dict reclamado, o None si no hay nada
    elegible ahora mismo) solo tiene sentido cuando estado==CONECTADA;
    en SIN_CONEXION/ERROR_BACKEND siempre es None. `detalle` como en
    evaluar_status(), para logs."""
    if not roles:
        return ESTADO_CONECTADA, None, None

    peticion = sesion or requests

    def _hacer():
        respuesta = peticion.post(
            URL_CLAIM, json={"station_id": station_id, "roles": list(roles)}, timeout=timeout
        )
        estado, datos, detalle = _clasificar_respuesta(respuesta)
        if estado != ESTADO_CONECTADA:
            return estado, None, detalle
        return estado, datos.get("job"), None

    return _peticion_segura(_hacer)


def consultar_status(roles, timeout=5, sesion=None):
    """{"pendientes": N, "por_rol": {...}} o None si no se pudo
    consultar (red caida, error del servidor, respuesta inesperada...).
    Contrato simple sobre evaluar_status(), para llamadores que no
    necesitan distinguir el motivo."""
    estado, datos, _detalle = evaluar_status(roles, timeout=timeout, sesion=sesion)
    return datos if estado == ESTADO_CONECTADA else None


def reclamar(station_id, roles, timeout=8, sesion=None):
    """El dict del job reclamado, o None si no hay nada elegible o hubo
    un error. Contrato simple sobre evaluar_claim()."""
    estado, job, _detalle = evaluar_claim(station_id, roles, timeout=timeout, sesion=sesion)
    return job if estado == ESTADO_CONECTADA else None


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
