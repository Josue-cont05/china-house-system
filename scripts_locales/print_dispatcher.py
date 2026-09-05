"""
print_dispatcher.py

Worker local UNIFICADO de la cola central de impresion (mision "NEKO
PRINTING 2.0"): un unico proceso que reclama (claim), imprime y
confirma (ack) trabajos de TODOS los roles asignados a esta estacion
(COCINA + los RECIBO_* que apliquen segun el perfil configurado).

Por que un unico proceso (mision, seccion 29): hoy Cocina y Recibos
comparten UNA SOLA impresora fisica. Dos procesos independientes
escribiendo al mismo COM en cualquier momento es un riesgo real de
corrupcion/errores intercalados. Este dispatcher reemplaza a
script_comanda_cocina.py + script_factura.py como fuente de impresion
NORMAL: una sola secuencia fisica ordenada (COCINA antes que recibos,
FIFO dentro de cada rol -- ya resuelto por el backend al reclamar), sin
riesgo de dos escrituras concurrentes.

Los scripts legacy (script_comanda_cocina.py, script_factura.py) NO se
borran (siguen sirviendo para diagnostico manual con --port), pero Neko
Local ya no los arranca como parte de "INICIAR NEKO": arranca este
dispatcher en su lugar. Ver launcher_core.py.

FUENTE DE VERDAD: el backend (print_jobs). Los archivos locales
(comandas_impresas.txt, facturas_impresas.txt) siguen existiendo como
SEGUNDA capa de seguridad/dedup (mision seccion 28), nunca como
autoridad: un evento ya PRINTED en el backend nunca se reimprime aunque
falte en el dedup local (p. ej. porque la impresora estuvo en otra PC).

ACK PENDIENTE (mision seccion 21/65): si la impresion fisica tuvo exito
pero el ACK al backend falla (red caida justo despues de imprimir), el
evento YA se marco impreso en el dedup local (nunca se reimprime) y el
job queda anotado en pendientes_ack.txt para reintentar el ACK en el
siguiente ciclo, ANTES de reclamar un job nuevo.
"""

import argparse
import json
import time
from pathlib import Path

import neko_config
import neko_log
import neko_version
import port_detection
import print_queue_client
import station_roles
from bluetooth_printer import PrinterError
from comanda_presentacion import imprimir_comanda
from factura_presentacion import imprimir_factura
from single_instance import SingleInstanceLock

log = neko_log.obtener_logger("dispatcher")

NOMBRE_MUTEX_DISPATCHER = "NekoWok_PrintDispatcher"

POLL_CON_JOB_SEG = 0.2  # tras imprimir uno, revisa el siguiente casi de inmediato
POLL_SIN_JOB_SEG = 3.0
POLL_SIN_ROLES_SEG = 10.0

# Backoff ante fallas de CONEXION con la cola central (red caida, error
# del backend...): mision seccion 15, "no bombardear Render". Escala
# hasta un tope moderado y vuelve a POLL_SIN_JOB_SEG en cuanto la cola
# vuelve a responder (ver `fallos_conexion_consecutivos` en
# ejecutar_polling). Distinto de MAX_FALLOS_CONSECUTIVOS (ese es sobre
# fallos de IMPRESION fisica, no de red).
BACKOFF_CONEXION_SEG = (3, 5, 10, 20, 30)

# Tras estos fallos de impresion CONSECUTIVOS, el dispatcher deja de
# reclamar (mision seccion 53: "si el puerto deja de funcionar... NO
# claim nuevos jobs") hasta que un reclamo posterior tenga exito o se
# reconfigure la impresora. Evita un ciclo fallar/liberar/fallar sin fin.
MAX_FALLOS_CONSECUTIVOS = 3

ARCHIVO_DEDUP_COCINA = "comandas_impresas.txt"
ARCHIVO_DEDUP_RECIBOS = "facturas_impresas.txt"
ARCHIVO_PENDIENTES_ACK = "pendientes_ack.txt"
ARCHIVO_HEARTBEAT = "dispatcher_heartbeat.json"

