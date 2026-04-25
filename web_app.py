from collections import defaultdict
import datetime
import html as html_lib
import io
import os
import sqlite3
import zipfile
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from flask import Flask, Response, jsonify, redirect, request, session
import pytz

try:
    import psycopg2
except Exception:
    psycopg2 = None


CLAVE_SUPERVISOR = "0102"
VENEZUELA_TZ = pytz.timezone("America/Caracas")
METODOS_PAGO_VALIDOS = {"bs_pago_movil", "pago_movil", "bs_efectivo", "usd"}
SABORES_REFRESCO = [
    "Coca Cola",
    "Chinotto",
    "Frescolita",
    "Naranja",
    "Uva",
    "Manzana",
    "7Up",
    "Pepsi",
]
ETIQUETAS_METODO_PAGO = {
    "bs_pago_movil": "Pago movil en Bs",
    "pago_movil": "Pago movil en Bs",
    "bs_efectivo": "Efectivo en Bs",
    "usd": "Efectivo en USD",
}


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
    }


CONFIG = cargar_configuracion()

app = Flask(__name__)
app.secret_key = CONFIG["SECRET_KEY"]


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


def ahora_venezuela():
    return datetime.datetime.now(VENEZUELA_TZ)


def parsear_fecha_hora_venezuela(fecha_texto):
    dt = datetime.datetime.strptime(fecha_texto, "%Y-%m-%d %H:%M:%S")
    return VENEZUELA_TZ.localize(dt)


def a_float(valor, default=0.0):
    try:
        if valor is None:
            return default
        texto = str(valor).strip().replace(",", ".")
        if texto == "":
            return default
        return float(texto)
    except Exception:
        return default


def normalizar_metodo_pago(metodo):
    metodo = (metodo or "").strip()
    if metodo == "pago_movil":
        return "bs_pago_movil"
    return metodo


def es_producto_refresco(nombre):
    return "refresco" in (nombre or "").lower()


def normalizar_sabor_refresco(sabor):
    sabor_limpio = (sabor or "").strip()
    if not sabor_limpio or len(sabor_limpio) > 40:
        return ""

    for opcion in SABORES_REFRESCO:
        if sabor_limpio.lower() == opcion.lower():
            return opcion

    sabor_limpio = sabor_limpio.replace("<", "").replace(">", "")
    return sabor_limpio.strip()


def etiqueta_metodo_pago(metodo):
    return ETIQUETAS_METODO_PAGO.get(normalizar_metodo_pago(metodo), metodo or "-")


def monto_formateado_segun_metodo(metodo, monto):
    metodo = normalizar_metodo_pago(metodo)
    monto = a_float(monto)
    if metodo == "usd":
        return f"$ {round(monto, 2)}"
    return f"Bs {round(monto, 2)}"


def convertir_pago_equivalente(metodo, monto, tasa):
    metodo = normalizar_metodo_pago(metodo)
    monto = a_float(monto)

    if metodo == "usd":
        return monto * tasa, monto

    if metodo in ("bs_pago_movil", "bs_efectivo"):
        usd = (monto / tasa) if tasa else 0.0
        return monto, usd

    return 0.0, 0.0


def obtener_tasa_actual(cursor):
    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()
    return float(row[0]) if row and row[0] else 1.0


def asegurar_columna(tabla, columna, definicion):
    conn = get_connection()
    cursor = conn.cursor()

    if not columna_existe(cursor, tabla, columna):
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        conn.commit()

    conn.close()


def asegurar_columna_facturar():
    asegurar_columna("ordenes", "facturar", "INTEGER DEFAULT 0")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET facturar=0 WHERE facturar IS NULL")
    conn.commit()
    conn.close()


def crear_tablas_cierre_jornada():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cierres_caja (
            id {pk_autoincrement_sql()},
            fecha TEXT,
            total_ventas REAL,
            usuario_id INTEGER
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cierre_detalle (
            id {pk_autoincrement_sql()},
            cierre_id INTEGER,
            producto TEXT,
            cantidad INTEGER
        )
        """
    )

    conn.commit()
    conn.close()

    asegurar_columna("ordenes", "fecha", "TEXT")
    asegurar_columna("ordenes", "cierre_id", "INTEGER")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE ordenes
        SET fecha = substr(fecha_hora, 1, 10)
        WHERE (fecha IS NULL OR fecha = '')
        AND fecha_hora IS NOT NULL
        """
    )
    conn.commit()
    conn.close()


def crear_usuarios_iniciales():
    conn = get_connection()
    cursor = conn.cursor()

    usuarios = [
        ("Gaby", "2807"),
        ("Julissa", "2002"),
        ("Monica", "1310"),
        ("Josue", "0510"),
        ("Fabian", "2107"),
        ("Oscar", "1810"),
    ]

    for nombre, pin in usuarios:
        cursor.execute("SELECT id FROM usuarios WHERE nombre=?", (nombre,))
        existe = cursor.fetchone()

        if existe:
            cursor.execute("UPDATE usuarios SET pin=? WHERE id=?", (pin, existe[0]))
        else:
            cursor.execute(
                "INSERT INTO usuarios (nombre, pin) VALUES (?, ?)",
                (nombre, pin),
            )

    conn.commit()
    conn.close()


