"""
print_queue.py (infraestructura)

Acceso a datos de la cola central de impresion (tabla print_jobs).
Dos estilos, igual que kitchen_comandas.py:

- `crear_job_en_cursor()`: funcion de nivel-cursor, para insertar un job
  DENTRO de una transaccion ya abierta por otro flujo (p. ej. junto con
  la propia creacion de la comanda en crear_comanda_en_cursor, o junto
  con /activar_factura) - asi el job nunca puede faltar si la operacion
  que lo origina si se confirmo.
- `SqlPrintQueueRepository`: operaciones que abren su propia conexion
  (claim/ack/fail/status), porque no dependen de otra transaccion de
  negocio en curso.

IMPORTANTE (payload de COCINA): el payload se guarda con los items
CRUDOS (producto, indicacion) tal como estan en orden_items en el
momento de crear el job -- nunca el texto ya formateado para el papel
(agrupar_items_comanda, en web_app.py, no es importable desde aqui sin
crear un ciclo). El formateo final se aplica en el momento del claim,
en la ruta Flask (que si puede importar esa funcion). Como
agrupar_items_comanda es pura (mismo resultado dado el mismo input),
aplicarla en el claim en vez de en la creacion no cambia el resultado
impreso, y evita que una edicion posterior de orden_items (ver
/eliminar_item, /actualizar_indicacion_item) altere retroactivamente
lo que se imprime: los items crudos ya quedaron congelados en el
payload del job desde el instante de creacion.
"""

import json

ESTADO_PENDING = "PENDING"
ESTADO_LEASED = "LEASED"
ESTADO_PRINTED = "PRINTED"

RESULTADO_OK = "OK"
RESULTADO_OK_IDEMPOTENTE = "OK_IDEMPOTENTE"
RESULTADO_NO_ENCONTRADO = "NO_ENCONTRADO"
RESULTADO_LEASE_INVALIDO = "LEASE_INVALIDO"