# Heartbeat "viejo" mas alla de este umbral = el proceso sigue vivo pero
# dejo de avanzar (colgado): usado por neko_local.py para distinguir
# "activo y funcionando" de "activo pero sin respuesta" (mision seccion
# 13). Generoso frente al peor caso normal (backoff maximo + timeout de
# claim): nunca debe dar un falso "colgado" en operacion normal.
HEARTBEAT_OBSOLETO_SEG = 60


# ----------------------------------------------------------------------
# Heartbeat (mision seccion 12/13): archivo simple, sin IPC complejo,
# que la GUI puede leer para saber si el dispatcher sigue avanzando
# (nunca solo si el proceso sigue vivo -- eso ya lo sabe por si misma
# via GestorWorkerProceso.activo).
# ----------------------------------------------------------------------
def escribir_heartbeat(estado_cola, ruta=None):
    """Nunca lanza: el heartbeat es diagnostico, no debe poder tumbar
    el dispatcher si el disco falla."""
    try:
        ruta = Path(ruta) if ruta else neko_config.state_dir() / ARCHIVO_HEARTBEAT
        ruta.parent.mkdir(parents=True, exist_ok=True)
        contenido = json.dumps(
            {"actualizado_en": time.time(), "estado_cola": estado_cola}, ensure_ascii=False
        )
        tmp = ruta.with_suffix(ruta.suffix + ".tmp")
        tmp.write_text(contenido, encoding="utf-8")
        tmp.replace(ruta)
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo escribir el heartbeat del dispatcher: {e}")


def leer_heartbeat(ruta=None):
    """Usado por neko_local.py. None si nunca se escribio o no se pudo
    leer (p. ej. el dispatcher nunca ha corrido en esta PC)."""
    ruta = Path(ruta) if ruta else neko_config.state_dir() / ARCHIVO_HEARTBEAT
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return None


# ----------------------------------------------------------------------
# Dedup local (segunda capa de seguridad, nunca la autoridad).
# ----------------------------------------------------------------------
def _leer_lineas(ruta):
    if not ruta.exists():
        return set()
    try:
        return {l.strip() for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()}
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo leer {ruta}: {e}")
        return set()


def _agregar_linea(ruta, linea):
    try:
        with ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(f"{linea}\n")
    except Exception as e:
        print(f"ADVERTENCIA: no se pudo escribir en {ruta}: {e}")


class DedupLocal:
    """Un set en memoria respaldado por un archivo de texto (uno por
    rol: comandas_impresas.txt / facturas_impresas.txt), migrado desde
    su ubicacion legacy junto al script la primera vez que se usa."""

    def __init__(self, nombre_archivo, ruta_legacy=None):
        self._nombre_archivo = nombre_archivo
        self._ruta_legacy = ruta_legacy
        self._ruta = None
        self._eventos = None

    def _asegurar(self):
        if self._ruta is None:
            self._ruta = neko_config.migrar_dedup_legacy(self._nombre_archivo, self._ruta_legacy)
            self._eventos = _leer_lineas(self._ruta)
        return self._ruta

    def contiene(self, evento):
        self._asegurar()
        return evento in self._eventos

    def marcar(self, evento):
        ruta = self._asegurar()
        if evento in self._eventos:
            return
        self._eventos.add(evento)
        _agregar_linea(ruta, evento)