def crear_tablas_inventario():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS inventario (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            stock_actual REAL,
            unidad TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS compras (
            id {pk_autoincrement_sql()},
            producto TEXT,
            cantidad REAL,
            precio_total REAL,
            proveedor TEXT,
            fecha TEXT,
            usuario_id INTEGER
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS producciones (
            id {pk_autoincrement_sql()},
            producto_origen TEXT,
            cantidad_origen REAL,
            producto_resultado TEXT,
            cantidad_resultado REAL,
            costo_total REAL,
            fecha TEXT,
            usuario_id INTEGER
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS proveedores (
            id {pk_autoincrement_sql()},
            nombre TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS productos_base (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            unidad TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def usuario_activo():
    return session.get("usuario_nombre", "")


def usuario_es_admin_cierre():
    return session.get("usuario") == "Josue"


def usuario_puede_reimprimir_cocina():
    return session.get("usuario") == "Josue"


def crear_datos_base_inventario():
    conn = get_connection()
    cursor = conn.cursor()

    productos_base = [
        ("Pollo", "kg"),
        ("Cerdo", "kg"),
        ("Camaron", "kg"),
        ("Arroz", "kg"),
        ("Lumpias", "unidad"),
        ("Salsa", "lt"),
        ("Refresco", "unidad"),
    ]

    for nombre, unidad in productos_base:
        cursor.execute(
            "SELECT id FROM productos_base WHERE lower(nombre)=lower(?)",
            (nombre,),
        )
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO productos_base (nombre, unidad)
                VALUES (?, ?)
                """,
                (nombre, unidad),
            )

    conn.commit()
    conn.close()


def obtener_costo_promedio_producto(cursor, producto):
    cursor.execute(
        """
        SELECT costo_promedio
        FROM inventario
        WHERE lower(nombre) = lower(?)
        LIMIT 1
        """,
        (producto,),
    )
    row = cursor.fetchone()
    if row and row[0]:
        return float(row[0])

    cursor.execute(
        """
        SELECT COALESCE(SUM(precio_total), 0), COALESCE(SUM(cantidad), 0)
        FROM compras
        WHERE lower(producto) = lower(?)
        """,
        (producto,),
    )
    total, cantidad = cursor.fetchone()
    if cantidad and cantidad > 0:
        return float(total or 0) / float(cantidad)

    cursor.execute(
        """
        SELECT COALESCE(SUM(costo_total), 0), COALESCE(SUM(cantidad_resultado), 0)
        FROM producciones
        WHERE lower(producto_resultado) = lower(?)
        """,
        (producto,),
    )
    total, cantidad = cursor.fetchone()
    if cantidad and cantidad > 0:
        return float(total or 0) / float(cantidad)

    return 0.0


def estilos_base():
    return """
    :root {
        --rojo-china: #b91c1c;
        --rojo-oscuro: #7f1d1d;
        --dorado: #f59e0b;
        --verde: #15803d;
        --azul: #1d4ed8;
        --gris-fondo: #f3f4f6;
        --texto: #111827;
        --borde: #e5e7eb;
        --sombra: 0 10px 26px rgba(17, 24, 39, 0.12);
    }
    * { box-sizing: border-box; }
    body {
        font-family: Arial, Helvetica, sans-serif;
        color: var(--texto);
        background:
            radial-gradient(circle at top left, rgba(245, 158, 11, 0.14), transparent 28rem),
            linear-gradient(180deg, #fff7ed 0%, var(--gris-fondo) 34%, #eef2f7 100%);
    }
    .header {
        background: linear-gradient(135deg, var(--rojo-oscuro), var(--rojo-china) 58%, #111827);
        color: white;
        padding: 18px 22px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        box-shadow: 0 8px 24px rgba(127, 29, 29, 0.28);
        position: sticky;
        top: 0;
        z-index: 20;
    }
    .titulo { font-size: 26px; font-weight: 900; letter-spacing: 0; }
    .menu-top { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .menu-top a, .volver, .btn-accion, .btn-ver, .btn-cobrar, .btn-acceso {
        color: white;
        text-decoration: none;
        font-weight: 800;
        border-radius: 8px;
        min-height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        box-shadow: 0 3px 10px rgba(17, 24, 39, 0.12);
    }
    .menu-top a { background: rgba(255, 255, 255, 0.16); padding: 10px 13px; font-size: 14px; }
    .menu-top a:hover { background: rgba(255, 255, 255, 0.26); }
    .contenido, .contenedor { max-width: 1280px; margin: 0 auto; }
    .card, .panel-izq, .panel-der, .panel, .login-box {
        border: 1px solid rgba(229, 231, 235, 0.85);
        box-shadow: var(--sombra);
    }
    h1, h2, h3 { letter-spacing: 0; }
    input, select, textarea {
        border: 1px solid #cbd5e1;
        min-height: 46px;
        background: white;
    }
    button, .btn, .btn-agregar, .btn-guardar {
        font-weight: 900;
        min-height: 48px;
        box-shadow: 0 4px 12px rgba(17, 24, 39, 0.14);
    }
    @media (min-width: 900px) {
        .contenedor { flex-direction: row !important; align-items: flex-start; padding: 18px !important; }
        .panel-izq { flex: 0 0 360px; }
        .panel-der { flex: 1; }
        .card { flex-direction: row !important; justify-content: space-between; align-items: center; }
    }
    @media (max-width: 768px) {
        .header { position: static; flex-direction: column; align-items: stretch; }
        .titulo { font-size: 23px; text-align: center; }
        .menu-top { justify-content: stretch; }
        .menu-top a { flex: 1 1 42%; }
    }
    """


def barra_superior(extra_links=""):
    return f"""
    <style>{estilos_base()}</style>
    <div class="header">
        <div class="titulo">🍜 China House POS</div>
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px;">
            <div style="font-size:14px;">👤 Usuario: <b>{usuario_activo()}</b></div>
            <div class="menu-top">
                {extra_links}
                <a href="/logout">🚪 Cerrar sesión</a>
            </div>
        </div>
    </div>
    """


def obtener_inicio_jornada_actual(cursor):
    inicio_hoy = ahora_venezuela().strftime("%Y-%m-%d 00:00:00")

    cursor.execute(
        """
        SELECT fecha
        FROM cierres_caja
        ORDER BY fecha DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    ultimo_cierre = row[0] if row and row[0] else None

    if ultimo_cierre and ultimo_cierre > inicio_hoy:
        return ultimo_cierre

    return inicio_hoy


def texto_numero_orden(numero):
    if numero is None:
        return "Sin numero"
    return f"#{numero}"


def construir_resumen_cierre(cursor):
    tasa = obtener_tasa_actual(cursor)

    cursor.execute(
        """
        SELECT MIN(fecha_hora)
        FROM ordenes
        WHERE cierre_id IS NULL
        """
    )
    row_inicio = cursor.fetchone()
    inicio_jornada = row_inicio[0] if row_inicio and row_inicio[0] else "Sin ordenes pendientes"

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM ordenes
        WHERE cierre_id IS NULL
          AND estado != 'cerrada'
        """,
    )
    ordenes_activas = int(cursor.fetchone()[0] or 0)

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            COALESCE(o.cliente, ''),
            COALESCE(o.descuento, 0),
            COALESCE(SUM(oi.precio), 0)
        FROM ordenes o
        LEFT JOIN orden_items oi ON oi.orden_id = o.id
        WHERE o.cierre_id IS NULL
          AND o.estado = 'cerrada'
        GROUP BY o.id, o.numero_orden, o.cliente, o.descuento
        ORDER BY o.id ASC
        """
    )
    filas_ordenes = cursor.fetchall()

    ordenes_cerradas = []
    ordenes_cerradas_detalle = []
    orden_ids = []
    total_ventas_usd = 0.0
    total_ventas_bs = 0.0

    for orden_id, numero_orden, cliente, descuento_bs, subtotal_usd in filas_ordenes:
        subtotal_usd = a_float(subtotal_usd)
        descuento_bs = a_float(descuento_bs)
        descuento_usd = (descuento_bs / tasa) if tasa else 0.0
        total_neto_usd = max(subtotal_usd - descuento_usd, 0.0)
        total_neto_bs = max((subtotal_usd * tasa) - descuento_bs, 0.0)

        total_ventas_usd += total_neto_usd
        total_ventas_bs += total_neto_bs
        orden_ids.append(orden_id)
        ordenes_cerradas.append((orden_id, numero_orden, descuento_bs))
        ordenes_cerradas_detalle.append(
            {
                "id": orden_id,
                "numero_orden": numero_orden,
                "cliente": cliente,
                "descuento_bs": descuento_bs,
                "subtotal_usd": subtotal_usd,
                "total_neto_usd": total_neto_usd,
                "total_neto_bs": total_neto_bs,
            }
        )

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            COALESCE(o.cliente, ''),
            p.metodo,
            p.monto,
            p.referencia,
            p.fecha
        FROM pagos p
        JOIN ordenes o ON p.orden_id = o.id
        WHERE o.cierre_id IS NULL
          AND o.estado = 'cerrada'
        ORDER BY o.numero_orden ASC, o.id ASC, p.id ASC
        """
    )
    filas_pagos = cursor.fetchall()

    total_pago_movil_bs = 0.0
    total_efectivo_bs = 0.0
    total_efectivo_usd = 0.0
    auditoria_pagos = []

    for orden_id, numero_orden, cliente, metodo, monto, referencia, fecha in filas_pagos:
        metodo = normalizar_metodo_pago(metodo)
        monto = a_float(monto)

        if metodo == "bs_pago_movil":
            total_pago_movil_bs += monto
        elif metodo == "bs_efectivo":
            total_efectivo_bs += monto
        elif metodo == "usd":
            total_efectivo_usd += monto

        auditoria_pagos.append(
            {
                "orden_id": orden_id,
                "numero_orden": numero_orden,
                "cliente": cliente,
                "metodo": metodo,
                "metodo_label": etiqueta_metodo_pago(metodo),
                "monto": monto,
                "referencia": referencia or "",
                "fecha": fecha or "",
            }
        )

    cursor.execute(
        """
        SELECT oi.producto, COUNT(oi.id) as cantidad
        FROM orden_items oi
        JOIN ordenes o ON oi.orden_id = o.id
        WHERE o.cierre_id IS NULL
          AND o.estado = 'cerrada'
        GROUP BY oi.producto
        ORDER BY cantidad DESC, oi.producto ASC
        """
    )
    productos = cursor.fetchall()

    total_cobrado_equiv_bs = (
        total_pago_movil_bs + total_efectivo_bs + (total_efectivo_usd * tasa)
    )
    total_cobrado_equiv_usd = total_efectivo_usd + (
        ((total_pago_movil_bs + total_efectivo_bs) / tasa) if tasa else 0.0
    )
    diferencia_usd = total_ventas_usd - total_cobrado_equiv_usd
    diferencia_bs = total_ventas_bs - total_cobrado_equiv_bs

    return {
        "inicio_jornada": inicio_jornada,
        "tasa": tasa,
        "ordenes_activas": ordenes_activas,
        "ordenes_cerradas": ordenes_cerradas,
        "ordenes_cerradas_detalle": ordenes_cerradas_detalle,
        "orden_ids": orden_ids,
        "cantidad_ordenes_cerradas": len(ordenes_cerradas),
        "total_ventas_usd": round(total_ventas_usd, 2),
        "total_ventas_bs": round(total_ventas_bs, 2),
        "total_ventas": round(total_ventas_bs, 2),
        "total_pago_movil_bs": round(total_pago_movil_bs, 2),
        "total_efectivo_bs": round(total_efectivo_bs, 2),
        "total_efectivo_usd": round(total_efectivo_usd, 2),
        "total_cobrado_equiv_bs": round(total_cobrado_equiv_bs, 2),
        "total_cobrado_equiv_usd": round(total_cobrado_equiv_usd, 2),
        "total_cobrado": round(total_cobrado_equiv_bs, 2),
        "diferencia_usd": round(diferencia_usd, 2),
        "diferencia_bs": round(diferencia_bs, 2),
        "diferencia": round(diferencia_bs, 2),
        "auditoria_pagos": auditoria_pagos,
        "productos": productos,
    }


def resumen_cierre_pendiente():
    conn = get_connection()
    cursor = conn.cursor()
    resumen = construir_resumen_cierre(cursor)
    conn.close()
    return resumen


def fechas_reporte_desde_request():
    hoy = ahora_venezuela().strftime("%Y-%m-%d")
    desde = (request.args.get("desde") or hoy).strip()
    hasta = (request.args.get("hasta") or hoy).strip()

    try:
        datetime.datetime.strptime(desde, "%Y-%m-%d")
    except Exception:
        desde = hoy

    try:
        datetime.datetime.strptime(hasta, "%Y-%m-%d")
    except Exception:
        hasta = hoy

    if desde > hasta:
        desde, hasta = hasta, desde

    return desde, hasta


def construir_reporte_rango(cursor, desde, hasta):
    inicio = f"{desde} 00:00:00"
    fin = f"{hasta} 23:59:59"
    tasa = obtener_tasa_actual(cursor)

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            o.fecha_hora,
            COALESCE(o.tipo, ''),
            COALESCE(o.referencia, ''),
            COALESCE(o.cliente, ''),
            COALESCE(o.descuento, 0),
            o.cierre_id,
            COALESCE(u.nombre, ''),
            COALESCE(SUM(oi.precio), 0)
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        LEFT JOIN orden_items oi ON oi.orden_id = o.id
        WHERE o.estado = 'cerrada'
          AND o.fecha_hora >= ?
          AND o.fecha_hora <= ?
        GROUP BY o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia,
                 o.cliente, o.descuento, o.cierre_id, u.nombre
        ORDER BY o.fecha_hora ASC, o.id ASC
        """,
        (inicio, fin),
    )
    ordenes_db = cursor.fetchall()

    ventas_por_orden = []
    ventas_por_dia = defaultdict(lambda: {"total_usd": 0.0, "total_bs": 0.0, "ordenes": 0})
    total_vendido_usd = 0.0
    total_vendido_bs = 0.0
    orden_ids = []

    for orden in ordenes_db:
        (
            orden_id,
            numero_orden,
            fecha_hora,
            tipo,
            referencia,
            cliente,
            descuento_bs,
            cierre_id,
            mesonera,
            subtotal_usd,
        ) = orden
        subtotal_usd = a_float(subtotal_usd)
        descuento_bs = a_float(descuento_bs)
        descuento_usd = (descuento_bs / tasa) if tasa else 0.0
        total_neto_usd = max(subtotal_usd - descuento_usd, 0.0)
        total_neto_bs = max((subtotal_usd * tasa) - descuento_bs, 0.0)
        dia = (fecha_hora or "")[:10]

        total_vendido_usd += total_neto_usd
        total_vendido_bs += total_neto_bs
        orden_ids.append(orden_id)
        ventas_por_dia[dia]["total_usd"] += total_neto_usd
        ventas_por_dia[dia]["total_bs"] += total_neto_bs
        ventas_por_dia[dia]["ordenes"] += 1

        ventas_por_orden.append(
            {
                "orden_id": orden_id,
                "numero_orden": numero_orden,
                "fecha_hora": fecha_hora,
                "tipo": tipo,
                "referencia": referencia,
                "cliente": cliente,
                "cierre_id": cierre_id,
                "mesonera": mesonera,
                "subtotal_usd": round(subtotal_usd, 2),
                "descuento_bs": round(descuento_bs, 2),
                "total_usd": round(total_neto_usd, 2),
                "total_bs": round(total_neto_bs, 2),
            }
        )

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            o.fecha_hora,
            COALESCE(o.cliente, ''),
            p.metodo,
            p.monto,
            COALESCE(p.referencia, ''),
            COALESCE(p.fecha, '')
        FROM pagos p
        JOIN ordenes o ON p.orden_id = o.id
        WHERE o.estado = 'cerrada'
          AND o.fecha_hora >= ?
          AND o.fecha_hora <= ?
        ORDER BY o.fecha_hora ASC, o.id ASC, p.id ASC
        """,
        (inicio, fin),
    )
    pagos_db = cursor.fetchall()

    pagos = []
    metodos_pago = defaultdict(lambda: {"cantidad": 0, "total_bs": 0.0, "total_usd": 0.0})
    total_pago_movil_bs = 0.0
    total_efectivo_bs = 0.0
    total_efectivo_usd = 0.0

    for orden_id, numero_orden, fecha_hora, cliente, metodo, monto, referencia, fecha_pago in pagos_db:
        metodo = normalizar_metodo_pago(metodo)
        monto = a_float(monto)
        equiv_bs, equiv_usd = convertir_pago_equivalente(metodo, monto, tasa)

        if metodo == "bs_pago_movil":
            total_pago_movil_bs += monto
        elif metodo == "bs_efectivo":
            total_efectivo_bs += monto
        elif metodo == "usd":
            total_efectivo_usd += monto

        metodos_pago[metodo]["cantidad"] += 1
        metodos_pago[metodo]["total_bs"] += equiv_bs
        metodos_pago[metodo]["total_usd"] += equiv_usd

        pagos.append(
            {
                "orden_id": orden_id,
                "numero_orden": numero_orden,
                "fecha_hora": fecha_hora,
                "cliente": cliente,
                "metodo": metodo,
                "metodo_label": etiqueta_metodo_pago(metodo),
                "monto": round(monto, 2),
                "referencia": referencia,
                "fecha_pago": fecha_pago,
                "equivalente_bs": round(equiv_bs, 2),
                "equivalente_usd": round(equiv_usd, 2),
            }
        )

    cursor.execute(
        """
        SELECT oi.producto, COUNT(oi.id) as cantidad
        FROM orden_items oi
        JOIN ordenes o ON oi.orden_id = o.id
        WHERE o.estado = 'cerrada'
          AND o.fecha_hora >= ?
          AND o.fecha_hora <= ?
        GROUP BY oi.producto
        ORDER BY cantidad DESC, oi.producto ASC
        """,
        (inicio, fin),
    )
    platos_vendidos = [
        {"producto": producto, "cantidad": int(cantidad or 0)}
        for producto, cantidad in cursor.fetchall()
    ]

    total_equiv_bs = total_pago_movil_bs + total_efectivo_bs + (total_efectivo_usd * tasa)
    total_equiv_usd = total_efectivo_usd + (
        ((total_pago_movil_bs + total_efectivo_bs) / tasa) if tasa else 0.0
    )

    ventas_por_dia_lista = []
    for dia in sorted(ventas_por_dia):
        datos = ventas_por_dia[dia]
        ventas_por_dia_lista.append(
            {
                "fecha": dia,
                "ordenes": datos["ordenes"],
                "total_usd": round(datos["total_usd"], 2),
                "total_bs": round(datos["total_bs"], 2),
            }
        )

    metodos_pago_lista = []
    for metodo, datos in sorted(metodos_pago.items()):
        metodos_pago_lista.append(
            {
                "metodo": metodo,
                "metodo_label": etiqueta_metodo_pago(metodo),
                "cantidad": datos["cantidad"],
                "total_bs": round(datos["total_bs"], 2),
                "total_usd": round(datos["total_usd"], 2),
            }
        )

    return {
        "desde": desde,
        "hasta": hasta,
        "inicio": inicio,
        "fin": fin,
        "tasa": round(tasa, 2),
        "total_vendido_usd": round(total_vendido_usd, 2),
        "total_vendido_bs": round(total_vendido_bs, 2),
        "total_pago_movil_bs": round(total_pago_movil_bs, 2),
        "total_efectivo_bs": round(total_efectivo_bs, 2),
        "total_efectivo_usd": round(total_efectivo_usd, 2),
        "total_equiv_usd": round(total_equiv_usd, 2),
        "total_equiv_bs": round(total_equiv_bs, 2),
        "cantidad_ordenes": len(orden_ids),
        "ventas_por_orden": ventas_por_orden,
        "pagos": pagos,
        "platos_vendidos": platos_vendidos,
        "ventas_por_dia": ventas_por_dia_lista,
        "metodos_pago": metodos_pago_lista,
    }


def xml_cell(valor):
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return f"<c><v>{valor}</v></c>"
    texto = html_lib.escape("" if valor is None else str(valor), quote=True)
    return f'<c t="inlineStr"><is><t>{texto}</t></is></c>'


def xml_sheet(filas):
    rows = []
    for idx, fila in enumerate(filas, start=1):
        cells = "".join(xml_cell(valor) for valor in fila)
        rows.append(f'<row r="{idx}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData>"
        "</worksheet>"
    )


def generar_xlsx(hojas):
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(hojas) + 1)
            )
            + "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{html_lib.escape(nombre, quote=True)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, (nombre, _) in enumerate(hojas, start=1)
            )
            + "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(hojas) + 1)
            )
            + "</Relationships>",
        )
        for i, (_, filas) in enumerate(hojas, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml_sheet(filas))

    salida.seek(0)
    return salida.getvalue()


@app.before_request
def proteger_sistema():
    rutas_publicas = {"login", "static", "ordenes_cocina", "facturas_pendientes"}
    rutas_admin = {
        "cierre",
        "cerrar_jornada",
        "cerrar_dia",
        "exportar",
        "reportes",
        "exportar_reporte",
        "dashboard",
        "revertir_orden_cierre",
        "eliminar_orden",
        "produccion",
    }

    if request.endpoint in rutas_publicas:
        return

    if not session.get("usuario_id"):
        return redirect("/login")

    if request.endpoint in rutas_admin and not usuario_es_admin_cierre():
        return "Acceso denegado", 403


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS productos (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            precio REAL
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cierres (
            id {pk_autoincrement_sql()},
            fecha_inicio TEXT,
            fecha_fin TEXT,
            total_ordenes INTEGER,
            total_ventas_usd REAL,
            total_ventas_bs REAL,
            total_pagado_usd REAL,
            total_pagado_bs REAL,
            diferencia REAL,
            fecha_cierre TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS categorias (
            id {pk_autoincrement_sql()},
            nombre TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS usuarios (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            pin TEXT
        )
        """
    )

    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        categorias = [
            ("Solo para ti",),
            ("Para compartir",),
            ("Banquete imperial",),
            ("Platos adicionales",),
            ("Bebidas",),
            ("Delivery",),
            ("Extras",),
        ]
        cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", categorias)

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ordenes (
            id {pk_autoincrement_sql()},
            numero_orden INTEGER,
            fecha_hora TEXT,
            tipo TEXT,
            referencia TEXT,
            cliente TEXT,
            estado TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS orden_items (
            id {pk_autoincrement_sql()},
            orden_id INTEGER,
            producto TEXT,
            precio REAL
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS pagos (
            id {pk_autoincrement_sql()},
            orden_id INTEGER,
            metodo TEXT,
            monto REAL,
            referencia TEXT,
            fecha TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS tasa (
            id {pk_autoincrement_sql()},
            valor REAL
        )
        """
    )

    cursor.execute("SELECT COUNT(*) FROM tasa")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO tasa (valor) VALUES (36)")

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ingredientes (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            unidad TEXT,
            stock REAL
        )
        """
    )

    conn.commit()
    conn.close()

    asegurar_columna("productos", "categoria_id", "INTEGER")
    asegurar_columna("ordenes", "fecha", "TEXT")
    asegurar_columna("ordenes", "descuento", "REAL DEFAULT 0")
    asegurar_columna("ordenes", "observacion", "TEXT")
    asegurar_columna("ordenes", "usuario_id", "INTEGER")
    asegurar_columna("ordenes", "cierre_id", "INTEGER")
    asegurar_columna("ordenes", "reimpresion_token", "TEXT")
    asegurar_columna_facturar()
    crear_tablas_cierre_jornada()
    crear_tablas_inventario()
    asegurar_columna("inventario", "costo_promedio", "REAL DEFAULT 0")
    crear_usuarios_iniciales()
    crear_datos_base_inventario()


def cargar_productos():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    cursor.execute("SELECT id, nombre FROM categorias")
    cat_dict = {nombre: id for id, nombre in cursor.fetchall()}

    productos = [
        ("Solo para ti Cerdo", 4.5, "Solo para ti"),
        ("Solo para ti Pollo", 4.5, "Solo para ti"),
        ("Solo para ti Cerdo-Pollo", 5.0, "Solo para ti"),
        ("Solo para ti Pollo-Camaron", 5.0, "Solo para ti"),
        ("Solo para ti Premium", 6.0, "Solo para ti"),
        ("Para compartir Cerdo", 7.0, "Para compartir"),
        ("Para compartir Pollo", 7.0, "Para compartir"),
        ("Para compartir Cerdo-Pollo", 8.0, "Para compartir"),
        ("Para compartir Pollo-Camaron", 8.0, "Para compartir"),
        ("Para compartir Premium", 9.0, "Para compartir"),
        ("Banquete Imperial Cerdo", 10.0, "Banquete imperial"),
        ("Banquete Imperial Pollo", 10.0, "Banquete imperial"),
        ("Banquete Imperial Cerdo-Pollo", 11.0, "Banquete imperial"),
        ("Banquete Imperial Pollo-Camaron", 11.0, "Banquete imperial"),
        ("Banquete Imperial Premium", 13.0, "Banquete imperial"),
        ("Racion de Lumpias", 4.0, "Platos adicionales"),
        ("Media racion de Lumpias", 2.5, "Platos adicionales"),
        ("Shop Suey", 4.0, "Platos adicionales"),
        ("Racion de Pollo Agridulce", 5.0, "Platos adicionales"),
        ("Refresco 1 Lt", 1.0, "Bebidas"),
        ("Refresco 1.5 Lt", 1.5, "Bebidas"),
        ("Delivery 0.5", 0.5, "Delivery"),
        ("Delivery 1", 1.0, "Delivery"),
        ("Delivery 1.5", 1.5, "Delivery"),
        ("Delivery 2", 2.0, "Delivery"),
        ("Delivery 2.5", 2.5, "Delivery"),
        ("Delivery 3", 3.0, "Delivery"),
        ("Delivery 3.5", 3.5, "Delivery"),
        ("Extra de Salsa", 0.25, "Extras"),
    ]

    for nombre, precio, categoria in productos:
        categoria_id = cat_dict.get(categoria)
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id) VALUES (?, ?, ?)",
            (nombre, precio, categoria_id),
        )

    conn.commit()
    conn.close()


def siguiente_numero():
    conn = get_connection()
    cursor = conn.cursor()
    inicio_jornada = obtener_inicio_jornada_actual(cursor)

    cursor.execute(
        """
        SELECT MAX(numero_orden)
        FROM ordenes
        WHERE fecha_hora >= ?
          AND estado IN ('en cocina', 'cerrada')
          AND numero_orden IS NOT NULL
        """,
        (inicio_jornada,),
    )
    ultimo = cursor.fetchone()[0]
    conn.close()
    return 1 if ultimo is None else ultimo + 1


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM usuarios ORDER BY nombre")
    usuarios = cursor.fetchall()

    error = ""

    if request.method == "POST":
        usuario_id = request.form.get("usuario_id")
        pin = request.form.get("pin", "").strip()

        cursor.execute(
            "SELECT id, nombre FROM usuarios WHERE id=? AND pin=?",
            (usuario_id, pin),
        )
        usuario = cursor.fetchone()

        if usuario:
            session["usuario_id"] = usuario[0]
            session["usuario_nombre"] = usuario[1]
            session["usuario"] = usuario[1]
            conn.close()
            return redirect("/")

        error = "Usuario o PIN incorrecto"

    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    """ + estilos_base() + """
    body { font-family: Arial; margin: 0; background: #f5f6fa; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
    .login-box { background: white; width: 92%; max-width: 420px; padding: 28px; border-radius: 12px; box-shadow: 0 18px 40px rgba(127,29,29,0.18); }
    h1 { text-align: center; margin-top: 0; }
    input, select { width: 100%; padding: 14px; margin: 8px 0; border-radius: 6px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 15px; background: linear-gradient(135deg, #15803d, #16a34a); color: white; border: none; border-radius: 8px; font-size: 18px; margin-top: 10px; }
    .error { background: #fdecea; color: #c0392b; padding: 10px; border-radius: 6px; margin-bottom: 10px; text-align: center; }
    </style>
    </head>
    <body>
    <div class="login-box">
        <h1>🔐 Login Mesonera</h1>
    """

    if error:
        html += f"<div class='error'>{error}</div>"

    html += """
        <form method="post">
            <label>Usuario</label>
            <select name="usuario_id" required>
    """

    for usuario in usuarios:
        html += f"<option value='{usuario[0]}'>{usuario[1]}</option>"

    html += """
            </select>
            <label>PIN</label>
            <input type="password" name="pin" required placeholder="Ingrese PIN">
            <button type="submit">🔐 Entrar</button>
        </form>
    </div>
    </body>
    </html>
    """

    return html


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
def index():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
               o.estado, o.observacion, o.descuento, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.cierre_id IS NULL
        ORDER BY o.id DESC
        """
    )
    ordenes = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .header { background: #2c3e50; color: white; padding: 15px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }
    .titulo { font-size: 22px; font-weight: bold; }
    .menu-top { display: flex; flex-wrap: wrap; gap: 5px; justify-content: flex-end; }
    .menu-top a { color: white; text-decoration: none; background: #34495e; padding: 10px; border-radius: 5px; font-size: 13px; flex: 1 1 45%; text-align: center; }
    .contenedor { display: flex; padding: 10px; gap: 10px; flex-direction: column; }
    .panel-izq, .panel-der { width: 100%; background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    input, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 16px; background: #27ae60; color: white; border: none; border-radius: 5px; margin-top: 10px; font-size: 18px; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); display: flex; flex-direction: column; gap: 10px; font-size: 18px; }
    .estado { padding: 5px 10px; border-radius: 5px; color: white; font-size: 12px; display: inline-block; }
    .btn-ver, .btn-cobrar { display: block; width: 100%; text-align: center; padding: 10px; border-radius: 5px; text-decoration: none; margin-bottom: 5px; }
    .btn-ver { background: #3498db; color: white; }
    .btn-cobrar { background: #27ae60; color: white; }
    .btn-cierre-jornada { display:block; width:100%; padding:16px; background:#c0392b; color:white; text-decoration:none; text-align:center; border-radius:5px; margin-top:12px; font-size:18px; box-sizing:border-box; }
    .mesonera { font-size: 14px; color: #555; margin-top: 4px; }
    </style>
    </head>
    <body>
    """

    links_admin = ""
    if usuario_es_admin_cierre():
        links_admin = """
        <a href="/exportar">📤 Exportar</a>
        <a href="/cierre">📊 Cierre</a>
        <a href="/reportes">📊 Reportes</a>
        <a href="/cerrar_jornada">🔒 Cerrar jornada</a>
        <a href="/produccion">🏭 Producción</a>
        """

    html += barra_superior(
        f"""
        <a href="/cambiar_tasa">💱 Tasa</a>
        {links_admin}
        <a href="/menu">📋 Menú</a>
        <a href="/inventario">📦 Inventario</a>
        <a href="/compras">🛒 Compras</a>
        <a href="/cocina">🍳 Cocina</a>
        """
    )

    boton_cerrar_jornada = ""
    if usuario_es_admin_cierre():
        boton_cerrar_jornada = (
            '<a href="/cerrar_jornada" class="btn-cierre-jornada">🔒 Confirmar cierre de jornada</a>'
        )

    html += f"""
    <div class="contenedor">
        <div class="panel-izq">
            <h3>🆕 Nueva Orden</h3>
            <form action="/crear_orden" method="post">
                <label>Tipo</label>
                <select name="tipo">
                    <option value="Mesa">Mesa</option>
                    <option value="Delivery">Delivery</option>
                    <option value="Para llevar">Pick Up</option>
                </select>
                <label>Referencia</label>
                <input name="referencia">
                <label>👤 Cliente</label>
                <input name="cliente">
                <button type="submit">🆕 Crear Orden</button>
            </form>
            {boton_cerrar_jornada}
        </div>
        <div class="panel-der">
    """

    html += "<h3>🧾 Ordenes activas</h3>"
    for o in ordenes:
        if o[6] != "abierta":
            continue
        html += f"""
        <div class="card">
            <div>
                <b>Orden {texto_numero_orden(o[1])}</b><br>
                {o[3]} - {o[4]}<br>
                Cliente: {o[5] if o[5] else '-'}
                <div class="mesonera">👩 Mesonera: {o[9] if o[9] else '-'}</div>
            </div>
            <div>
                <span class="estado" style="background:#e74c3c;">ABIERTA</span>
                <a href="/orden/{o[0]}" class="btn-ver">🔍 Ver detalle</a>
                <a href="/cobrar/{o[0]}" class="btn-cobrar" onclick="return confirm('⚠️ Esta orden aún no ha sido enviada a cocina. ¿Seguro que quieres continuar con el cobro?')">💵 Cobrar</a>
            </div>
        </div>
        """

    html += "<h3>🍳 En cocina</h3>"
    for o in ordenes:
        if o[6] != "en cocina":
            continue
        html += f"""
        <div class="card" style="background:#fff3cd;">
            <div>
                <b>Orden {texto_numero_orden(o[1])}</b><br>
                {o[3]} - {o[4]}<br>
                Cliente: {o[5] if o[5] else '-'}
                <div class="mesonera">👩 Mesonera: {o[9] if o[9] else '-'}</div>
            </div>
            <div>
                <span class="estado" style="background:#e67e22;">EN COCINA</span>
                <a href="/orden/{o[0]}" class="btn-ver">🔍 Ver detalle</a>
                <a href="/cobrar/{o[0]}" class="btn-cobrar">💵 Cobrar</a>
            </div>
        </div>
        """

    html += "<h3>📚 Historial del dia</h3>"
    for o in ordenes:
        if o[6] != "cerrada":
            continue
        html += f"""
        <div style="background:#ecf0f1; padding:10px; margin-bottom:8px; border-radius:5px;">
            <div style="font-weight:bold;">
                Orden {texto_numero_orden(o[1])} - {o[5] if o[5] else '-'}
            </div>
            <div class="mesonera">👩 Mesonera: {o[9] if o[9] else '-'}</div>
            <div style="margin-top:5px;">
                <a href="/orden/{o[0]}" style="color:#2980b9; text-decoration:none;">🔍 Ver detalle</a>
            </div>
        </div>
        """

    html += """
        </div>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/menu", methods=["GET", "POST"])
def menu():
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        nombre = request.form["nombre"]
        precio = float(request.form["precio"])
        categoria_id = request.form["categoria"]
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id) VALUES (?, ?, ?)",
            (nombre, precio, categoria_id),
        )
        conn.commit()

    cursor.execute("SELECT id, nombre FROM categorias")
    categorias = cursor.fetchall()

    cursor.execute(
        """
        SELECT p.id, p.nombre, p.precio, c.nombre
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        """
    )
    productos = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .header { background: #2c3e50; color: white; padding: 15px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }
    .titulo { font-size: 22px; font-weight: bold; }
    .menu-top { display: flex; flex-wrap: wrap; gap: 5px; justify-content: flex-end; }
    .menu-top a { color: white; text-decoration: none; background: #34495e; padding: 10px; border-radius: 5px; font-size: 13px; flex: 1 1 45%; text-align: center; }
    .contenido { padding: 10px; }
    h1 { text-align: center; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    input, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 5px; background: #27ae60; color: white; cursor: pointer; }
    .producto { background: white; padding: 10px; margin-bottom: 8px; border-radius: 5px; font-size: 16px; }
    .acciones { margin-top: 8px; display: flex; gap: 10px; }
    .acciones a { text-decoration: none; color: white; padding: 8px 10px; border-radius: 5px; font-size: 14px; }
    .editar { background: #2980b9; }
    .eliminar { background: #c0392b; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: #7f8c8d; color: white; text-decoration: none; border-radius: 5px; }
    </style>
    </head>
    <body>
    """

    html += barra_superior('<a href="/">🏠 Inicio</a>')
    html += """
    <div class="contenido">
    <h1>📋 Menú</h1>
    <div class="card">
        <form method="post">
            <input name="nombre" placeholder="Nombre del producto" required>
            <input name="precio" type="number" step="0.01" placeholder="Precio USD" required>
            <select name="categoria">
    """

    for c in categorias:
        html += f"<option value='{c[0]}'>{c[1]}</option>"

    html += """
            </select>
            <button>➕ Agregar producto</button>
        </form>
    </div>
    <h2>🍽️ Productos</h2>
    """

    for p in productos:
        html += f"""
        <div class="producto">
            {p[1]} - ${p[2]} <br>
            <small>{p[3] if p[3] else ''}</small>
            <div class="acciones">
                <a class="editar" href="/editar_producto/{p[0]}">✏️ Editar</a>
                <a class="eliminar" href="/eliminar_producto/{p[0]}">🗑️ Eliminar</a>
            </div>
        </div>
        """

    html += """
    <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/inventario")
def inventario():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT nombre, stock_actual, unidad
        FROM inventario
        ORDER BY nombre ASC
        """
    )
    productos = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .contenido { padding: 10px; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    .accesos { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
    .btn-acceso { display: block; text-align: center; padding: 16px; background: #34495e; color: white; text-decoration: none; border-radius: 8px; font-size: 18px; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: #7f8c8d; color: white; text-decoration: none; border-radius: 5px; }
    @media (max-width: 768px) { .accesos { grid-template-columns: 1fr; } }
    </style>
    </head>
    <body>
    """

    produccion_link = '<a href="/produccion">🏭 Producción</a>' if usuario_es_admin_cierre() else ""
    html += barra_superior(
        f'<a href="/">🏠 Inicio</a><a href="/compras">🛒 Compras</a>{produccion_link}'
    )
    html += """
    <div class="contenido">
        <h1>📦 Inventario</h1>
        <div class="accesos">
            <a href="/productos_base" class="btn-acceso">📦 Productos base</a>
            <a href="/proveedores" class="btn-acceso">🤝 Proveedores</a>
        </div>
    """

    if not productos:
        html += """
        <div class="card">
            No hay productos registrados en inventario.
        </div>
        """
    else:
        for producto in productos:
            html += f"""
            <div class="card">
                <b>{producto[0]}</b><br>
                Stock actual: {round(producto[1] or 0, 2)}<br>
                Unidad: {producto[2] if producto[2] else '-'}
            </div>
            """

    html += """
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/compras", methods=["GET", "POST"])
def compras():
    compras_temporales = session.get("compras_temporales", [])
    conn = get_connection()
    cursor = conn.cursor()
    error = ""

    cursor.execute(
        """
        SELECT id, nombre, unidad
        FROM productos_base
        ORDER BY nombre ASC
        """
    )
    productos_base = cursor.fetchall()

    cursor.execute(
        """
        SELECT id, nombre
        FROM proveedores
        ORDER BY nombre ASC
        """
    )
    proveedores = cursor.fetchall()

    if request.method == "POST":
        accion = request.form.get("accion", "agregar").strip()

        if accion == "agregar":
            producto_base_id = request.form.get("producto_base_id", "").strip()
            proveedor_id = request.form.get("proveedor_id", "").strip()

            try:
                cantidad = float(request.form.get("cantidad", 0) or 0)
            except Exception:
                cantidad = 0

            if producto_base_id == "" or cantidad <= 0:
                error = "Debes seleccionar un producto y una cantidad valida"
            else:
                cursor.execute(
                    """
                    SELECT nombre, unidad
                    FROM productos_base
                    WHERE id=?
                    """,
                    (producto_base_id,),
                )
                producto_row = cursor.fetchone()

                proveedor = ""
                if proveedor_id != "":
                    cursor.execute(
                        """
                        SELECT nombre
                        FROM proveedores
                        WHERE id=?
                        """,
                        (proveedor_id,),
                    )
                    proveedor_row = cursor.fetchone()
                    if not proveedor_row:
                        error = "Proveedor no valido"
                    else:
                        proveedor = proveedor_row[0]

                if not error:
                    if not producto_row:
                        error = "Producto no valido"
                    else:
                        compras_temporales.append(
                            {
                                "producto": producto_row[0],
                                "unidad": producto_row[1] if producto_row[1] else "unidad",
                                "cantidad": cantidad,
                                "proveedor": proveedor,
                            }
                        )
                        session["compras_temporales"] = compras_temporales
                        conn.close()
                        return redirect("/compras")

        elif accion == "eliminar":
            try:
                indice = int(request.form.get("indice", -1))
            except Exception:
                indice = -1

            if 0 <= indice < len(compras_temporales):
                compras_temporales.pop(indice)
                session["compras_temporales"] = compras_temporales

            conn.close()
            return redirect("/compras")

        elif accion == "guardar":
            if not compras_temporales:
                error = "No hay compras para guardar"
            else:
                fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
                usuario_id = session.get("usuario_id")

                for item in compras_temporales:
                    cursor.execute(
                        """
                        INSERT INTO compras (producto, cantidad, precio_total, proveedor, fecha, usuario_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item["producto"],
                            item["cantidad"],
                            0,
                            item["proveedor"],
                            fecha,
                            usuario_id,
                        ),
                    )

                    cursor.execute(
                        """
                        SELECT id, stock_actual
                        FROM inventario
                        WHERE lower(nombre) = lower(?)
                        """,
                        (item["producto"],),
                    )
                    inventario_item = cursor.fetchone()

                    if inventario_item:
                        nuevo_stock = float(inventario_item[1] or 0) + float(item["cantidad"] or 0)
                        cursor.execute(
                            """
                            UPDATE inventario
                            SET stock_actual=?, unidad=?
                            WHERE id=?
                            """,
                            (nuevo_stock, item["unidad"], inventario_item[0]),
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO inventario (nombre, stock_actual, unidad, costo_promedio)
                            VALUES (?, ?, ?, ?)
                            """,
                            (item["producto"], item["cantidad"], item["unidad"], 0),
                        )

                conn.commit()
                session["compras_temporales"] = []
                conn.close()
                return redirect("/inventario")

    cursor.execute(
        """
        SELECT producto, cantidad, precio_total, proveedor, fecha
        FROM compras
        ORDER BY id DESC
        LIMIT 20
        """
    )
    historial = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .contenido { padding: 10px; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    input, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 5px; color: white; cursor: pointer; }
    .error { background: #fdecea; color: #c0392b; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    .grid-form { display: grid; grid-template-columns: 2fr 1fr 2fr; gap: 10px; align-items: end; }
    .btn-agregar { background: #27ae60; margin-top: 10px; }
    .item-lista { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 0; border-bottom: 1px solid #eee; }
    .item-lista:last-child { border-bottom: none; }
    .detalle-item { font-size: 17px; }
    .detalle-item small { display: block; margin-top: 4px; color: #7f8c8d; font-size: 13px; }
    .btn-eliminar { background: #c0392b; padding: 10px 12px; width: auto; }
    .btn-guardar { background: #2980b9; }
    .lista-vacia { color: #7f8c8d; text-align: center; }
    .resumen-lista { font-size: 18px; font-weight: bold; margin-top: 12px; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: #7f8c8d; color: white; text-decoration: none; border-radius: 5px; }
    @media (max-width: 768px) { .grid-form { grid-template-columns: 1fr; } }
    </style>
    </head>
    <body>
    """

    produccion_link = '<a href="/produccion">🏭 Producción</a>' if usuario_es_admin_cierre() else ""
    html += barra_superior(
        f'<a href="/">🏠 Inicio</a><a href="/inventario">📦 Inventario</a>{produccion_link}'
    )
    html += """
    <div class="contenido">
        <h1>🛒 Compras</h1>
        <div class="card">
    """

    if error:
        html += f"<div class='error'>{error}</div>"

    if not productos_base or not proveedores:
        html += """
            Debes registrar al menos un producto base y un proveedor antes de cargar compras.
        </div>
        <h2>Lista temporal</h2>
        """
    else:
        html += """
            <form method="post">
                <input type="hidden" name="accion" value="agregar">
                <div class="grid-form">
                    <div>
                        <label>Producto</label>
                        <select name="producto_base_id" required>
                            <option value="">Seleccione producto</option>
        """

        for producto in productos_base:
            html += f"<option value='{producto[0]}'>{producto[1]} ({producto[2] if producto[2] else '-'})</option>"

        html += """
                        </select>
                    </div>
                    <div>
                        <label>Cantidad</label>
                        <input id="cantidad" name="cantidad" type="number" step="0.01" placeholder="0" required autofocus>
                    </div>
                    <div>
                        <label>Proveedor</label>
                        <select name="proveedor_id">
                            <option value="">Sin proveedor</option>
        """

        for proveedor in proveedores:
            html += f"<option value='{proveedor[0]}'>{proveedor[1]}</option>"

        html += """
                        </select>
                    </div>
                </div>
                <button type="submit" class="btn-agregar">➕ Agregar</button>
            </form>
        </div>
        <h2>Lista temporal</h2>
        """

    if not compras_temporales:
        html += """
        <div class="card">
            <div class="lista-vacia">No hay productos agregados.</div>
        </div>
        """
    else:
        cantidad_total = 0
        html += "<div class='card'>"
        for idx, compra in enumerate(compras_temporales):
            cantidad_total += float(compra["cantidad"] or 0)
            html += f"""
            <div class="item-lista">
                <div class="detalle-item">
                    <b>{compra["producto"]}</b><br>
                    {round(compra["cantidad"] or 0, 2)} {compra["unidad"]}
                    <small>Proveedor: {compra["proveedor"] if compra["proveedor"] else 'Sin proveedor'}</small>
                </div>
                <form method="post" style="margin:0;">
                    <input type="hidden" name="accion" value="eliminar">
                    <input type="hidden" name="indice" value="{idx}">
                    <button type="submit" class="btn-eliminar">🗑️ Eliminar</button>
                </form>
            </div>
            """
        html += f"""
            <div class="resumen-lista">Items: {len(compras_temporales)} | Cantidad total: {round(cantidad_total, 2)}</div>
            <form method="post" style="margin-top:15px;">
                <input type="hidden" name="accion" value="guardar">
                <button type="submit" class="btn-guardar">💾 Guardar compras</button>
            </form>
        </div>
        """

    html += """
        <h2>🧾 Ultimas compras guardadas</h2>
    """

    if not historial:
        html += """
        <div class="card">
            No hay compras registradas.
        </div>
        """
    else:
        for compra in historial:
            html += f"""
            <div class="card">
                <b>{compra[0]}</b><br>
                Cantidad: {round(compra[1] or 0, 2)}<br>
                Precio total: ${round(compra[2] or 0, 2)}<br>
                Proveedor: {compra[3] if compra[3] else '-'}<br>
                Fecha: {compra[4]}
            </div>
            """

    html += """
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    <script>
    const cantidad = document.getElementById("cantidad");
    if (cantidad) {
        cantidad.focus();
        cantidad.select();
    }
    </script>
    </body>
    </html>
    """
    return html


@app.route("/proveedores", methods=["GET", "POST"])
def proveedores():
    conn = get_connection()
    cursor = conn.cursor()
    error = ""

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if nombre == "":
            error = "Nombre requerido"
        else:
            cursor.execute(
                "SELECT id FROM proveedores WHERE lower(nombre)=lower(?)",
                (nombre,),
            )
            if cursor.fetchone():
                error = "Ese proveedor ya existe"
            else:
                cursor.execute(
                    """
                    INSERT INTO proveedores (nombre)
                    VALUES (?)
                    """,
                    (nombre,),
                )
                conn.commit()
                conn.close()
                return redirect("/proveedores")

    cursor.execute(
        """
        SELECT nombre
        FROM proveedores
        ORDER BY nombre ASC
        """
    )
    lista = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .contenido { padding: 10px; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    input { width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 5px; background: #27ae60; color: white; cursor: pointer; }
    .error { background: #fdecea; color: #c0392b; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: #7f8c8d; color: white; text-decoration: none; border-radius: 5px; }
    </style>
    </head>
    <body>
    """

    html += barra_superior(
        '<a href="/">🏠 Inicio</a><a href="/compras">🛒 Compras</a><a href="/productos_base">📦 Productos base</a>'
    )
    html += """
    <div class="contenido">
        <h1>🤝 Proveedores</h1>
        <div class="card">
    """

    if error:
        html += f"<div class='error'>{error}</div>"

    html += """
            <form method="post">
                <input name="nombre" placeholder="Nombre del proveedor" required>
                <button type="submit">➕ Agregar proveedor</button>
            </form>
        </div>
        <h2>Lista de proveedores</h2>
    """

    if not lista:
        html += """
        <div class="card">
            No hay proveedores registrados.
        </div>
        """
    else:
        for proveedor in lista:
            html += f"""
            <div class="card">
                <b>{proveedor[0]}</b>
            </div>
            """

    html += """
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/productos_base", methods=["GET", "POST"])
def productos_base():
    conn = get_connection()
    cursor = conn.cursor()
    error = ""

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        unidad = request.form.get("unidad", "").strip()

        if nombre == "" or unidad == "":
            error = "Datos invalidos"
        else:
            cursor.execute(
                "SELECT id FROM productos_base WHERE lower(nombre)=lower(?)",
                (nombre,),
            )
            if cursor.fetchone():
                error = "Ese producto base ya existe"
            else:
                cursor.execute(
                    """
                    INSERT INTO productos_base (nombre, unidad)
                    VALUES (?, ?)
                    """,
                    (nombre, unidad),
                )
                conn.commit()
                conn.close()
                return redirect("/productos_base")

    cursor.execute(
        """
        SELECT nombre, unidad
        FROM productos_base
        ORDER BY nombre ASC
        """
    )
    lista = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .contenido { padding: 10px; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    input { width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 5px; background: #27ae60; color: white; cursor: pointer; }
    .error { background: #fdecea; color: #c0392b; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: #7f8c8d; color: white; text-decoration: none; border-radius: 5px; }
    </style>
    </head>
    <body>
    """

    html += barra_superior(
        '<a href="/">🏠 Inicio</a><a href="/compras">🛒 Compras</a><a href="/proveedores">🤝 Proveedores</a>'
    )
    html += """
    <div class="contenido">
        <h1>📦 Productos base</h1>
        <div class="card">
    """

    if error:
        html += f"<div class='error'>{error}</div>"

    html += """
            <form method="post">
                <input name="nombre" placeholder="Nombre del producto base" required>
                <input name="unidad" placeholder="Unidad (kg, lt, und)" required>
                <button type="submit">➕ Agregar producto base</button>
            </form>
        </div>
        <h2>Lista de productos base</h2>
    """

    if not lista:
        html += """
        <div class="card">
            No hay productos base registrados.
        </div>
        """
    else:
        for producto in lista:
            html += f"""
            <div class="card">
                <b>{producto[0]}</b><br>
                Unidad: {producto[1]}
            </div>
            """

    html += """
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/produccion", methods=["GET", "POST"])
def produccion():
    conn = get_connection()
    cursor = conn.cursor()
    error = ""

    cursor.execute(
        """
        SELECT id, nombre, unidad, stock_actual
        FROM inventario
        ORDER BY nombre ASC
        """
    )
    inventario_items = cursor.fetchall()

    cursor.execute(
        """
        SELECT id, nombre, unidad
        FROM productos_base
        ORDER BY nombre ASC
        """
    )
    productos_base_items = cursor.fetchall()

    if request.method == "POST":
        producto_origen_id = request.form.get("producto_origen", "").strip()
        producto_resultado_id = request.form.get("producto_resultado", "").strip()

        try:
            cantidad_origen = float(request.form.get("cantidad_origen", 0) or 0)
            cantidad_resultado = float(request.form.get("cantidad_resultado", 0) or 0)
        except Exception:
            cantidad_origen = 0
            cantidad_resultado = 0

        if (
            producto_origen_id == ""
            or producto_resultado_id == ""
            or cantidad_origen <= 0
            or cantidad_resultado <= 0
        ):
            error = "Datos invalidos"
        else:
            cursor.execute(
                """
                SELECT id, nombre, stock_actual, unidad
                FROM inventario
                WHERE id=?
                LIMIT 1
                """,
                (producto_origen_id,),
            )
            origen = cursor.fetchone()

            cursor.execute(
                """
                SELECT id, nombre, unidad
                FROM productos_base
                WHERE id=?
                LIMIT 1
                """,
                (producto_resultado_id,),
            )
            resultado_base = cursor.fetchone()

            if not origen:
                error = "Producto origen no encontrado en inventario"
            elif not resultado_base:
                error = "Producto resultado no valido"
            elif float(origen[2] or 0) < cantidad_origen:
                error = "Stock insuficiente para realizar la produccion"
            else:
                producto_origen = origen[1]
                producto_resultado = resultado_base[1]
                unidad_resultado = resultado_base[2] if resultado_base[2] else "unidad"
                costo_promedio_origen = obtener_costo_promedio_producto(cursor, producto_origen)
                costo_total = costo_promedio_origen * cantidad_origen
                costo_unitario_resultado = (
                    costo_total / cantidad_resultado if cantidad_resultado > 0 else 0
                )
                fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
                usuario_id = session.get("usuario_id")
                nuevo_stock_origen = float(origen[2] or 0) - cantidad_origen

                cursor.execute(
                    """
                    UPDATE inventario
                    SET stock_actual=?
                    WHERE id=?
                    """,
                    (nuevo_stock_origen, origen[0]),
                )

                cursor.execute(
                    """
                    SELECT id, stock_actual
                    FROM inventario
                    WHERE lower(nombre) = lower(?)
                    LIMIT 1
                    """,
                    (producto_resultado,),
                )
                resultado = cursor.fetchone()

                if resultado:
                    nuevo_stock_resultado = float(resultado[1] or 0) + cantidad_resultado
                    cursor.execute(
                        """
                        UPDATE inventario
                        SET stock_actual=?, unidad=?, costo_promedio=?
                        WHERE id=?
                        """,
                        (
                            nuevo_stock_resultado,
                            unidad_resultado,
                            costo_unitario_resultado,
                            resultado[0],
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO inventario (nombre, stock_actual, unidad, costo_promedio)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            producto_resultado,
                            cantidad_resultado,
                            unidad_resultado,
                            costo_unitario_resultado,
                        ),
                    )

                cursor.execute(
                    """
                    INSERT INTO producciones (
                        producto_origen, cantidad_origen, producto_resultado,
                        cantidad_resultado, costo_total, fecha, usuario_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        producto_origen,
                        cantidad_origen,
                        producto_resultado,
                        cantidad_resultado,
                        costo_total,
                        fecha,
                        usuario_id,
                    ),
                )

                conn.commit()
                conn.close()
                return redirect("/inventario")

    cursor.execute(
        """
        SELECT producto_origen, cantidad_origen, producto_resultado, cantidad_resultado, costo_total, fecha
        FROM producciones
        ORDER BY id DESC
        LIMIT 20
        """
    )
    historial = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: Arial; margin: 0; background: #f5f6fa; }
    .contenido { padding: 10px; }
    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    input, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }
    button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 5px; background: #27ae60; color: white; cursor: pointer; }
    .error { background: #fdecea; color: #c0392b; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    .grid-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: #7f8c8d; color: white; text-decoration: none; border-radius: 5px; }
    @media (max-width: 768px) { .grid-form { grid-template-columns: 1fr; } }
    </style>
    </head>
    <body>
    """

    html += barra_superior(
        '<a href="/">🏠 Inicio</a><a href="/inventario">📦 Inventario</a><a href="/compras">🛒 Compras</a>'
    )
    html += """
    <div class="contenido">
        <h1>🏭 Producción</h1>
        <div class="card">
    """

    if error:
        html += f"<div class='error'>{error}</div>"

    html += """
            <form method="post">
                <div class="grid-form">
                    <div>
                        <label>Producto origen</label>
                        <select name="producto_origen" required>
                            <option value="">Seleccione producto</option>
    """

    for item in inventario_items:
        html += (
            f"<option value='{item[0]}'>{item[1]} "
            f"({round(item[3] or 0, 2)} {item[2] if item[2] else ''})</option>"
        )

    html += """
                        </select>
                    </div>
                    <div>
                        <label>Producto resultado</label>
                        <select name="producto_resultado" required>
                            <option value="">Seleccione producto</option>
    """

    for producto in productos_base_items:
        html += f"<option value='{producto[0]}'>{producto[1]} ({producto[2] if producto[2] else '-'})</option>"

    html += """
                        </select>
                    </div>
                </div>
                <input name="cantidad_origen" type="number" step="0.01" min="0.01" placeholder="Cantidad origen" required>
                <input name="cantidad_resultado" type="number" step="0.01" min="0.01" placeholder="Cantidad resultado" required>
                <button type="submit">🏭 Registrar producción</button>
            </form>
        </div>
        <h2>🏭 Ultimas producciones</h2>
    """

    if not historial:
        html += """
        <div class="card">
            No hay producciones registradas.
        </div>
        """
    else:
        for prod in historial:
            costo_unitario = (float(prod[4] or 0) / float(prod[3])) if prod[3] else 0
            html += f"""
            <div class="card">
                <b>{prod[0]}</b> -> <b>{prod[2]}</b><br>
                Origen: {round(prod[1] or 0, 2)}<br>
                Resultado: {round(prod[3] or 0, 2)}<br>
                Costo total: ${round(prod[4] or 0, 2)}<br>
                Costo unitario resultado: ${round(costo_unitario, 4)}<br>
                Fecha: {prod[5]}
            </div>
            """

    html += """
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    nombre = request.form.get("nombre", "").strip()

    try:
        precio = float(request.form["precio"])
        categoria_id = int(request.form["categoria_id"])
    except Exception:
        return "Datos invalidos"

    if nombre == "":
        return "Nombre requerido"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO productos (nombre, precio, categoria_id)
        VALUES (?, ?, ?)
        """,
        (nombre, precio, categoria_id),
    )
    conn.commit()
    conn.close()
    return redirect("/menu")


@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM productos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/menu")


@app.route("/editar_producto/<int:id>", methods=["GET", "POST"])
def editar_producto(id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM categorias")
    categorias = cursor.fetchall()

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        try:
            precio = float(request.form["precio"])
            categoria_id = int(request.form["categoria_id"])
        except Exception:
            conn.close()
            return "Datos invalidos"

        cursor.execute(
            """
            UPDATE productos
            SET nombre=?, precio=?, categoria_id=?
            WHERE id=?
            """,
            (nombre, precio, categoria_id, id),
        )
        conn.commit()
        conn.close()
        return redirect("/menu")

    cursor.execute(
        """
        SELECT nombre, precio, categoria_id
        FROM productos
        WHERE id=?
        """,
        (id,),
    )
    p = cursor.fetchone()
    conn.close()

    if not p:
        return "Producto no encontrado"

    html = f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body {{ font-family: Arial; padding: 20px; background: #f5f6fa; }}
    .card {{ background: white; padding: 20px; max-width: 500px; margin: auto; border-radius: 10px; }}
    input, select {{ width: 100%; padding: 12px; margin: 5px 0; box-sizing: border-box; }}
    button {{ padding: 12px 20px; background: #27ae60; color: white; border: none; border-radius: 5px; }}
    a {{ display: inline-block; margin-top: 10px; }}
    </style>
    </head>
    <body>
    <div class="card">
    <h1>Editar producto</h1>
    <form method="post">
        Nombre: <input name="nombre" value="{p[0]}"><br><br>
        Precio: <input name="precio" value="{p[1]}"><br><br>
        Categoria:
        <select name="categoria_id">
    """

    for c in categorias:
        selected = "selected" if c[0] == p[2] else ""
        html += f"<option value='{c[0]}' {selected}>{c[1]}</option>"

    html += """
        </select><br><br>
        <button>Guardar</button>
    </form>
    <a href="/menu">Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/nueva_orden")
def nueva_orden():
    return redirect("/")


@app.route("/crear_orden", methods=["POST"])
def crear_orden():
    tipo = request.form.get("tipo")
    referencia = request.form.get("referencia", "")
    cliente = request.form.get("cliente", "")
    fecha_hora = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    fecha = ahora_venezuela().strftime("%Y-%m-%d")
    usuario_id = session.get("usuario_id")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO ordenes (
            numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (None, fecha_hora, fecha, tipo, referencia, cliente, "abierta", usuario_id),
    )
    orden_id = obtener_ultimo_id(cursor, "ordenes")
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/orden/<int:orden_id>")
def orden(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
               o.estado, o.observacion, o.descuento, u.nombre, o.cierre_id
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=?
        """,
        (orden_id,),
    )
    o = cursor.fetchone()
    if not o:
        conn.close()
        return "Orden no encontrada"

    estado = o[6]

    cursor.execute(
        """
        SELECT p.id, p.nombre, p.precio, c.nombre
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        """
    )
    productos = cursor.fetchall()

    cursor.execute(
        """
        SELECT producto, precio, id
        FROM orden_items
        WHERE orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()

    tasa = obtener_tasa_actual(cursor)
    conn.close()

    total_usd = sum(float(i[1]) for i in items)
    total_bs = total_usd * tasa
    descuento = o[8] if o[8] else 0
    total_bs_final = max(total_bs - descuento, 0)
    bloqueada_por_cierre = o[10] is not None

    boton_reimprimir = ""
    if usuario_puede_reimprimir_cocina() and estado in ("en cocina", "cerrada"):
        boton_reimprimir = (
            f'<a href="/reimprimir_cocina/{orden_id}" class="btn-accion" '
            'style="background:#8e44ad;">🔁 Reimprimir cocina</a>'
        )

    advertencia_cobro = ""
    if estado == "abierta":
        advertencia_cobro = (
            ' onclick="return confirm(\'⚠️ Esta orden aún no ha sido enviada a cocina. '
            '¿Seguro que quieres continuar con el cobro?\')"'
        )

    html = f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body {{ font-family: Arial; margin: 0; background: #f5f6fa; }}
    .header {{ background: #2c3e50; color: white; padding: 15px; display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
    .titulo {{ font-size: 22px; font-weight: bold; }}
    .menu-top {{ display: flex; flex-wrap: wrap; gap: 5px; justify-content: flex-end; }}
    .menu-top a {{ color: white; text-decoration: none; background: #34495e; padding: 10px; border-radius: 5px; font-size: 13px; flex: 1 1 45%; text-align: center; }}
    .contenedor {{ display: flex; gap: 0; }}
    .productos {{ width: 60%; padding: 20px; }}
    .panel {{ width: 40%; padding: 20px; background: #f4f4f4; min-height: calc(100vh - 84px); box-sizing: border-box; }}
    .btn {{ width: 100%; padding: 15px; margin: 5px 0; background: #27ae60; color: white; border: none; border-radius: 5px; }}
    .categoria {{ font-weight: bold; margin-top: 15px; background: #333; color: white; padding: 5px; border-radius: 5px; }}
    .grid-productos {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .acciones-superiores {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }}
    .btn-accion {{ display: block; padding: 12px; margin: 5px 0; text-align: center; color: white; text-decoration: none; border-radius: 5px; }}
    .cocina {{ background: #e67e22; }}
    .cobrar {{ background: #27ae60; }}
    .editar {{ background: #2980b9; }}
    .eliminar {{ background: #c0392b; }}
    .volver {{ background: #7f8c8d; }}
    .total {{ font-size: 20px; margin-top: 10px; }}
    .info-cierre {{ background:#fff3cd; border:1px solid #f1c40f; padding:12px; border-radius:8px; margin-bottom:15px; }}
    .modal-refresco {{ position:fixed; inset:0; background:rgba(17,24,39,0.62); display:none; align-items:center; justify-content:center; padding:18px; z-index:1000; }}
    .modal-refresco.activo {{ display:flex; }}
    .modal-contenido {{ width:min(620px, 100%); background:white; border-radius:12px; padding:20px; box-shadow:0 20px 46px rgba(0,0,0,0.28); }}
    .modal-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:14px; }}
    .modal-top h2 {{ margin:0; color:#7f1d1d; }}
    .modal-top p {{ margin:5px 0 0; color:#4b5563; }}
    .cerrar-modal {{ width:auto; min-height:44px; padding:8px 12px; border:none; border-radius:8px; background:#7f8c8d; color:white; cursor:pointer; }}
    .sabores-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
    .sabor-btn {{ min-height:64px; padding:12px; border:none; border-radius:8px; background:#27ae60; color:white; font-size:17px; font-weight:900; cursor:pointer; }}
    .sabor-btn.otro {{ background:#8e44ad; }}
    @media (max-width: 768px) {{
        .contenedor {{ flex-direction: column; }}
        .productos, .panel {{ width: 100%; min-height: auto; }}
        .sabores-grid {{ grid-template-columns:1fr 1fr; }}
    }}
    </style>
    </head>
    <body>
    """

    html += barra_superior('<a href="/">🏠 Inicio</a>')

    html += """
    <div class="contenedor">
    <div class="productos">
    <h2>📋 Agregar productos</h2>
    """

    if bloqueada_por_cierre:
        html += f"""
        <div class="info-cierre">
            Esta orden pertenece al cierre de jornada #{o[10]} y queda en modo consulta.
        </div>
        """

    categorias = defaultdict(list)
    for p in productos:
        categoria = p[3] if p[3] else "Sin categoria"
        categorias[categoria].append(p)

    if not bloqueada_por_cierre:
        for categoria, lista in categorias.items():
            html += f"<div class='categoria'>{categoria}</div>"
            html += "<div class='grid-productos'>"

            mitad = (len(lista) + 1) // 2
            col1 = lista[:mitad]
            col2 = lista[mitad:]
            ordenados = []

            for i in range(mitad):
                if i < len(col1):
                    ordenados.append(col1[i])
                if i < len(col2):
                    ordenados.append(col2[i])

            for p in ordenados:
                if es_producto_refresco(p[1]):
                    html += f"""
                    <button class="btn btn-refresco" type="button" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{html_lib.escape(p[1], quote=True)}">
                        {p[1]} - ${p[2]}
                    </button>
                    """
                else:
                    html += f"""
                    <a href="/agregar/{orden_id}/{p[0]}">
                        <button class="btn" type="button">{p[1]} - ${p[2]}</button>
                    </a>
                    """

            html += "</div>"

    html += "</div>"
    boton_eliminar_orden = ""
    if usuario_es_admin_cierre() and not bloqueada_por_cierre and estado in ("abierta", "en cocina"):
        boton_eliminar_orden = f"""
            <form method="post" action="/eliminar_orden/{orden_id}" class="form-eliminar-orden" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-accion eliminar" style="width:100%; border:none; cursor:pointer;">🗑️ Eliminar orden</button>
            </form>
        """

    html += f"""
    <div class="panel">
        <h2>🧾 Orden {texto_numero_orden(o[1])}</h2>
        <div class="acciones-superiores">
            <a href="/editar_orden/{orden_id}" class="btn-accion editar">✏️ Editar orden</a>
            {boton_eliminar_orden}
        </div>
        <p>Tipo: {o[3]}</p>
        <p>Referencia: {o[4]}</p>
        <p>👤 Cliente: {o[5] if o[5] else '-'}</p>
        <p>👩 Mesonera: <b>{o[9] if o[9] else '-'}</b></p>
        <p>Estado: {estado}</p>
        <p>Observacion: {o[7] if o[7] else '-'}</p>
        <h3>🍽️ Productos</h3>
    """

    for i in items:
        if estado == "cerrada" or bloqueada_por_cierre:
            boton_eliminar = ""
        else:
            boton_eliminar = f"""
            <form method="post" action="/eliminar_item/{i[2]}/{orden_id}" class="form-eliminar-item" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" style="background:#c0392b; color:white; border:none; border-radius:6px; padding:8px 12px; cursor:pointer; width:auto;">❌</button>
            </form>
            """

        html += f"""
        <div style='display:flex; justify-content:space-between; margin:5px 0; gap:10px;'>
            <span>{i[0]} - ${i[1]}</span>
            {boton_eliminar}
        </div>
        """

    html += f"""
        <div class="total">USD: ${round(total_usd, 2)}</div>
        <div class="total">Bs: {round(total_bs, 2)}</div>
        <p>Descuento: Bs {round(descuento, 2)}</p>
        <div class="total">Total Final Bs: {round(total_bs_final, 2)}</div>
        {boton_reimprimir}
    """

    if not bloqueada_por_cierre:
        html += f"""
        <a href="/enviar_cocina/{orden_id}" class="btn-accion cocina">🍳 Enviar a cocina</a>
        <a href="/activar_factura/{orden_id}" class="btn-accion" style="background:#8e44ad;">🧾 Facturar</a>
        <a href="/cobrar/{orden_id}" class="btn-accion cobrar"{advertencia_cobro}>💵 Cobrar</a>
        """

    html += f"""
        <a href="/factura/{orden_id}" class="btn-accion" style="background:#16a085;">🔍 Ver factura</a>
        <a href="/" class="btn-accion volver">🏠 Volver</a>
    </div>
    </div>
    <div id="modal-refresco" class="modal-refresco" aria-hidden="true">
        <div class="modal-contenido">
            <div class="modal-top">
                <div>
                    <h2>🥤 Seleccionar sabor</h2>
                    <p id="modal-refresco-producto">Refresco</p>
                </div>
                <button id="cerrar-modal-refresco" class="cerrar-modal" type="button">✖</button>
            </div>
            <div id="sabores-refresco-grid" class="sabores-grid"></div>
        </div>
    </div>
    <script>
    function pedirClaveSupervisor() {{
        const clave = prompt("Clave de supervisor");
        if (clave === null) {{
            return null;
        }}
        return clave.trim();
    }}

    const saboresRefresco = ["Coca Cola", "Chinotto", "Frescolita", "Naranja", "Uva", "Manzana", "7Up", "Pepsi", "Otro"];
    const modalRefresco = document.getElementById("modal-refresco");
    const modalRefrescoProducto = document.getElementById("modal-refresco-producto");
    const saboresRefrescoGrid = document.getElementById("sabores-refresco-grid");
    const cerrarModalRefresco = document.getElementById("cerrar-modal-refresco");
    let refrescoSeleccionadoUrl = "";

    function cerrarSelectorRefresco() {{
        refrescoSeleccionadoUrl = "";
        modalRefresco.classList.remove("activo");
        modalRefresco.setAttribute("aria-hidden", "true");
    }}

    function agregarRefrescoConSabor(sabor) {{
        const saborLimpio = (sabor || "").trim();
        if (!saborLimpio || !refrescoSeleccionadoUrl) {{
            return;
        }}
        window.location.href = refrescoSeleccionadoUrl + "?sabor=" + encodeURIComponent(saborLimpio);
    }}

    function abrirSelectorRefresco(btn) {{
        refrescoSeleccionadoUrl = btn.dataset.url;
        modalRefrescoProducto.textContent = btn.dataset.producto || "Refresco";
        saboresRefrescoGrid.innerHTML = "";

        saboresRefresco.forEach(function(sabor) {{
            const boton = document.createElement("button");
            boton.type = "button";
            boton.className = "sabor-btn" + (sabor === "Otro" ? " otro" : "");
            boton.textContent = sabor === "Otro" ? "✍️ Otro" : "🥤 " + sabor;
            boton.addEventListener("click", function() {{
                if (sabor === "Otro") {{
                    const escrito = prompt("Escribe el sabor del refresco");
                    if (escrito === null || !escrito.trim()) {{
                        return;
                    }}
                    agregarRefrescoConSabor(escrito);
                    return;
                }}
                agregarRefrescoConSabor(sabor);
            }});
            saboresRefrescoGrid.appendChild(boton);
        }});

        modalRefresco.classList.add("activo");
        modalRefresco.setAttribute("aria-hidden", "false");
    }}

    document.querySelectorAll(".btn-refresco").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            abrirSelectorRefresco(btn);
        }});
    }});

    cerrarModalRefresco.addEventListener("click", cerrarSelectorRefresco);
    modalRefresco.addEventListener("click", function(event) {{
        if (event.target === modalRefresco) {{
            cerrarSelectorRefresco();
        }}
    }});

    document.querySelectorAll(".form-eliminar-item").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            const clave = pedirClaveSupervisor();
            if (!clave) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave;
        }});
    }});

    document.querySelectorAll(".form-eliminar-orden").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            if (!confirm("¿Eliminar esta orden completa?")) {{
                event.preventDefault();
                return;
            }}
            const clave = pedirClaveSupervisor();
            if (!clave) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave;
        }});
    }});
    </script>
    </body>
    </html>
    """
    return html


@app.route("/agregar/<int:orden_id>/<int:producto_id>")
def agregar(orden_id, producto_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Orden no encontrada"

    if row[1] is not None:
        conn.close()
        return "No puedes modificar una orden archivada en cierre de jornada"

    if row[0] == "cerrada":
        conn.close()
        return "No puedes agregar productos a una orden cerrada"

    cursor.execute("SELECT nombre, precio FROM productos WHERE id=?", (producto_id,))
    p = cursor.fetchone()
    if not p:
        conn.close()
        return "Producto no encontrado"

    producto_nombre = p[0]
    if es_producto_refresco(producto_nombre):
        sabor = normalizar_sabor_refresco(request.args.get("sabor"))
        if not sabor:
            conn.close()
            return "Debes seleccionar un sabor valido para el refresco"
        producto_nombre = f"{producto_nombre} - {sabor}"

    cursor.execute(
        """
        INSERT INTO orden_items (orden_id, producto, precio)
        VALUES (?, ?, ?)
        """,
        (orden_id, producto_nombre, p[1]),
    )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/enviar_cocina/<int:orden_id>")
def cocina(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT numero_orden
        FROM ordenes
        WHERE id=? AND cierre_id IS NULL
        """,
        (orden_id,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return "Orden no encontrada"

    numero_actual = row[0]
    if numero_actual is None:
        numero_actual = siguiente_numero()

    cursor.execute(
        """
        UPDATE ordenes
        SET estado='en cocina', numero_orden=?
        WHERE id=? AND cierre_id IS NULL
        """,
        (numero_actual, orden_id),
    )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/reimprimir_cocina/<int:orden_id>")
def reimprimir_cocina(orden_id):
    if not usuario_puede_reimprimir_cocina():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, estado
        FROM ordenes
        WHERE id=?
        """,
        (orden_id,),
    )
    orden = cursor.fetchone()

    if not orden:
        conn.close()
        return "Orden no encontrada"

    if orden[1] not in ("en cocina", "cerrada"):
        conn.close()
        return "Solo se pueden reimprimir ordenes en cocina o cerradas"

    reimpresion_token = ahora_venezuela().strftime("%Y%m%d%H%M%S%f")

    cursor.execute(
        """
        UPDATE ordenes
        SET reimpresion_token=?
        WHERE id=?
        """,
        (reimpresion_token, orden_id),
    )

    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/eliminar_item/<int:item_id>/<int:orden_id>", methods=["POST"])
def eliminar_item(item_id, orden_id):
    clave = request.form.get("clave", "").strip()
    if clave != CLAVE_SUPERVISOR:
        return "Clave incorrecta"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return "Orden no encontrada"

    if row[1] is not None:
        conn.close()
        return "Orden archivada, no se puede modificar"

    estado = row[0]
    if estado == "cerrada":
        conn.close()
        return "Orden cerrada, no se puede modificar"

    cursor.execute(
        """
        SELECT id
        FROM orden_items
        WHERE id=? AND orden_id=?
        """,
        (item_id, orden_id),
    )
    if not cursor.fetchone():
        conn.close()
        return "Producto no encontrado en esta orden"

    cursor.execute("DELETE FROM orden_items WHERE id=? AND orden_id=?", (item_id, orden_id))
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/editar_orden/<int:orden_id>", methods=["GET", "POST"])
def editar_orden(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT cierre_id FROM ordenes WHERE id=?", (orden_id,))
    bloqueo = cursor.fetchone()
    if not bloqueo:
        conn.close()
        return "Orden no encontrada"

    if bloqueo[0] is not None:
        conn.close()
        return "No se puede editar una orden archivada por cierre de jornada"

    if request.method == "POST":
        tipo = request.form.get("tipo")
        referencia = request.form.get("referencia")
        cliente = request.form.get("cliente")
        observacion = request.form.get("observacion")
        cursor.execute(
            """
            UPDATE ordenes
            SET tipo=?, referencia=?, cliente=?, observacion=?
            WHERE id=?
            """,
            (tipo, referencia, cliente, observacion, orden_id),
        )
        conn.commit()
        conn.close()
        return redirect(f"/orden/{orden_id}")

    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.tipo, o.referencia, o.cliente, o.observacion, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=?
        """,
        (orden_id,),
    )
    o = cursor.fetchone()
    conn.close()

    if not o:
        return "Orden no encontrada"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body {{ font-family: Arial; padding: 20px; background: #f5f6fa; }}
    .card {{ background: white; max-width: 520px; margin: auto; padding: 20px; border-radius: 10px; }}
    input, textarea {{ width: 100%; padding: 12px; margin: 5px 0; box-sizing: border-box; }}
    button {{ padding: 12px 20px; background: #27ae60; color: white; border: none; border-radius: 5px; }}
    a {{ display: inline-block; margin-top: 10px; }}
    </style>
    </head>
    <body>
    <div class="card">
    <h2>Editar Orden {texto_numero_orden(o[1])}</h2>
    <p><b>Mesonera:</b> {o[6] if o[6] else '-'}</p>
    <form method="POST">
        <label>Mesa / tipo:</label><br>
        <input name="tipo" value="{o[2]}"><br><br>
        <label>Referencia:</label><br>
        <input name="referencia" value="{o[3]}"><br><br>
        <label>Nombre:</label><br>
        <input name="cliente" value="{o[4] if o[4] else ''}"><br><br>
        <label>Observacion:</label><br>
        <textarea name="observacion" style="height:80px;">{o[5] if o[5] else ''}</textarea><br><br>
        <button type="submit">Guardar</button>
    </form>
    <br>
    <a href="/orden/{orden_id}">Volver</a>
    </div>
    </body>
    </html>
    """


@app.route("/eliminar_orden/<int:orden_id>", methods=["GET", "POST"])
def eliminar_orden(orden_id):
    if request.method != "POST":
        return "Operacion requiere clave de supervisor", 405

    clave = request.form.get("clave", "").strip()
    if clave != CLAVE_SUPERVISOR:
        return "Clave incorrecta"

    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return "Orden no encontrada"

    if row[1] is not None:
        conn.close()
        return "No se puede eliminar una orden archivada"

    estado = row[0]

    if estado not in ("abierta", "en cocina"):
        conn.close()
        return "No se puede eliminar esta orden"

    cursor.execute("DELETE FROM orden_items WHERE orden_id=?", (orden_id,))
    cursor.execute("DELETE FROM pagos WHERE orden_id=?", (orden_id,))
    cursor.execute("DELETE FROM ordenes WHERE id=?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/cobrar/<int:orden_id>", methods=["GET", "POST"])
def cobrar(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
               o.estado, o.observacion, o.descuento, u.nombre, o.cierre_id
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=?
        """,
        (orden_id,),
    )
    o = cursor.fetchone()

    if not o:
        conn.close()
        return "Orden no encontrada"

    estado = o[6]

    if o[10] is not None:
        conn.close()
        return "Esta orden ya pertenece a un cierre de jornada"

    if estado == "cerrada" and o[10] is not None:
        conn.close()
        return "Esta orden ya esta cerrada"

    cursor.execute("SELECT precio FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    if len(items) == 0:
        conn.close()
        return "No puedes cobrar una orden vacia"

    total_usd = sum(a_float(i[0]) for i in items)
    tasa = obtener_tasa_actual(cursor)

    total_bs = total_usd * tasa
    descuento_bs = a_float(o[8])
    total_bs_final = max(total_bs - descuento_bs, 0)

    error = ""
    metodo1_val = "bs_pago_movil"
    monto1_val = f"{round(total_bs_final, 2)}"
    ref1_val = ""
    metodo2_val = ""
    monto2_val = ""
    ref2_val = ""
    descuento_val = f"{round(descuento_bs, 2)}"

    if request.method == "POST":
        metodo1_val = normalizar_metodo_pago(request.form.get("metodo1"))
        monto1_val = (request.form.get("monto1", "") or "").strip()
        ref1_val = (request.form.get("ref1", "") or "").strip()
        descuento_val = (request.form.get("descuento", "") or "").strip()
        metodo2_val = normalizar_metodo_pago(request.form.get("metodo2"))
        monto2_val = (request.form.get("monto2", "") or "").strip()
        ref2_val = (request.form.get("ref2", "") or "").strip()

        monto1 = a_float(monto1_val)
        monto2 = a_float(monto2_val)
        descuento = a_float(descuento_val)

        if metodo1_val == "":
            error = "Debes seleccionar el metodo de pago principal"
        elif metodo1_val not in METODOS_PAGO_VALIDOS:
            error = "Metodo de pago principal invalido"
        elif monto1 <= 0:
            error = "El monto del pago 1 debe ser mayor a 0"
        elif descuento < 0:
            error = "El descuento no puede ser negativo"
        elif metodo2_val and metodo2_val not in METODOS_PAGO_VALIDOS:
            error = "Metodo de pago 2 invalido"
        elif metodo2_val and monto2 < 0:
            error = "El monto del pago 2 no puede ser negativo"
        elif not metodo2_val and monto2 > 0:
            error = "Si colocas monto en pago 2, debes seleccionar el metodo"
        else:
            total_bs_final = max(total_bs - descuento, 0)
            total_usd_final = (total_bs_final / tasa) if tasa else 0.0

            pago1_bs, pago1_usd = convertir_pago_equivalente(metodo1_val, monto1, tasa)
            total_pagado_bs = pago1_bs
            total_pagado_usd = pago1_usd

            insertar_pago_1 = bool(metodo1_val and monto1 > 0)
            insertar_pago_2 = bool(metodo2_val and monto2 > 0 and pago1_usd + 0.0001 < total_usd_final)
            if insertar_pago_2:
                pago2_bs, pago2_usd = convertir_pago_equivalente(metodo2_val, monto2, tasa)
                total_pagado_bs += pago2_bs
                total_pagado_usd += pago2_usd

            if not insertar_pago_1:
                error = "No hay pagos validos para registrar"
            elif total_pagado_bs + 0.0001 < total_bs_final:
                error = "Pago insuficiente"
            else:
                fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("DELETE FROM pagos WHERE orden_id = ?", (orden_id,))

                if insertar_pago_1:
                    cursor.execute(
                        """
                        INSERT INTO pagos (orden_id, metodo, monto, referencia, fecha)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (orden_id, metodo1_val, monto1, ref1_val, fecha),
                    )

                if insertar_pago_2:
                    cursor.execute(
                        """
                        INSERT INTO pagos (orden_id, metodo, monto, referencia, fecha)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (orden_id, metodo2_val, monto2, ref2_val, fecha),
                    )

                cursor.execute(
                    """
                    UPDATE ordenes
                    SET estado='cerrada', descuento=?
                    WHERE id=?
                      AND cierre_id IS NULL
                      AND estado IN ('abierta', 'en cocina', 'listo', 'cerrada')
                    """,
                    (descuento, orden_id),
                )

                if getattr(cursor, "rowcount", 0) == 0:
                    conn.rollback()
                    conn.close()
                    return "Esta orden ya fue cerrada o pertenece a un cierre de jornada"

                conn.commit()
                conn.close()
                if usuario_es_admin_cierre():
                    return redirect("/cierre")
                return redirect("/")

    conn.close()

    def selected(actual, esperado):
        return "selected" if actual == esperado else ""

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ font-family: Arial; margin: 0; background: #f5f6fa; }}
    .contenedor {{ width: 95%; max-width: 720px; margin: 18px auto; background: white; padding: 22px; border-radius: 12px; box-shadow: var(--sombra); }}
    .titulo {{ text-align: center; font-size: 28px; font-weight: 900; color:#7f1d1d; }}
    .numero {{ text-align: right; font-size: 18px; margin-bottom: 10px; }}
    .sep {{ border-top: 1px dashed #ccc; margin: 15px 0; }}
    .total {{ font-size: 20px; font-weight: bold; text-align: right; }}
    input, select {{ width: 100%; padding: 12px; margin: 5px 0; border-radius: 5px; border: 1px solid #ccc; font-size: 16px; box-sizing: border-box; }}
    .btn {{ width: 100%; padding: 15px; margin-top: 10px; border: none; border-radius: 5px; font-size: 18px; cursor: pointer; }}
    .confirmar {{ background: linear-gradient(135deg, #15803d, #16a34a); color: white; }}
    .volver {{ background: #7f8c8d; color: white; text-decoration:none; display:block; text-align:center; padding:15px; border-radius:5px; }}
    .error {{ background:#fdecea; color:#c0392b; padding:12px; border-radius:8px; margin-bottom:12px; }}
    </style>
    </head>
    <body>
    <div class="contenedor">
    <div class="titulo">💵 COBRAR</div>
    <div class="numero">Orden {texto_numero_orden(o[1])}</div>
    <div>
    <b>👤 Cliente:</b> {o[5] if o[5] else '-'}<br>
    <b>Tipo:</b> {o[3]}<br>
    <b>👩 Mesonera:</b> {o[9] if o[9] else '-'}
    </div>
    <div class="sep"></div>
    <div class="total">USD: ${round(total_usd, 2)}</div>
    <div class="total">Bs: {round(total_bs, 2)}</div>
    <div class="total">Tasa: Bs {round(tasa, 2)}</div>
    <div class="total">Total final Bs: {round(total_bs_final, 2)}</div>
    <div class="sep"></div>
    {"<div class='error'>" + error + "</div>" if error else ""}
    <form method="post">
    <h3>💳 Pago 1</h3>
    <select name="metodo1" id="metodo1" required>
        <option value="bs_pago_movil" {selected(metodo1_val, "bs_pago_movil")}>Pago movil en Bs</option>
        <option value="usd" {selected(metodo1_val, "usd")}>Efectivo USD</option>
        <option value="bs_efectivo" {selected(metodo1_val, "bs_efectivo")}>Efectivo Bs</option>
    </select>
    <input name="monto1" id="monto1" type="number" step="0.01" min="0.01" value="{monto1_val}" placeholder="Monto" required>
    <input name="ref1" value="{ref1_val}" placeholder="Referencia">
    <div class="sep"></div>
    <h3>💳 Pago 2 (opcional)</h3>
    <select name="metodo2" id="metodo2">
        <option value="" {selected(metodo2_val, "")}>-- ninguno --</option>
        <option value="usd" {selected(metodo2_val, "usd")}>Efectivo USD</option>
        <option value="bs_efectivo" {selected(metodo2_val, "bs_efectivo")}>Efectivo Bs</option>
        <option value="bs_pago_movil" {selected(metodo2_val, "bs_pago_movil")}>Pago movil en Bs</option>
    </select>
    <input name="monto2" id="monto2" type="number" step="0.01" min="0" value="{monto2_val}" placeholder="Monto">
    <input name="ref2" value="{ref2_val}" placeholder="Referencia">
    <div class="sep"></div>
    <label>Descuento (Bs)</label>
    <input name="descuento" id="descuento" type="number" step="0.01" value="{descuento_val}">
    <button class="btn confirmar">💵 Confirmar pago</button>
    </form>
    <a href="/orden/{orden_id}" class="volver">🏠 Volver</a>
    </div>
    <script>
    const metodo1 = document.getElementById("metodo1");
    const monto1 = document.getElementById("monto1");
    const metodo2 = document.getElementById("metodo2");
    const monto2 = document.getElementById("monto2");
    const descuento = document.getElementById("descuento");
    const totalUSD = {round(total_usd, 2)};
    const tasa = {round(tasa, 6)};

    function metodoEsUSD(metodo) {{
        return metodo === "usd";
    }}

    function metodoEsBs(metodo) {{
        return metodo === "bs_pago_movil" || metodo === "bs_efectivo" || metodo === "pago_movil";
    }}

    function numero(valor) {{
        const n = parseFloat(String(valor || "0").replace(",", "."));
        return Number.isFinite(n) ? n : 0;
    }}

    function totalFinalUSD() {{
        const descuentoBs = Math.max(numero(descuento.value), 0);
        return Math.max(totalUSD - (tasa ? descuentoBs / tasa : 0), 0);
    }}

    function totalFinalBs() {{
        return totalFinalUSD() * tasa;
    }}

    function pago1EnUSD() {{
        const valor = Math.max(numero(monto1.value), 0);
        if (metodoEsUSD(metodo1.value)) {{
            return valor;
        }}
        if (metodoEsBs(metodo1.value)) {{
            return tasa ? valor / tasa : 0;
        }}
        return 0;
    }}

    function recalcularPago2() {{
        const restanteUSD = Math.max(totalFinalUSD() - pago1EnUSD(), 0);
        if (restanteUSD <= 0) {{
            monto2.value = "0.00";
            return;
        }}
        if (!metodo2.value) {{
            return;
        }}
        if (metodoEsUSD(metodo2.value)) {{
            monto2.value = restanteUSD.toFixed(2);
        }} else if (metodoEsBs(metodo2.value)) {{
            monto2.value = (restanteUSD * tasa).toFixed(2);
        }}
    }}

    metodo1.addEventListener("change", function() {{
        if (metodo1.value === "usd") {{
            monto1.value = totalUSD.toFixed(2);
        }} else {{
            monto1.value = totalFinalBs().toFixed(2);
        }}
        recalcularPago2();
    }});
    monto1.addEventListener("input", recalcularPago2);
    metodo2.addEventListener("change", recalcularPago2);
    descuento.addEventListener("input", recalcularPago2);
    recalcularPago2();
    </script>
    </body>
    </html>
    """


@app.route("/cambiar_tasa", methods=["GET", "POST"])
def cambiar_tasa():
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        nueva_tasa = float(request.form["tasa"])
        cursor.execute("UPDATE tasa SET valor=?", (nueva_tasa,))
        conn.commit()

    tasa_actual = obtener_tasa_actual(cursor)
    conn.close()

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}</style>
    </head>
    <body style="font-family:Arial; padding:24px;">
    {barra_superior('<a href="/">🏠 Inicio</a>')}
    <div class="card" style="max-width:520px; margin:24px auto; background:white; padding:24px; border-radius:12px;">
    <h2>💱 Cambiar tasa</h2>
    <p>Tasa actual: <b>{tasa_actual}</b></p>
    <form method="post">
        <input name="tasa" placeholder="Nueva tasa" style="padding:12px; width:100%;">
        <button style="padding:12px 20px; background:#15803d; color:white; border:none; border-radius:8px;">💾 Guardar</button>
    </form>
    <a href="/" class="volver" style="background:#2c3e50; margin-top:15px;">🏠 Volver</a>
    </div>
    </body>
    </html>
    """


@app.route("/exportar")
def exportar():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
               o.estado, o.observacion, o.descuento, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        ORDER BY o.id ASC
        """
    )
    ordenes = cursor.fetchall()
    filas = []

    for o in ordenes:
        orden_id = o[0]
        cursor.execute(
            """
            SELECT producto, precio
            FROM orden_items
            WHERE orden_id=?
            """,
            (orden_id,),
        )
        items = cursor.fetchall()

        cursor.execute(
            """
            SELECT metodo, monto, referencia
            FROM pagos
            WHERE orden_id=?
            ORDER BY id ASC
            """,
            (orden_id,),
        )
        pagos = cursor.fetchall()

        total_usd = sum(i[1] for i in items)
        tasa = obtener_tasa_actual(cursor)
        total_bs = total_usd * tasa
        descuento = o[8] if o[8] else 0
        total_final = max(total_bs - descuento, 0)

        if not items:
            filas.append(
                [
                    orden_id,
                    o[2],
                    o[3],
                    o[4],
                    o[5],
                    o[9] if o[9] else "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    total_usd,
                    total_final,
                ]
            )
            continue

        for idx, item in enumerate(items):
            metodo = ""
            monto = 0
            referencia = ""
            if idx < len(pagos):
                metodo = pagos[idx][0]
                monto = pagos[idx][1]
                referencia = pagos[idx][2]

            filas.append(
                [
                    orden_id,
                    o[2],
                    o[3],
                    o[4],
                    o[5],
                    o[9] if o[9] else "",
                    item[0],
                    item[1],
                    metodo,
                    monto,
                    referencia,
                    total_usd if idx == 0 else 0,
                    total_final if idx == 0 else 0,
                ]
            )

    conn.close()

    def generar():
        yield "Orden,Fecha,Tipo,Ref Orden,Cliente,Mesonera,Producto,Precio USD,Metodo,Monto,Referencia Pago,Total USD,Total Bs\n"
        for fila in filas:
            yield ",".join(str(x) for x in fila) + "\n"

    return Response(generar(), mimetype="text/csv")


@app.route("/revertir_orden_cierre/<int:orden_id>", methods=["POST"])
def revertir_orden_cierre(orden_id):
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    clave = request.form.get("clave", "").strip()
    if clave != CLAVE_SUPERVISOR:
        return "Clave incorrecta"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT estado, cierre_id
        FROM ordenes
        WHERE id=?
        """,
        (orden_id,),
    )
    orden_row = cursor.fetchone()

    if not orden_row:
        conn.close()
        return "Orden no encontrada"

    estado, cierre_id = orden_row
    if cierre_id is None:
        conn.close()
        return "La orden no pertenece a ningun cierre"

    if estado != "cerrada":
        conn.close()
        return "Solo se pueden revertir ordenes cerradas"

    cursor.execute(
        """
        UPDATE ordenes
        SET cierre_id = NULL
        WHERE id=?
          AND cierre_id IS NOT NULL
          AND estado='cerrada'
        """,
        (orden_id,),
    )
    conn.commit()
    conn.close()

    return redirect(request.form.get("volver") or "/reportes")


@app.route("/reportes")
def reportes():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    desde, hasta = fechas_reporte_desde_request()
    conn = get_connection()
    cursor = conn.cursor()
    reporte = construir_reporte_rango(cursor, desde, hasta)
    conn.close()

    platos_html = ""
    if reporte["platos_vendidos"]:
        for plato in reporte["platos_vendidos"]:
            platos_html += f"""
            <tr>
                <td>{html_lib.escape(plato["producto"])}</td>
                <td>{plato["cantidad"]}</td>
            </tr>
            """
    else:
        platos_html = '<tr><td colspan="2">No hay platos vendidos en este rango.</td></tr>'

    ordenes_html = ""
    if reporte["ventas_por_orden"]:
        for orden in reporte["ventas_por_orden"]:
            accion_revertir = "-"
            if orden["cierre_id"] is not None:
                volver_url = f"/reportes?{urlencode({'desde': desde, 'hasta': hasta})}"
                accion_revertir = f"""
                <form method="post" action="/revertir_orden_cierre/{orden["orden_id"]}" class="form-revertir-cierre" style="margin:0;">
                    <input type="hidden" name="clave" value="">
                    <input type="hidden" name="volver" value="{volver_url}">
                    <button type="submit" style="background:#7f1d1d; color:white; border:none; border-radius:8px; padding:9px 11px; cursor:pointer; width:auto; min-height:38px;">🧨 Revertir orden</button>
                </form>
                """
            ordenes_html += f"""
            <tr>
                <td>{texto_numero_orden(orden["numero_orden"])}</td>
                <td>{orden["fecha_hora"]}</td>
                <td>{html_lib.escape(orden["cliente"] or "-")}</td>
                <td>{html_lib.escape(orden["mesonera"] or "-")}</td>
                <td>$ {orden["total_usd"]}</td>
                <td>Bs {orden["total_bs"]}</td>
                <td>{orden["cierre_id"] if orden["cierre_id"] is not None else "-"}</td>
                <td>{accion_revertir}</td>
            </tr>
            """
    else:
        ordenes_html = '<tr><td colspan="8">No hay ordenes cerradas en este rango.</td></tr>'

    export_url = f"/exportar_reporte?{urlencode({'desde': desde, 'hasta': hasta})}"
    dashboard_url = f"/dashboard?{urlencode({'desde': desde, 'hasta': hasta})}"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; }}
    .filtros, .metricas, .bloque {{ background:white; border-radius:12px; padding:18px; box-shadow:var(--sombra); margin-bottom:16px; }}
    .filtros form {{ display:grid; grid-template-columns: 1fr 1fr auto auto; gap:12px; align-items:end; }}
    .metricas {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }}
    .metrica {{ background:#f8fafc; border:1px solid #e5e7eb; border-left:5px solid var(--rojo-china); padding:14px; border-radius:8px; }}
    .metrica small {{ display:block; color:#64748b; font-weight:bold; margin-bottom:6px; }}
    .metrica b {{ font-size:22px; }}
    button, .btn-link {{ border:none; border-radius:8px; padding:13px 16px; color:white; background:#15803d; text-decoration:none; font-weight:900; min-height:48px; display:inline-flex; align-items:center; justify-content:center; }}
    .btn-excel {{ background:#1d4ed8; }}
    .btn-dashboard {{ background:#7f1d1d; }}
    table {{ width:100%; border-collapse:collapse; background:white; }}
    th, td {{ border-bottom:1px solid #e5e7eb; padding:11px; text-align:left; }}
    th {{ background:#fff7ed; color:#7f1d1d; }}
    .tabla-wrap {{ overflow:auto; }}
    @media (max-width: 900px) {{
        .filtros form, .metricas {{ grid-template-columns:1fr; }}
    }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">🏠 Inicio</a><a href="/dashboard">📈 Dashboard</a>')}
    <div class="contenido">
        <h1>📊 Reportes</h1>
        <div class="filtros">
            <form method="get" action="/reportes">
                <div>
                    <label>Fecha desde</label>
                    <input type="date" name="desde" value="{desde}" required>
                </div>
                <div>
                    <label>Fecha hasta</label>
                    <input type="date" name="hasta" value="{hasta}" required>
                </div>
                <button type="submit">🔍 Consultar</button>
                <a class="btn-link btn-excel" href="{export_url}">📤 Exportar Excel</a>
            </form>
        </div>

        <div class="metricas">
            <div class="metrica"><small>Total vendido USD</small><b>$ {reporte["total_vendido_usd"]}</b></div>
            <div class="metrica"><small>Pago movil Bs</small><b>Bs {reporte["total_pago_movil_bs"]}</b></div>
            <div class="metrica"><small>Efectivo Bs</small><b>Bs {reporte["total_efectivo_bs"]}</b></div>
            <div class="metrica"><small>Efectivo USD</small><b>$ {reporte["total_efectivo_usd"]}</b></div>
            <div class="metrica"><small>Total equivalente USD</small><b>$ {reporte["total_equiv_usd"]}</b></div>
            <div class="metrica"><small>Total equivalente Bs</small><b>Bs {reporte["total_equiv_bs"]}</b></div>
            <div class="metrica"><small>Cantidad de ordenes</small><b>{reporte["cantidad_ordenes"]}</b></div>
            <div class="metrica"><small>Tasa usada</small><b>Bs {reporte["tasa"]}</b></div>
        </div>

        <div class="bloque">
            <h2>🧾 Ventas por orden</h2>
            <div class="tabla-wrap">
                <table>
                    <thead><tr><th>Orden</th><th>Fecha</th><th>Cliente</th><th>Mesonera</th><th>Total USD</th><th>Total Bs</th><th>Cierre</th><th>Accion</th></tr></thead>
                    <tbody>{ordenes_html}</tbody>
                </table>
            </div>
        </div>

        <div class="bloque">
            <h2>🍽️ Platos vendidos</h2>
            <div class="tabla-wrap">
                <table>
                    <thead><tr><th>Producto</th><th>Cantidad</th></tr></thead>
                    <tbody>{platos_html}</tbody>
                </table>
            </div>
        </div>

        <a class="btn-link btn-dashboard" href="{dashboard_url}">📈 Ver dashboard</a>
    </div>
    <script>
    document.querySelectorAll(".form-revertir-cierre").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            if (!confirm("¿Revertir esta orden del cierre? No se eliminaran pagos ni productos.")) {{
                event.preventDefault();
                return;
            }}
            const clave = prompt("Clave de supervisor");
            if (!clave || !clave.trim()) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave.trim();
        }});
    }});
    </script>
    </body>
    </html>
    """


@app.route("/exportar_reporte")
def exportar_reporte():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    desde, hasta = fechas_reporte_desde_request()
    conn = get_connection()
    cursor = conn.cursor()
    reporte = construir_reporte_rango(cursor, desde, hasta)
    conn.close()

    resumen = [
        ["Concepto", "Valor"],
        ["Desde", reporte["desde"]],
        ["Hasta", reporte["hasta"]],
        ["Tasa", reporte["tasa"]],
        ["Total vendido USD", reporte["total_vendido_usd"]],
        ["Total pago movil Bs", reporte["total_pago_movil_bs"]],
        ["Total efectivo Bs", reporte["total_efectivo_bs"]],
        ["Total efectivo USD", reporte["total_efectivo_usd"]],
        ["Total equivalente USD", reporte["total_equiv_usd"]],
        ["Total equivalente Bs", reporte["total_equiv_bs"]],
        ["Cantidad de ordenes", reporte["cantidad_ordenes"]],
    ]

    ventas = [[
        "Orden ID",
        "Numero",
        "Fecha",
        "Tipo",
        "Referencia",
        "Cliente",
        "Mesonera",
        "Subtotal USD",
        "Descuento Bs",
        "Total USD",
        "Total Bs",
    ]]
    for orden in reporte["ventas_por_orden"]:
        ventas.append([
            orden["orden_id"],
            orden["numero_orden"] or "",
            orden["fecha_hora"],
            orden["tipo"],
            orden["referencia"],
            orden["cliente"],
            orden["mesonera"],
            orden["subtotal_usd"],
            orden["descuento_bs"],
            orden["total_usd"],
            orden["total_bs"],
        ])

    pagos = [[
        "Orden ID",
        "Numero",
        "Fecha orden",
        "Cliente",
        "Metodo",
        "Monto",
        "Referencia",
        "Fecha pago",
        "Equiv Bs",
        "Equiv USD",
    ]]
    for pago in reporte["pagos"]:
        pagos.append([
            pago["orden_id"],
            pago["numero_orden"] or "",
            pago["fecha_hora"],
            pago["cliente"],
            pago["metodo_label"],
            pago["monto"],
            pago["referencia"],
            pago["fecha_pago"],
            pago["equivalente_bs"],
            pago["equivalente_usd"],
        ])

    platos = [["Producto", "Cantidad"]]
    for plato in reporte["platos_vendidos"]:
        platos.append([plato["producto"], plato["cantidad"]])

    contenido = generar_xlsx(
        [
            ("Resumen", resumen),
            ("Ventas por orden", ventas),
            ("Pagos", pagos),
            ("Platos vendidos", platos),
        ]
    )

    nombre = f"reporte_china_house_{desde}_a_{hasta}.xlsx"
    respuesta = Response(
        contenido,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@app.route("/dashboard")
def dashboard():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    desde, hasta = fechas_reporte_desde_request()
    conn = get_connection()
    cursor = conn.cursor()
    reporte = construir_reporte_rango(cursor, desde, hasta)
    conn.close()

    max_ventas = max([dia["total_usd"] for dia in reporte["ventas_por_dia"]] or [1])
    ventas_dia_html = ""
    for dia in reporte["ventas_por_dia"]:
        ancho = int((dia["total_usd"] / max_ventas) * 100) if max_ventas else 0
        ventas_dia_html += f"""
        <div class="fila-barra">
            <div><b>{dia["fecha"]}</b><br>{dia["ordenes"]} ordenes · $ {dia["total_usd"]}</div>
            <div class="barra"><span style="width:{ancho}%;"></span></div>
        </div>
        """
    if not ventas_dia_html:
        ventas_dia_html = "<div class='vacio'>No hay ventas por dia en este rango.</div>"

    max_ordenes = max([dia["ordenes"] for dia in reporte["ventas_por_dia"]] or [1])
    ordenes_dia_html = ""
    for dia in reporte["ventas_por_dia"]:
        ancho = int((dia["ordenes"] / max_ordenes) * 100) if max_ordenes else 0
        ordenes_dia_html += f"""
        <div class="fila-barra">
            <div><b>{dia["fecha"]}</b><br>{dia["ordenes"]} ordenes cerradas</div>
            <div class="barra"><span style="width:{ancho}%;"></span></div>
        </div>
        """
    if not ordenes_dia_html:
        ordenes_dia_html = "<div class='vacio'>No hay ordenes cerradas en este rango.</div>"

    platos_html = ""
    max_platos = max([plato["cantidad"] for plato in reporte["platos_vendidos"]] or [1])
    for plato in reporte["platos_vendidos"][:12]:
        ancho = int((plato["cantidad"] / max_platos) * 100) if max_platos else 0
        platos_html += f"""
        <div class="fila-barra">
            <div><b>{html_lib.escape(plato["producto"])}</b><br>{plato["cantidad"]} vendidos</div>
            <div class="barra"><span style="width:{ancho}%;"></span></div>
        </div>
        """
    if not platos_html:
        platos_html = "<div class='vacio'>No hay platos vendidos en este rango.</div>"

    metodos_html = ""
    max_metodos = max([metodo["total_bs"] for metodo in reporte["metodos_pago"]] or [1])
    for metodo in reporte["metodos_pago"]:
        ancho = int((metodo["total_bs"] / max_metodos) * 100) if max_metodos else 0
        metodos_html += f"""
        <div class="fila-barra">
            <div><b>{metodo["metodo_label"]}</b><br>{metodo["cantidad"]} pagos · Bs {metodo["total_bs"]} · $ {metodo["total_usd"]}</div>
            <div class="barra"><span style="width:{ancho}%;"></span></div>
        </div>
        """
    if not metodos_html:
        metodos_html = "<div class='vacio'>No hay pagos en este rango.</div>"

    reportes_url = f"/reportes?{urlencode({'desde': desde, 'hasta': hasta})}"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; }}
    .filtros, .panel-dashboard {{ background:white; border-radius:12px; padding:18px; box-shadow:var(--sombra); margin-bottom:16px; }}
    .filtros form {{ display:grid; grid-template-columns: 1fr 1fr auto auto; gap:12px; align-items:end; }}
    .grid-dashboard {{ display:grid; grid-template-columns: repeat(2, 1fr); gap:16px; }}
    .resumen-top {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:16px; }}
    .metrica {{ background:#fff7ed; border-left:5px solid var(--rojo-china); padding:14px; border-radius:8px; }}
    .metrica small {{ display:block; color:#64748b; font-weight:bold; margin-bottom:6px; }}
    .metrica b {{ font-size:22px; }}
    button, .btn-link {{ border:none; border-radius:8px; padding:13px 16px; color:white; background:#15803d; text-decoration:none; font-weight:900; min-height:48px; display:inline-flex; align-items:center; justify-content:center; }}
    .btn-reportes {{ background:#1d4ed8; }}
    .fila-barra {{ display:grid; grid-template-columns: 240px 1fr; gap:12px; align-items:center; padding:10px 0; border-bottom:1px solid #e5e7eb; }}
    .fila-barra:last-child {{ border-bottom:none; }}
    .barra {{ height:18px; background:#fee2e2; border-radius:999px; overflow:hidden; }}
    .barra span {{ display:block; height:100%; background:linear-gradient(90deg, var(--rojo-china), var(--dorado)); }}
    .vacio {{ color:#64748b; padding:12px 0; }}
    @media (max-width: 900px) {{
        .filtros form, .grid-dashboard, .resumen-top, .fila-barra {{ grid-template-columns:1fr; }}
    }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">🏠 Inicio</a><a href="/reportes">📊 Reportes</a>')}
    <div class="contenido">
        <h1>📈 Dashboard</h1>
        <div class="filtros">
            <form method="get" action="/dashboard">
                <div>
                    <label>Fecha desde</label>
                    <input type="date" name="desde" value="{desde}" required>
                </div>
                <div>
                    <label>Fecha hasta</label>
                    <input type="date" name="hasta" value="{hasta}" required>
                </div>
                <button type="submit">🔍 Consultar</button>
                <a class="btn-link btn-reportes" href="{reportes_url}">📊 Ver reporte</a>
            </form>
        </div>

        <div class="resumen-top">
            <div class="metrica"><small>Total facturado USD</small><b>$ {reporte["total_vendido_usd"]}</b></div>
            <div class="metrica"><small>Total facturado Bs</small><b>Bs {reporte["total_vendido_bs"]}</b></div>
            <div class="metrica"><small>Ordenes cerradas</small><b>{reporte["cantidad_ordenes"]}</b></div>
            <div class="metrica"><small>Total cobrado USD equiv.</small><b>$ {reporte["total_equiv_usd"]}</b></div>
        </div>

        <div class="grid-dashboard">
            <div class="panel-dashboard">
                <h2>📅 Ventas por dia</h2>
                {ventas_dia_html}
            </div>
            <div class="panel-dashboard">
                <h2>🧾 Cantidad de ordenes por dia</h2>
                {ordenes_dia_html}
            </div>
            <div class="panel-dashboard">
                <h2>🍽️ Platos mas vendidos</h2>
                {platos_html}
            </div>
            <div class="panel-dashboard">
                <h2>💳 Metodos de pago</h2>
                {metodos_html}
            </div>
        </div>
    </div>
    </body>
    </html>
    """


@app.route("/cierre")
def cierre():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    resumen = construir_resumen_cierre(cursor)
    conn.close()

    ordenes_activas = resumen["ordenes_activas"]
    cantidad_ordenes_cerradas = resumen["cantidad_ordenes_cerradas"]

    if ordenes_activas > 0:
        mensaje = (
            f"<h2 style='color:#e67e22;'>Hay {ordenes_activas} órdenes activas pendientes, "
            "debes cerrarlas o eliminarlas antes de cerrar jornada.</h2>"
        )
    elif cantidad_ordenes_cerradas == 0:
        mensaje = "<h2 style='color:#c0392b;'>No hay ordenes cerradas para esta jornada.</h2>"
    else:
        mensaje = "<h2 style='color:green;'>Jornada lista para cierre</h2>"

    boton = ""
    if ordenes_activas == 0 and cantidad_ordenes_cerradas > 0:
        boton = '<br><br><a href="/cerrar_jornada" class="volver" style="background:#c0392b;">🔒 Confirmar cierre de jornada</a>'

    auditoria_html = ""
    if not resumen["auditoria_pagos"]:
        auditoria_html = "<div class='vacio'>No hay pagos registrados para esta jornada.</div>"
    else:
        auditoria_html += """
        <div class="tabla-wrap">
        <table>
            <thead>
                <tr>
                    <th>Orden</th>
                    <th>Cliente</th>
                    <th>Metodo</th>
                    <th>Monto</th>
                </tr>
            </thead>
            <tbody>
        """
        for pago in resumen["auditoria_pagos"]:
            auditoria_html += f"""
            <tr>
                <td>{texto_numero_orden(pago["numero_orden"])}</td>
                <td>{pago["cliente"] if pago["cliente"] else '-'}</td>
                <td>{pago["metodo_label"]}</td>
                <td>{monto_formateado_segun_metodo(pago["metodo"], pago["monto"])}</td>
            </tr>
            """
        auditoria_html += """
            </tbody>
        </table>
        </div>
        """

    productos_html = ""
    if not resumen["productos"]:
        productos_html = "<div class='vacio'>No hay platos vendidos en la jornada.</div>"
    else:
        productos_html += "<div class='tabla-wrap'><table><thead><tr><th>Producto</th><th>Cantidad</th></tr></thead><tbody>"
        for producto, cantidad in resumen["productos"]:
            productos_html += f"<tr><td>{producto}</td><td>{cantidad}</td></tr>"
        productos_html += "</tbody></table></div>"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ font-family: Arial; background: #f5f6fa; padding: 20px; }}
    .card {{ max-width: 980px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: var(--sombra); }}
    .bloque {{ background: #f8f9fb; padding: 14px; border-radius: 10px; margin-bottom: 14px; }}
    .titulo-bloque {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
    .dato {{ margin: 6px 0; font-size: 17px; }}
    .volver {{ display:inline-block; margin-top:20px; padding:12px 16px; background:#2c3e50; color:white; text-decoration:none; border-radius:6px; }}
    .tabla-wrap {{ overflow:auto; }}
    table {{ width:100%; border-collapse: collapse; background:white; }}
    th, td {{ border-bottom:1px solid #e5e7eb; padding:10px; text-align:left; }}
    th {{ background:#eef2f7; }}
    .vacio {{ color:#7f8c8d; }}
    </style>
    </head>
    <body>
    <div class="card">
        <h1>📊 Cierre del Dia</h1>
        {mensaje}

        <div class="dato"><b>Inicio de jornada:</b> {resumen["inicio_jornada"]}</div>
        <div class="dato"><b>Ordenes cerradas:</b> {cantidad_ordenes_cerradas}</div>

        <div class="bloque">
            <div class="titulo-bloque">💵 VENTAS</div>
            <div class="dato"><b>Total vendido en USD:</b> ${round(resumen["total_ventas_usd"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">💳 COBRADO</div>
            <div class="dato"><b>Pago movil en Bs:</b> Bs {round(resumen["total_pago_movil_bs"], 2)}</div>
            <div class="dato"><b>Efectivo en Bs:</b> Bs {round(resumen["total_efectivo_bs"], 2)}</div>
            <div class="dato"><b>Efectivo en USD:</b> $ {round(resumen["total_efectivo_usd"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">💱 TASA</div>
            <div class="dato"><b>Tasa actual:</b> Bs {round(resumen["tasa"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">🧮 EQUIVALENTES</div>
            <div class="dato"><b>Total cobrado equivalente en Bs:</b> Bs {round(resumen["total_cobrado_equiv_bs"], 2)}</div>
            <div class="dato"><b>Total cobrado equivalente en USD:</b> $ {round(resumen["total_cobrado_equiv_usd"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">⚖️ DIFERENCIA</div>
            <div class="dato"><b>Diferencia en USD entre vendido y cobrado:</b> $ {round(resumen["diferencia_usd"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">🔍 AUDITORIA DE PAGOS</div>
            {auditoria_html}
        </div>

        <div class="bloque">
            <div class="titulo-bloque">🍽️ PLATOS VENDIDOS EN LA JORNADA</div>
            {productos_html}
        </div>

        {boton}
        <br>
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """


@app.route("/cerrar_jornada")
def cerrar_jornada():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    resumen = resumen_cierre_pendiente()

    if resumen["ordenes_activas"] > 0:
        return f"""
        <html>
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}</style>
        </head>
        <body style="font-family:Arial; padding:20px;">
        <h1>🔒 No se puede cerrar la jornada</h1>
        <p>Hay órdenes activas pendientes, debes cerrarlas o eliminarlas antes de cerrar jornada.</p>
        <p>Total pendientes: {resumen['ordenes_activas']}</p>
        <a href="/" class="volver">🏠 Volver</a>
        </body>
        </html>
        """

    if resumen["cantidad_ordenes_cerradas"] == 0:
        return f"""
        <html>
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}</style>
        </head>
        <body style="font-family:Arial; padding:20px;">
        <h1>📊 No hay ordenes cerradas para esta jornada</h1>
        <a href="/" class="volver">🏠 Volver</a>
        </body>
        </html>
        """

    conn = get_connection()
    cursor = conn.cursor()

    fecha_cierre = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    usuario_id = session.get("usuario_id")

    cursor.execute(
        """
        INSERT INTO cierres_caja (fecha, total_ventas, usuario_id)
        VALUES (?, ?, ?)
        """,
        (fecha_cierre, resumen["total_ventas_bs"], usuario_id),
    )
    cierre_id = obtener_ultimo_id(cursor, "cierres_caja")

    for producto, cantidad in resumen["productos"]:
        cursor.execute(
            """
            INSERT INTO cierre_detalle (cierre_id, producto, cantidad)
            VALUES (?, ?, ?)
            """,
            (cierre_id, producto, cantidad),
        )

    orden_ids = resumen["orden_ids"]
    if orden_ids:
        placeholders = ",".join("?" for _ in orden_ids)
        cursor.execute(
            f"""
            UPDATE ordenes
            SET cierre_id = ?
            WHERE id IN ({placeholders})
            """,
            [cierre_id] + orden_ids,
        )

    conn.commit()
    conn.close()

    productos_html = ""
    for producto, cantidad in resumen["productos"]:
        productos_html += f"<li>{producto}: {cantidad}</li>"

    if not productos_html:
        productos_html = "<li>Sin productos registrados</li>"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ font-family: Arial; background: #f5f6fa; padding: 20px; }}
    .card {{ max-width: 760px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
    h1 {{ margin-top: 0; }}
    .total {{ font-size: 22px; font-weight: bold; color: #27ae60; margin-bottom: 8px; }}
    .volver {{ display:inline-block; margin-top:20px; padding:12px 16px; background:#2c3e50; color:white; text-decoration:none; border-radius:6px; }}
    </style>
    </head>
    <body>
    <div class="card">
        <h1>✅ CIERRE REALIZADO</h1>
        <p>Cierre #{cierre_id}</p>
        <p>Inicio de jornada: {resumen["inicio_jornada"]}</p>
        <p>Fecha de cierre: {fecha_cierre}</p>
        <p>Ordenes cerradas: {resumen["cantidad_ordenes_cerradas"]}</p>
        <div class="total">Total vendido: $ {round(resumen["total_ventas_usd"], 2)}</div>
        <div class="total">Total cobrado equivalente: Bs {round(resumen["total_cobrado_equiv_bs"], 2)} / $ {round(resumen["total_cobrado_equiv_usd"], 2)}</div>
        <div class="total">Diferencia: $ {round(resumen["diferencia_usd"], 2)}</div>
        <h2>🍽️ Productos vendidos</h2>
        <ul>{productos_html}</ul>
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """


@app.route("/cocina")
def pantalla_cocina():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.tipo, o.referencia, o.fecha_hora, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.estado = 'en cocina'
        ORDER BY o.numero_orden ASC, o.fecha_hora ASC
        """
    )
    ordenes = cursor.fetchall()

    ahora = ahora_venezuela()
    arroz_html = ""
    caliente_html = ""
    total_ordenes = len(ordenes)

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        """ + estilos_base() + """
        body { font-family: Arial; background:black; color:white; font-size:22px; margin:0; }
        .topbar { padding:12px 16px; background:#111; display:flex; justify-content:space-between; align-items:center; gap:10px; }
        .topbar a { color:white; text-decoration:none; background:#2c3e50; padding:10px 12px; border-radius:5px; }
        .container { display:flex; }
        .col { width:50%; padding:10px; box-sizing:border-box; }
        .orden { border:4px solid white; margin:10px; padding:15px; border-radius:10px; }
        .green { border-color: green; }
        .orange { border-color: orange; }
        .red { border-color: red; }
        .btn { padding:10px; background:green; color:white; border:none; font-size:18px; }
        .mesonera { color:#f1c40f; font-weight:bold; }
        h1 { text-align:center; }
        @media (max-width: 768px) { .container { flex-direction: column; } .col { width:100%; } }
    </style>
    <script>
        let lastCount = 0;
        function checkNewOrders(currentCount) {
            if (currentCount > lastCount) {
                let audio = new Audio('https://www.soundjay.com/buttons/sounds/button-3.mp3');
                audio.play();
            }
            lastCount = currentCount;
        }
    </script>
    </head>
    <body>
    <div class="topbar">
        <div>Usuario: <b>""" + usuario_activo() + """</b></div>
        <div style="display:flex; gap:8px;">
            <a href="/">🏠 Inicio</a>
            <a href="/logout">🚪 Cerrar sesión</a>
        </div>
    </div>
    <h1>🍳 COCINA</h1>
    <div class="container">
        <div class="col">
            <h2>🍚 ESTACION ARROZ</h2>
    """

    for o in ordenes:
        fecha_orden = parsear_fecha_hora_venezuela(o[4])
        minutos = (ahora - fecha_orden).total_seconds() / 60

        if minutos < 5:
            color_class = "green"
        elif minutos < 10:
            color_class = "orange"
        else:
            color_class = "red"

        cursor.execute("SELECT producto FROM orden_items WHERE orden_id=?", (o[0],))
        items = cursor.fetchall()
        tiene_arroz = any("Arroz chino" in i[0] for i in items)
        tiene_otro = any("Arroz chino" not in i[0] for i in items)

        bloque = f"""
        <div class="orden {color_class}">
            <h2>Orden {texto_numero_orden(o[1])}</h2>
            <p>{o[2]} - {o[3]}</p>
            <p class="mesonera">👩 Mesonera: {(o[5] or '-').upper()}</p>
            <p>{int(minutos)} min</p>
        """

        for i in items:
            bloque += f"<p>- {i[0]}</p>"

        bloque += f"""
            <a href="/listo/{o[0]}">
                <button class="btn">✅ LISTO</button>
            </a>
        </div>
        """

        if tiene_arroz:
            arroz_html += bloque
        if tiene_otro:
            caliente_html += bloque

    html += arroz_html
    html += """
        </div>
        <div class="col">
            <h2>🔥 ESTACION CALIENTE</h2>
    """
    html += caliente_html
    html += f"""
        </div>
    </div>
    <script>
        checkNewOrders({total_ordenes});
    </script>
    </body>
    </html>
    """
    conn.close()
    return html


@app.route("/listo/<int:orden_id>")
def marcar_listo(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ordenes SET estado='listo' WHERE id=? AND cierre_id IS NULL",
        (orden_id,),
    )
    conn.commit()
    conn.close()
    return redirect("/cocina")


@app.route("/ordenes_cocina")
def ordenes_cocina():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT o.id, o.numero_orden, o.tipo, o.cliente, o.referencia, u.nombre,
                   o.estado, o.reimpresion_token
            FROM ordenes o
            LEFT JOIN usuarios u ON o.usuario_id = u.id
            WHERE o.estado = 'en cocina'
               OR (o.estado = 'cerrada' AND o.reimpresion_token IS NOT NULL)
               OR (o.estado = 'en cocina' AND o.reimpresion_token IS NOT NULL)
            ORDER BY o.numero_orden ASC, o.fecha_hora ASC
            """
        )

        ordenes = []
        reimpresiones_emitidas = []

        for o in cursor.fetchall():
            cursor.execute(
                """
                SELECT producto
                FROM orden_items
                WHERE orden_id=?
                """,
                (o[0],),
            )
            items = [i[0] for i in cursor.fetchall()]

            evento_impresion = f"{o[0]}-{o[7] if o[7] else 'base'}"

            ordenes.append(
                {
                    "id": o[0],
                    "numero": o[1],
                    "tipo": o[2],
                    "cliente": o[3],
                    "referencia": o[4],
                    "usuario": o[5] if o[5] else "N/A",
                    "estado": o[6],
                    "items": items,
                    "reimpresion_token": o[7],
                    "evento_impresion": evento_impresion,
                }
            )

            if o[7]:
                reimpresiones_emitidas.append(o[0])

        if reimpresiones_emitidas:
            placeholders = ",".join("?" for _ in reimpresiones_emitidas)
            cursor.execute(
                f"""
                UPDATE ordenes
                SET reimpresion_token=NULL
                WHERE id IN ({placeholders})
                """,
                reimpresiones_emitidas,
            )
            conn.commit()

        conn.close()
        return jsonify(ordenes)

    except Exception as e:
        print("ERROR EN ORDENES_COCINA:", e)
        return jsonify([])


@app.route("/factura/<int:orden_id>")
def factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT o.numero_orden, o.tipo, o.referencia, o.cliente, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=?
        """,
        (orden_id,),
    )
    o = cursor.fetchone()
    if not o:
        conn.close()
        return "Orden no encontrada"

    cursor.execute(
        """
        SELECT producto, precio
        FROM orden_items
        WHERE orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()
    conn.close()

    total = sum(i[1] for i in items)
    html = f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body {{ font-family: Arial; padding: 20px; max-width: 400px; margin: auto; }}
    .titulo {{ text-align: center; font-size: 22px; font-weight: bold; }}
    .numero {{ text-align: right; font-size: 20px; font-weight: bold; }}
    .sep {{ border-top: 1px dashed black; margin: 10px 0; }}
    .item {{ display: flex; justify-content: space-between; margin: 5px 0; }}
    .total {{ font-size: 18px; font-weight: bold; text-align: right; }}
    </style>
    </head>
    <body>
    <div class="titulo">CHINA HOUSE</div>
    <div class="numero">Orden {texto_numero_orden(o[0])}</div>
    <div class="sep"></div>
    <div>
        <b>Tipo:</b> {o[1]}<br>
        <b>Cliente:</b> {o[3] if o[3] else '-'}<br>
        <b>Referencia:</b> {o[2]}<br>
        <b>Mesonera:</b> {o[4] if o[4] else '-'}
    </div>
    <div class="sep"></div>
    """

    for i in items:
        html += f"""
        <div class="item">
            <span>{i[0]}</span>
            <span>${i[1]}</span>
        </div>
        """

    html += f"""
    <div class="sep"></div>
    <div class="total">TOTAL: ${round(total, 2)}</div>
    </body>
    </html>
    """
    return html


@app.route("/cerrar_dia")
def cerrar_dia():
    return redirect("/cerrar_jornada")


@app.route("/facturas_pendientes")
def facturas_pendientes():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT o.id, o.numero_orden, o.tipo, o.cliente, o.referencia, u.nombre
            FROM ordenes o
            LEFT JOIN usuarios u ON o.usuario_id = u.id
            WHERE o.facturar = 1
            """
        )
        ordenes = cursor.fetchall()

        resultado = []

        for o in ordenes:
            cursor.execute(
                """
                SELECT producto, precio
                FROM orden_items
                WHERE orden_id=?
                """,
                (o[0],),
            )
            items = cursor.fetchall()

            resultado.append(
                {
                    "id": o[0],
                    "numero": o[1],
                    "tipo": o[2],
                    "cliente": o[3],
                    "referencia": o[4],
                    "usuario": o[5] if o[5] else "N/A",
                    "items": [f"{i[0]} - ${i[1]}" for i in items],
                    "total": sum(i[1] for i in items),
                }
            )

        conn.close()
        return jsonify(resultado)

    except Exception as e:
        print("ERROR EN FACTURAS:", e)
        return jsonify([])


@app.route("/activar_factura/<int:orden_id>")
def activar_factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ordenes SET facturar=1 WHERE id=? AND cierre_id IS NULL",
        (orden_id,),
    )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/desactivar_factura/<int:orden_id>")
def desactivar_factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET facturar=0 WHERE id=?", (orden_id,))
    conn.commit()
    conn.close()
    return "ok"


with app.app_context():
    init_db()
    cargar_productos()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
