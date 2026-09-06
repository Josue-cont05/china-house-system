"""
notifications.py (infraestructura)

Motor GENERAL de notificaciones internas (mision "engine general de
notificaciones"): un unico mecanismo IN_APP para avisar a un usuario
especifico que algo paso (Mesa lista para retirar, Pick Up listo,
Delivery asignado/sin conductor/listo, etc).

Deliberadamente INDEPENDIENTE de:
- print_jobs / Printing 2.0 (claim/lease/ACK/dispatcher/estaciones):
  una notificacion NO es un trabajo de impresion.
- service_alerts (solicitudes operativas para Monica en /despacho):
  dominios distintos, tablas distintas, sin relacion transaccional.

Idempotente via UNIQUE(event_key) + INSERT...WHERE NOT EXISTS (mismo
patron que print_jobs.py y service_alerts.py), asi un reintento HTTP o
un doble evento nunca duplica una notificacion.
"""

import json


def crear_tabla_notifications(get_connection, pk_autoincrement_sql):
    """Idempotente, no destructiva. Se llama desde web_app.init_db()."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS notifications (
            id {pk_autoincrement_sql()},
            usuario_destino_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            orden_id INTEGER,
            titulo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            datos TEXT,
            created_at TEXT NOT NULL,
            read_at TEXT,
            event_key TEXT NOT NULL UNIQUE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_usuario ON notifications (usuario_destino_id, read_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications (created_at)"
    )
    conn.commit()
    conn.close()


def crear_notificacion(
    connection_factory,
    *,
    event_key,
    usuario_destino_id,
    tipo,
    titulo,
    mensaje,
    orden_id=None,
    datos=None,
    fecha,
):
    """Crea una notificacion con SU PROPIA conexion/transaccion --
    deliberadamente NO participa de la transaccion de negocio que la
    origina (marcar listo para retirar, crear un delivery, etc): una
    notificacion es un efecto secundario tolerante a fallos, nunca debe
    poder bloquear ni revertir la operacion real. Si usuario_destino_id
    es None (no hay a quien notificar, p.ej. falta configurar un
    coordinador) no hace nada y devuelve False."""
    if not usuario_destino_id:
        return False
    conn = connection_factory()
    cursor = conn.cursor()
    try:
        datos_json = json.dumps(datos or {}, ensure_ascii=False)
        cursor.execute(
            """
            INSERT INTO notifications (
                usuario_destino_id, tipo, orden_id, titulo, mensaje,
                datos, created_at, read_at, event_key
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, NULL, ?
            WHERE NOT EXISTS (SELECT 1 FROM notifications WHERE event_key = ?)
            """,
            (
                usuario_destino_id,
                tipo,
                orden_id,
                titulo,
                mensaje,
                datos_json,
                fecha,
                event_key,
                event_key,
            ),
        )
        creada = cursor.rowcount == 1
        conn.commit()
        return creada
    except Exception as exc:
        conn.rollback()
        print(f"ADVERTENCIA: no se pudo crear notificacion '{event_key}': {exc}")
        return False
    finally:
        conn.close()


class SqlNotificationsRepository:
    def __init__(self, connection_factory):
        self._connection_factory = connection_factory

    def listar_para_usuario(self, usuario_id, limite=30):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, tipo, orden_id, titulo, mensaje, datos, created_at, read_at
                FROM notifications
                WHERE usuario_destino_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (usuario_id, limite),
            )
            filas = cursor.fetchall()
        finally:
            conn.close()

        notificaciones = []
        for fila in filas:
            notif_id, tipo, orden_id, titulo, mensaje, datos_json, created_at, read_at = fila
            try:
                datos = json.loads(datos_json) if datos_json else {}
            except (TypeError, ValueError):
                datos = {}
            notificaciones.append(
                {
                    "id": notif_id,
                    "tipo": tipo,
                    "orden_id": orden_id,
                    "titulo": titulo,
                    "mensaje": mensaje,
                    "datos": datos,
                    "created_at": created_at,
                    "read_at": read_at,
                    "leida": read_at is not None,
                }
            )
        return notificaciones

    def contar_no_leidas(self, usuario_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM notifications WHERE usuario_destino_id = ? AND read_at IS NULL",
                (usuario_id,),
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def marcar_leida(self, notificacion_id, usuario_id, fecha):
        """Idempotente y con ownership: solo el DESTINATARIO puede marcar
        su propia notificacion como leida (nunca la de otro usuario)."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE notifications
                SET read_at = ?
                WHERE id = ? AND usuario_destino_id = ? AND read_at IS NULL
                """,
                (fecha, notificacion_id, usuario_id),
            )
            afectadas = cursor.rowcount
            conn.commit()
            return afectadas > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def marcar_todas_leidas(self, usuario_id, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE notifications
                SET read_at = ?
                WHERE usuario_destino_id = ? AND read_at IS NULL
                """,
                (fecha, usuario_id),
            )
            afectadas = cursor.rowcount
            conn.commit()
            return afectadas
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