# ----------------------------------------------------------------------
# ACK pendiente persistente (mision seccion 21/65).
# ----------------------------------------------------------------------
class PendientesAck:
    """Trabajos ya impresos fisicamente cuyo ACK todavia no se confirmo
    con el backend (tipicamente: la red cayo justo despues de imprimir).
    Persistente en disco para sobrevivir un reinicio del dispatcher
    entre la impresion y el ACK exitoso."""

    def __init__(self, ruta=None):
        self._ruta = ruta

    def _ruta_real(self):
        if self._ruta is None:
            neko_config.state_dir().mkdir(parents=True, exist_ok=True)
            self._ruta = neko_config.state_dir() / ARCHIVO_PENDIENTES_ACK
        return self._ruta

    def listar(self):
        ruta = self._ruta_real()
        if not ruta.exists():
            return []
        pendientes = []
        try:
            for linea in ruta.read_text(encoding="utf-8").splitlines():
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    pendientes.append(json.loads(linea))
                except ValueError:
                    continue
        except Exception as e:
            print(f"ADVERTENCIA: no se pudo leer {ruta}: {e}")
        return pendientes

    def _guardar_todos(self, pendientes):
        ruta = self._ruta_real()
        contenido = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pendientes)
        tmp = ruta.with_suffix(ruta.suffix + ".tmp")
        tmp.write_text(contenido, encoding="utf-8")
        tmp.replace(ruta)

    def agregar(self, job_id, station_id, lease_token, event_key):
        pendientes = self.listar()
        if any(p.get("job_id") == job_id for p in pendientes):
            return
        pendientes.append(
            {"job_id": job_id, "station_id": station_id, "lease_token": lease_token, "event_key": event_key}
        )
        self._guardar_todos(pendientes)

    def quitar(self, job_id):
        pendientes = [p for p in self.listar() if p.get("job_id") != job_id]
        self._guardar_todos(pendientes)


# ----------------------------------------------------------------------
# Orquestacion de un ciclo (testable sin HTTP/hardware reales: recibe
# `cliente` y `abridor_por_rol` inyectables).
# ----------------------------------------------------------------------
def reintentar_pendientes_ack(cliente, pendientes_ack, ahora_fn=None, log=None):
    """Reintenta confirmar el ACK de cada job pendiente. Devuelve
    cuantos quedaron SIN confirmar (si es 0, es seguro reclamar un job
    nuevo)."""
    restantes = 0
    for pendiente in pendientes_ack.listar():
        ok = cliente.confirmar(pendiente["job_id"], pendiente["station_id"], pendiente["lease_token"])
        if ok:
            pendientes_ack.quitar(pendiente["job_id"])
            if log:
                log.info("ACK pendiente confirmado: job_id=%s evento=%s", pendiente["job_id"], pendiente.get("event_key"))
        else:
            restantes += 1
    return restantes


def _dedup_para_rol(rol, dedup_cocina, dedup_recibos):
    return dedup_cocina if rol == station_roles.ROL_COCINA else dedup_recibos


def procesar_un_job(cliente, job, imprimir_por_rol, dedup_cocina, dedup_recibos, pendientes_ack, station_id, log=None):
    """Procesa UN job ya reclamado: imprime (si no esta en dedup local),
    marca dedup, confirma ACK (o lo deja pendiente). Devuelve un string
    de resultado para logs/tests: "impreso", "duplicado_localmente",
    "fallo_impresion", "ack_pendiente"."""
    rol = job["required_role"]
    evento = job["event_key"]
    dedup = _dedup_para_rol(rol, dedup_cocina, dedup_recibos)

    if dedup.contiene(evento):
        # Ya se imprimio fisicamente en un ciclo anterior (p. ej. el
        # dispatcher se reinicio entre imprimir y confirmar el ACK).
        # NUNCA reimprime; solo reintenta confirmar.
        if log:
            log.info("Job %s (evento=%s) ya impreso localmente; solo confirmando ACK", job["id"], evento)
        if cliente.confirmar(job["id"], station_id, job["lease_token"]):
            return "ack_confirmado_sin_reimprimir"
        pendientes_ack.agregar(job["id"], station_id, job["lease_token"], evento)
        return "ack_pendiente"

    try:
        imprimir_por_rol(job)
    except Exception as e:
        if log:
            log.warning("Fallo imprimiendo job %s (evento=%s): %s", job["id"], evento, e)
        cliente.reportar_fallo(job["id"], station_id, job["lease_token"], str(e))
        return "fallo_impresion"

    dedup.marcar(evento)
    if log:
        log.info("Job %s (evento=%s, rol=%s) impreso OK", job["id"], evento, rol)

    if cliente.confirmar(job["id"], station_id, job["lease_token"]):
        return "impreso"

    pendientes_ack.agregar(job["id"], station_id, job["lease_token"], evento)
    if log:
        log.warning("ACK fallo tras imprimir job %s (evento=%s); queda pendiente de reintento", job["id"], evento)
    return "ack_pendiente"


