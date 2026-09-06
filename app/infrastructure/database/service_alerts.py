"""
service_alerts.py (infraestructura)

Acceso a datos de las alertas operativas de servicio (tabla
service_alerts), para la pantalla DESPACHO. Mismo estilo dual que
print_queue.py:

- `crear_alerta_en_cursor()`: funcion de nivel-cursor, para insertar
  DENTRO de la misma transaccion que crea el lote incremental de cocina
  (crear_comanda_en_cursor, en kitchen_comandas.py) -- asi la alerta
  nunca puede faltar si el lote que la origina si se confirmo, y nunca
  puede duplicarse (UNIQUE event_key + INSERT...WHERE NOT EXISTS, igual
  patron que print_jobs, portable SQLite/Postgres).
- `SqlServiceAlertsRepository`: listar pendientes / marcar atendida,
  con conexion propia (no dependen de una transaccion de negocio en
  curso).

Deliberadamente NO reutiliza la tabla print_jobs: una alerta de
servicio no es un trabajo de impresion (no hay claim/lease/ACK/rol de
estacion), es una notificacion para un humano en la pantalla /despacho.
"""

import json

ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_ATENDIDA = "ATENDIDA"


def crear_tabla_service_alerts(get_connection, pk_autoincrement_sql):
    """Crea la tabla (idempotente, no destructiva) e indices minimos.
    Se llama desde web_app.init_db(), igual que crear_tabla_print_jobs():
    recibe get_connection/pk_autoincrement_sql como funciones para no
    importar web_app.py desde este modulo (evita el ciclo)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS service_alerts (
            id {pk_autoincrement_sql()},
            orden_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDIENTE'
                CHECK (status IN ('PENDIENTE', 'ATENDIDA')),
            atendido_at TEXT,
            atendido_por TEXT,
            event_key TEXT NOT NULL UNIQUE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_alerts_status ON service_alerts (status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_alerts_orden ON service_alerts (orden_id)"
    )
    conn.commit()
    conn.close()


def crear_alerta_en_cursor(cursor, *, event_key, orden_id, tipo, payload, fecha):
    """Inserta una service_alert si `event_key` no existe todavia
    (idempotente via UNIQUE + INSERT...WHERE NOT EXISTS). Devuelve True
    si se creo una alerta nueva, False si ya existia.

    No hace commit ni abre conexion: opera sobre `cursor`, para llamarse
    DENTRO de la transaccion que crea el lote de cocina que origina la
    alerta.
    """
    payload_json = json.dumps(payload, ensure_ascii=False)
    cursor.execute(
        """
        INSERT INTO service_alerts (
            orden_id, tipo, payload, created_at, status, event_key
        )
        SELECT ?, ?, ?, ?, 'PENDIENTE', ?
        WHERE NOT EXISTS (SELECT 1 FROM service_alerts WHERE event_key = ?)
        """,
        (orden_id, tipo, payload_json, fecha, event_key, event_key),
    )
    return cursor.rowcount == 1


class SqlServiceAlertsRepository:
    def __init__(self, connection_factory):
        self._connection_factory = connection_factory

    def listar_pendientes(self):
        """Alertas activas, mas antigua primero (deben persistir hasta
        ser atendidas -- nunca desaparecen por refresh ni por poll)."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, orden_id, tipo, payload, created_at, event_key
                FROM service_alerts
                WHERE status = 'PENDIENTE'
                ORDER BY created_at ASC, id ASC
                """
            )
            filas = cursor.fetchall()
        finally:
            conn.close()
        alertas = []
        for fila in filas:
            alerta_id, orden_id, tipo, payload_json, created_at, event_key = fila
            try:
                payload = json.loads(payload_json)
            except (TypeError, ValueError):
                payload = {}
            alertas.append(
                {
                    "id": alerta_id,
                    "orden_id": orden_id,
                    "tipo": tipo,
                    "payload": payload,
                    "created_at": created_at,
                    "event_key": event_key,
                }
            )
        return alertas

    def marcar_atendida(self, alerta_id, usuario, fecha):
        """Idempotente: si la alerta ya estaba ATENDIDA, no hace nada y
        devuelve False (no es un error -- dos clicks no producen dos
        eventos de atencion)."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE service_alerts
                SET status = 'ATENDIDA', atendido_at = ?, atendido_por = ?
                WHERE id = ? AND status = 'PENDIENTE'
                """,
                (fecha, usuario, alerta_id),
            )
            afectadas = cursor.rowcount
            conn.commit()
            return afectadas > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