def crear_tabla_print_jobs(get_connection, pk_autoincrement_sql):
    """Crea la tabla (idempotente, no destructiva) e indices minimos.
    Se llama desde web_app.init_db(), igual que crear_tablas_comandas():
    recibe get_connection/pk_autoincrement_sql como funciones para no
    importar web_app.py desde este modulo (evita el ciclo)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS print_jobs (
            id {pk_autoincrement_sql()},
            event_key TEXT NOT NULL UNIQUE,
            job_type TEXT NOT NULL,
            required_role TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'LEASED', 'PRINTED')),
            created_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            lease_owner TEXT,
            lease_token TEXT,
            lease_expires_at TEXT,
            printed_at TEXT,
            printed_by_station TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_print_jobs_claim
        ON print_jobs (required_role, status, available_at)
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs (status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_print_jobs_created ON print_jobs (created_at)"
    )
    conn.commit()
    conn.close()


def crear_job_en_cursor(cursor, *, event_key, job_type, required_role, payload, fecha):
    """Inserta un print_job si `event_key` no existe todavia (idempotente
    va UNIQUE + INSERT...WHERE NOT EXISTS, portable entre SQLite y
    Postgres sin ramificar por dialecto). Devuelve True si se creo un
    job nuevo, False si ya existia (no se duplica; no es un error).

    No hace commit ni abre conexion: opera sobre `cursor`, para poder
    llamarse DENTRO de la transaccion de quien crea el evento de
    negocio (comanda, activacion de factura, reimpresion...).
    """
    payload_json = json.dumps(payload, ensure_ascii=False)
    cursor.execute(
        """
        INSERT INTO print_jobs (
            event_key, job_type, required_role, payload, status,
            created_at, available_at, attempt_count
        )
        SELECT ?, ?, ?, ?, 'PENDING', ?, ?, 0
        WHERE NOT EXISTS (SELECT 1 FROM print_jobs WHERE event_key = ?)
        """,
        (event_key, job_type, required_role, payload_json, fecha, fecha, event_key),
    )
    return cursor.rowcount == 1


class SqlPrintQueueRepository:
    def __init__(self, connection_factory):
        self._connection_factory = connection_factory

    def contar_pendientes_por_rol(self, roles, ahora_texto):
        if not roles:
            return {}
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in roles)
            cursor.execute(
                f"""
                SELECT required_role, COUNT(*)
                FROM print_jobs
                WHERE required_role IN ({placeholders})
                  AND (
                    (status = 'PENDING' AND available_at <= ?)
                    OR (status = 'LEASED' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                  )
                GROUP BY required_role
                """,
                (*roles, ahora_texto, ahora_texto),
            )
            resultado = {rol: 0 for rol in roles}
            for rol, cantidad in cursor.fetchall():
                resultado[rol] = int(cantidad)
            return resultado
        finally:
            conn.close()

    def reclamar_job(self, *, roles, station_id, lease_token, lease_expires_texto, ahora_texto):
        """Reclamo atomico: UPDATE condicional (nunca SELECT+UPDATE
        separados) que solo puede afectar una fila, y que vuelve a
        validar la elegibilidad al momento de escribir (asi dos
        estaciones concurrentes nunca ganan la misma fila: la segunda
        en llegar ve status ya cambiado y su UPDATE no afecta ninguna
        fila). Prioridad: COCINA antes que cualquier recibo; dentro de
        un mismo rol, FIFO por created_at/id. Devuelve un dict del job
        reclamado, o None si no hay ninguno elegible ahora mismo."""
        if not roles:
            return None
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in roles)
            elegible = (
                "(status = 'PENDING' AND available_at <= ?) "
                "OR (status = 'LEASED' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)"
            )
            cursor.execute(
                f"""
                UPDATE print_jobs
                SET status='LEASED', lease_owner=?, lease_token=?, lease_expires_at=?,
                    attempt_count = attempt_count + 1
                WHERE id = (
                    SELECT id FROM print_jobs
                    WHERE required_role IN ({placeholders})
                      AND ({elegible})
                    ORDER BY
                        CASE required_role WHEN 'COCINA' THEN 0 ELSE 1 END ASC,
                        created_at ASC,
                        id ASC
                    LIMIT 1
                )
                AND ({elegible})
                RETURNING id, event_key, job_type, required_role, payload, created_at
                """,
                (
                    station_id, lease_token, lease_expires_texto,
                    *roles, ahora_texto, ahora_texto,
                    ahora_texto, ahora_texto,
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            if row is None:
                return None
            return {
                "id": row[0],
                "event_key": row[1],
                "job_type": row[2],
                "required_role": row[3],
                "payload": json.loads(row[4]),
                "created_at": row[5],
                "lease_token": lease_token,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def confirmar_ack(self, *, job_id, station_id, lease_token, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT status, lease_owner, lease_token FROM print_jobs WHERE id=?",
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                return RESULTADO_NO_ENCONTRADO

            status, lease_owner, stored_token = row
            if status == ESTADO_PRINTED:
                conn.rollback()
                if lease_owner == station_id and stored_token == lease_token:
                    return RESULTADO_OK_IDEMPOTENTE
                return RESULTADO_LEASE_INVALIDO

            if status != ESTADO_LEASED or lease_owner != station_id or stored_token != lease_token:
                conn.rollback()
                return RESULTADO_LEASE_INVALIDO

            cursor.execute(
                """
                UPDATE print_jobs
                SET status='PRINTED', printed_at=?, printed_by_station=?
                WHERE id=? AND lease_token=?
                """,
                (fecha, station_id, job_id, lease_token),
            )
            conn.commit()
            return RESULTADO_OK
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def liberar_job(self, *, job_id, station_id, lease_token, error_sanitizado, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT status, lease_owner, lease_token FROM print_jobs WHERE id=?",
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                return RESULTADO_NO_ENCONTRADO

            status, lease_owner, stored_token = row
            if status != ESTADO_LEASED or lease_owner != station_id or stored_token != lease_token:
                conn.rollback()
                return RESULTADO_LEASE_INVALIDO

            cursor.execute(
                """
                UPDATE print_jobs
                SET status='PENDING', lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL,
                    available_at=?, last_error=?
                WHERE id=? AND lease_token=?
                """,
                (fecha, error_sanitizado, job_id, lease_token),
            )
            conn.commit()
            return RESULTADO_OK
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