def _imprimir_por_rol(job, puerto, baudrate):
    """Despacho por rol: COCINA -> comanda_presentacion, RECIBO_* ->
    factura_presentacion. El payload de COCINA ya llega con "items"
    formateados por el backend en el momento del claim (ver
    web_app.py::api_printing_claim); este dispatcher nunca formatea ni
    calcula dinero, solo pasa los datos tal cual a la capa de
    presentacion, igual que hacian los workers legacy."""
    payload = job["payload"]
    if job["required_role"] == station_roles.ROL_COCINA:
        imprimir_comanda(payload, puerto, baudrate=baudrate)
        return
    imprimir_factura(
        numero=payload.get("numero"),
        cliente=payload.get("cliente"),
        tipo=payload.get("tipo"),
        referencia=payload.get("referencia"),
        fecha_hora=payload.get("fecha_hora"),
        items=payload.get("items") or [],
        subtotal=payload.get("subtotal"),
        descuento=payload.get("descuento"),
        delivery=payload.get("delivery"),
        total=payload.get("total"),
        total_bs=payload.get("total_bs"),
        cobrada=payload.get("cobrada"),
        port=puerto,
        baudrate=baudrate,
    )


class _ClienteQueue:
    """Envoltorio delgado sobre print_queue_client para que
    procesar_un_job()/reintentar_pendientes_ack() reciban un objeto con
    metodos (mas facil de inyectar un doble de prueba) en vez de
    funciones sueltas."""

    def __init__(self, station_id):
        self.station_id = station_id

    def reclamar(self, roles):
        return print_queue_client.reclamar(self.station_id, roles)

    def confirmar(self, job_id, station_id, lease_token):
        return print_queue_client.confirmar(job_id, station_id, lease_token)

    def reportar_fallo(self, job_id, station_id, lease_token, error):
        return print_queue_client.reportar_fallo(job_id, station_id, lease_token, error)


def resolver_puerto_worker(override_port):
    """Identico en espiritu a los workers legacy: --port fuerza el
    puerto sin tocar la config; si no, resuelve contra la config local
    (huella de la impresora), actualizandola si cambio de COM."""
    if override_port:
        print(f"[DISPATCHER] Puerto forzado por --port: {override_port}")
        return override_port, neko_config.DEFAULT_BAUDRATE

    config = neko_config.cargar_config()
    resultado = port_detection.resolver_puerto(config)

    if resultado.status == "ok":
        return resultado.port, config.get("baudrate", neko_config.DEFAULT_BAUDRATE)
    if resultado.status == "rematched":
        neko_config.guardar_config(resultado.config)
        print(f"[DISPATCHER] La impresora cambio de puerto; ahora en {resultado.port}.")
        return resultado.port, resultado.config.get("baudrate", neko_config.DEFAULT_BAUDRATE)
    if resultado.status == "sin_configurar":
        print("[DISPATCHER] No hay impresora configurada todavia. Abre Neko Local y usa 'Configurar impresora'.")
        return None, None
    if resultado.status == "ambiguous":
        print("[DISPATCHER] Varios puertos coinciden con la impresora guardada; reconfigura desde Neko Local.")
        return None, None
    print("[DISPATCHER] No se encontro la impresora configurada; reconfigura desde Neko Local.")
    return None, None


class EstadoDispatcher:
    """Contadores/transiciones que persisten entre ciclos de
    ejecutar_un_ciclo(). Objeto mutable simple a proposito (sin IPC ni
    framework): separado de ejecutar_polling() para poder probar la
    logica de un ciclo sin threads, sin time.sleep real y sin un loop
    infinito real."""

    def __init__(self, puerto, baudrate):
        self.puerto = puerto
        self.baudrate = baudrate
        self.fallos_impresion_consecutivos = 0
        self.fallos_conexion_consecutivos = 0
        self.estado_cola_anterior = None
        self.hubo_trabajo_la_ultima_vez = None


