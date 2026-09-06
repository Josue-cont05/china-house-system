"""
schema.py (infraestructura)

Unico lugar del proyecto que debe saber si la base de datos activa es
SQLite (dev/test) o Postgres (produccion, via DATABASE_URL): carga la
configuracion desde variables de entorno, abre la conexion correcta y
expone los helpers de esquema que dependen de ese detalle
(pk_autoincrement_sql, obtener_ultimo_id, columna_existe,
asegurar_columna). El resto del codigo (web_app.py y los modulos de
app/infrastructure/database/*) solo ve `cursor.execute(...)` con "?"
como placeholder -- CursorWrapper/adaptar_query traducen a "%s" cuando
hace falta.

CONFIG es un dict mutable a proposito: varios tests redirigen la base
de datos en runtime mutandolo en el lugar (`CONFIG["SQLITE_PATH"] = ...`)
en vez de reasignarlo. web_app.py importa este MISMO objeto (no una
copia), asi que esa mutacion sigue viendose reflejada aqui.
"""

import os
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    import psycopg2
except Exception:
    psycopg2 = None


def cargar_configuracion():
    app_env = os.environ.get("APP_ENV", "development").strip().lower()

    if app_env == "test":
        sqlite_path = os.environ.get("TEST_SQLITE_PATH", "china_house_test.db").strip()
    else:
        sqlite_path = os.environ.get(
            "SQLITE_PATH",
            os.environ.get("DB_PATH", "china_house.db"),
        ).strip()

    database_url = os.environ.get("DATABASE_URL", "").strip()

    return {
        "APP_ENV": app_env,
        "DATABASE_URL": database_url,
        "USE_POSTGRES": bool(database_url),
        "SQLITE_PATH": sqlite_path,
        "SECRET_KEY": os.environ.get("SECRET_KEY", "china-house-pos-secret"),
        "SELF_ORDER_PUBLIC_BASE_URL": os.environ.get("SELF_ORDER_PUBLIC_BASE_URL", "").strip(),
    }


CONFIG = cargar_configuracion()


def es_postgres():
    return CONFIG["USE_POSTGRES"]


def normalizar_database_url(database_url):
    if not database_url:
        return database_url

    parsed = urlparse(database_url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if "sslmode" not in query_params:
        query_params["sslmode"] = "require"

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_params),
            parsed.fragment,
        )
    )


def adaptar_query(query):
    if es_postgres():
        return query.replace("?", "%s")
    return query


class CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        query = adaptar_query(query)
        if params is None:
            self._cursor.execute(query)
        else:
            self._cursor.execute(query, params)
        return self

    def executemany(self, query, seq_of_params):
        query = adaptar_query(query)
        self._cursor.executemany(query, seq_of_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    def __getattr__(self, item):
        return getattr(self._cursor, item)


class ConnectionWrapper:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return CursorWrapper(self._connection.cursor())

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()

    def __getattr__(self, item):
        return getattr(self._connection, item)


def get_connection():
    if es_postgres():
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL requiere psycopg2-binary instalado.")

        conn = psycopg2.connect(normalizar_database_url(CONFIG["DATABASE_URL"]))
        return ConnectionWrapper(conn)

    conn = sqlite3.connect(CONFIG["SQLITE_PATH"])
    return ConnectionWrapper(conn)


def pk_autoincrement_sql():
    if es_postgres():
        return "SERIAL PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


def obtener_ultimo_id(cursor, tabla):
    if es_postgres():
        cursor.execute(
            "SELECT currval(pg_get_serial_sequence(?, ?))",
            (tabla, "id"),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    if cursor.lastrowid:
        return cursor.lastrowid

    cursor.execute("SELECT last_insert_rowid()")
    row = cursor.fetchone()
    return row[0] if row else None


def columna_existe(cursor, tabla, columna):
    if es_postgres():
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = ?
              AND column_name = ?
            LIMIT 1
            """,
            (tabla, columna),
        )
        return cursor.fetchone() is not None

    cursor.execute(f"PRAGMA table_info({tabla})")
    columnas = [col[1] for col in cursor.fetchall()]
    return columna in columnas


def asegurar_columna(tabla, columna, definicion):
    conn = get_connection()
    cursor = conn.cursor()

    if not columna_existe(cursor, tabla, columna):
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        conn.commit()

    conn.close()