def ejecutar_un_ciclo(estado, station_id, roles, cliente, dedup_cocina, dedup_recibos, pendientes_ack, log=None, evaluar_claim_fn=None):
    """Un solo ciclo de trabajo del dispatcher, SIN time.sleep ni loop
    infinito: evalua conectividad, decide si puede reclamar, procesa un
    job si hay uno, y devuelve (resultado, espera_seg, estado_heartbeat)
    para que ejecutar_polling() decida cuanto dormir. `estado` (un
    EstadoDispatcher) se muta in-place con los contadores/transiciones.

    `resultado` es uno de: "circuito_abierto", "ack_pendiente",
    "sin_conexion", "error_backend", "sin_trabajos", "trabajo_procesado".
    Nunca hace claim/imprime/suena si la cola no esta CONECTADA (mision
    seccion 14): esto es lo que hace testeable, sin red ni hardware
    reales, el caso critico "Printing API falla -> no claim/print/beep".
    """
    evaluar_claim_fn = evaluar_claim_fn or print_queue_client.evaluar_claim

    if estado.fallos_impresion_consecutivos >= MAX_FALLOS_CONSECUTIVOS:
        if log:
            log.warning(
                "Circuito abierto tras %d fallos consecutivos de impresion; en espera.",
                estado.fallos_impresion_consecutivos,
            )
        nuevo_puerto, nuevo_baudrate = resolver_puerto_worker(None)
        if nuevo_puerto:
            estado.puerto, estado.baudrate = nuevo_puerto, nuevo_baudrate
            estado.fallos_impresion_consecutivos = 0
            if log:
                log.info("Impresora recuperada; reanudando reclamos (puerto=%s).", nuevo_puerto)
        return "circuito_abierto", POLL_SIN_JOB_SEG * 3, "IMPRESORA_EN_ESPERA"

    pendientes_restantes = reintentar_pendientes_ack(cliente, pendientes_ack, log=log)
    if pendientes_restantes > 0:
        return "ack_pendiente", POLL_SIN_JOB_SEG, "ACK_PENDIENTE"

    # evaluar_claim (no el `reclamar()` simple) para distinguir "cola
    # vacia" de "no se pudo hablar con la cola" -- esa distincion es
    # exactamente lo que faltaba para diagnosticar el caso real "Cola:
    # sin conexion" pese a que el backend si respondia.
    estado_cola, job, detalle = evaluar_claim_fn(station_id, roles)

    if estado_cola != estado.estado_cola_anterior and log:
        if estado_cola == print_queue_client.ESTADO_CONECTADA:
            log.info("Cola: conectada.")
        elif estado_cola == print_queue_client.ESTADO_SIN_CONEXION:
            log.warning("Cola: sin conexion (%s).", detalle)
        else:
            log.warning("Cola: error del backend (%s).", detalle)
    estado.estado_cola_anterior = estado_cola

    if estado_cola != print_queue_client.ESTADO_CONECTADA:
        # NUNCA claim/print/beep/ack si la cola no es usable (seccion
        # 14). Backoff progresivo para no bombardear Render (seccion
        # 15); vuelve a polling normal apenas la cola responda de nuevo.
        estado.fallos_conexion_consecutivos += 1
        espera = BACKOFF_CONEXION_SEG[min(estado.fallos_conexion_consecutivos - 1, len(BACKOFF_CONEXION_SEG) - 1)]
        resultado = "sin_conexion" if estado_cola == print_queue_client.ESTADO_SIN_CONEXION else "error_backend"
        return resultado, espera, estado_cola
    estado.fallos_conexion_consecutivos = 0

    if job is None:
        if estado.hubo_trabajo_la_ultima_vez is not False:
            if log:
                log.info("Sin trabajos pendientes; en espera.")
            estado.hubo_trabajo_la_ultima_vez = False
        return "sin_trabajos", POLL_SIN_JOB_SEG, estado_cola
    estado.hubo_trabajo_la_ultima_vez = True

    if log:
        log.info("Job reclamado: id=%s rol=%s evento=%s", job["id"], job["required_role"], job["event_key"])
    resultado_job = procesar_un_job(
        cliente, job, lambda j: _imprimir_por_rol(j, estado.puerto, estado.baudrate),
        dedup_cocina, dedup_recibos, pendientes_ack, station_id, log=log,
    )
    if resultado_job == "fallo_impresion":
        estado.fallos_impresion_consecutivos += 1
    else:
        estado.fallos_impresion_consecutivos = 0
    return "trabajo_procesado", POLL_CON_JOB_SEG, estado_cola


def ejecutar_polling(puerto, baudrate, station_id, roles):
    cliente = _ClienteQueue(station_id)
    dedup_cocina = DedupLocal(ARCHIVO_DEDUP_COCINA, Path(__file__).resolve().parent / ARCHIVO_DEDUP_COCINA)
    dedup_recibos = DedupLocal(ARCHIVO_DEDUP_RECIBOS, Path(__file__).resolve().parent / ARCHIVO_DEDUP_RECIBOS)
    pendientes_ack = PendientesAck()
    estado = EstadoDispatcher(puerto, baudrate)

    station_id_resumido = f"{station_id[:8]}..." if station_id and len(station_id) > 8 else station_id
    print(f"Dispatcher iniciado. station_id={station_id} roles={list(roles)} puerto={puerto} baudrate={baudrate}")
    log.info(
        "%s dispatcher iniciado: backend=%s puerto=%s station_id=%s roles=%s",
        neko_version.version_texto(), print_queue_client.URL_STATUS.rsplit("/api/", 1)[0],
        puerto, station_id_resumido, list(roles),
    )
    escribir_heartbeat("INICIANDO")

    while True:
        try:
            _resultado, espera_seg, estado_heartbeat = ejecutar_un_ciclo(
                estado, station_id, roles, cliente, dedup_cocina, dedup_recibos, pendientes_ack, log=log,
            )
            escribir_heartbeat(estado_heartbeat)
            time.sleep(espera_seg)
        except Exception as e:
            print(f"ERROR general en el dispatcher: {e}")
            log.warning("Error general en el ciclo del dispatcher: %s", e)
            escribir_heartbeat("ERROR_INTERNO")
            time.sleep(POLL_SIN_JOB_SEG)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dispatcher unificado de impresion (cocina + recibos).")
    parser.add_argument("--port", default=None, help="Override manual de puerto (ej. COM6)")
    args = parser.parse_args(argv)

    puerto, baudrate = resolver_puerto_worker(args.port)
    if puerto is None:
        return 1

    config = neko_config.asegurar_identidad_estacion()
    station_id = config["station_id"]
    try:
        roles = station_roles.roles_validos(config.get("roles"))
    except ValueError as e:
        print(f"[DISPATCHER] Configuracion de roles invalida ({e}); usando perfil TODO por seguridad.")
        roles = station_roles.roles_por_perfil(station_roles.PERFIL_TODO)

    if not roles:
        print("[DISPATCHER] Esta estacion no tiene ningun rol asignado. Nada que hacer.")
        return 1

    lock = SingleInstanceLock(NOMBRE_MUTEX_DISPATCHER)
    if not lock.acquire():
        print("[DISPATCHER] Ya hay un dispatcher en ejecucion en esta computadora. Cerrando.")
        return 0

    try:
        ejecutar_polling(puerto, baudrate, station_id, roles)
    except Exception as e:
        # ejecutar_polling() corre en un `while True` con su propio
        # manejo de errores por ciclo: llegar aqui es una falla
        # realmente inesperada (nunca deberia pasar en operacion
        # normal), asi que queda registrada explicitamente.
        log.error("Dispatcher detenido inesperadamente: %s", e)
        raise
    finally:
        lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
