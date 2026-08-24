from collections import defaultdict
import datetime
import html as html_lib
import io
import json
import os
import re
import sqlite3
import zipfile
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from flask import Flask, Response, g, jsonify, redirect, request, session
import pytz

try:
    import psycopg2
except Exception:
    psycopg2 = None

from app.shared.constants.system import (
    ETIQUETAS_METODO_PAGO,
    METODOS_PAGO_VALIDOS,
    ROLES_USUARIO_VALIDOS,
    SABORES_REFRESCO,
)


CLAVE_SUPERVISOR = "0102"
VENEZUELA_TZ = pytz.timezone("America/Caracas")

ORDEN_CATEGORIAS_POS = [
    "Neko Combos",
    "Promociones Neko",
    "Neko Dúo",
    "Neko Clan",
    "Favoritos de Neko",
    "Bebidas",
    "Delivery",
    "Extras",
]

COLORES_CATEGORIAS_POS = {
    "Neko Combos":      "#0d4a32",
    "Promociones Neko": "#be123c",
    "Neko Dúo":         "#c2410c",
    "Neko Clan":        "#1e3a8a",
    "Favoritos de Neko": "#0f766e",
    "Bebidas":          "#0284c7",
    "Delivery":         "#6d28d9",
    "Extras":           "#374151",
}

FAVORITOS_COMBO_1 = [
    "Pollo Agridulce",
    "Chop Suey de Pollo",
]
COMBOS_PERSONALES = {
    "Neko Combo 1": {
        "arroz": "Arroz de pollo",
        "bebida": "Coca Cola Personal",
        "favoritos_disponibles": FAVORITOS_COMBO_1,
        "favoritos_fijos": [],
    },
    "Neko Combo 2": {
        "arroz": "Arroz de pollo",
        "bebida": "Coca Cola Personal",
        "favoritos_disponibles": [],
        "favoritos_fijos": ["Pollo Agridulce", "Chop Suey de Pollo"],
    },
    "Neko Combo 3": {
        "arroz": "Arroz triple",
        "bebida": "Coca Cola Personal",
        "favoritos_disponibles": [],
        "favoritos_fijos": ["Pollo Agridulce", "Chop Suey de Pollo"],
    },
}
COMBOS_CON_FAVORITO = {"Neko Combo 1": FAVORITOS_COMBO_1}
COMBOS_JSON = {
    "Neko Combo 1": "combo1",
    "Neko Combo 2": "combo2",
    "Neko Combo 3": "combo3",
}
ACOMPANANTES_COMBO = [
    "Pollo Agridulce",
    "Pollo BBQ",
    "Pollo BBQ/Agridulce",
    "Chop Suey",
    "Lumpia",
]
BEBIDAS_COMBO = [
    "Coca Cola",
    "Frescolita",
    "Chinotto",
    "Agua de Manzana",
]
COMBOS_CANTIDAD_ACOMPANANTES = {
    "Neko Combo 1": 1,
    "Neko Combo 2": 2,
    "Neko Combo 3": 2,
}
POLLOS_PROMOCION = [
    "Pollo BBQ",
    "Pollo Agridulce",
    "Pollo BBQ/Agridulce",
]
ARROCES_PROMOCION = ["Pollo + Cerdo", "Pollo + Camarón", "Triple"]
PROMOCIONES_NEKO = {
    "Wok para Dos": {"cantidad_arroces": 1, "cantidad_refrescos": 1, "refresco": "Refresco 1 Lt"},
    "Familiar": {"cantidad_arroces": 1, "cantidad_refrescos": 1, "refresco": "Refresco 1.5 Lt"},
    "Mega Familiar": {"cantidad_arroces": 2, "cantidad_refrescos": 2, "refresco": "Refresco 1.5 Lt"},
}
PROMOCIONES_JSON = {
    "Wok para Dos": "wok_para_dos",
    "Familiar": "familiar",
    "Mega Familiar": "mega_familiar",
}
PROMOCIONES_CON_POLLO = {"Familiar", "Mega Familiar"}
PROMO_EXTRA_LUMPIAS_NOMBRE = "Promo extra: Ración de Lumpias"
PROMO_EXTRA_LUMPIAS_PRECIO = 3.00
DELIVERY_MONTOS_RAPIDOS = [0.50, 1.00, 1.50, 2.00, 2.50, 3.00, 3.50]
DELIVERY_MONTO_MAXIMO = 100.0

PRODUCTOS_MENU_NEKO = [
    ("Neko Combo 1", 5.30, "Neko Combos"),
    ("Neko Combo 2", 6.00, "Neko Combos"),
    ("Neko Combo 3", 7.00, "Neko Combos"),
    ("Wok para Dos", 13.00, "Promociones Neko"),
    ("Familiar", 20.00, "Promociones Neko"),
    ("Mega Familiar", 38.00, "Promociones Neko"),
    ("Neko Dúo Pollo Cerdo", 8.00, "Neko Dúo"),
    ("Neko Dúo Pollo Camarón", 8.00, "Neko Dúo"),
    ("Neko Dúo Triple", 9.00, "Neko Dúo"),
    ("Neko Clan Pollo Cerdo", 11.00, "Neko Clan"),
    ("Neko Clan Pollo Camarón", 11.00, "Neko Clan"),
    ("Neko Clan Triple", 13.00, "Neko Clan"),
    ("Pollo Agridulce", 4.80, "Favoritos de Neko"),
    ("Chop Suey de Pollo", 5.00, "Favoritos de Neko"),
    ("Chop Suey de Vegetales", 4.00, "Favoritos de Neko"),
    ("Ración de Lumpias (2u)", 4.00, "Favoritos de Neko"),
    ("1/2 Ración de Lumpias (1u)", 2.50, "Favoritos de Neko"),
    ("Tequeños (5u)", 3.00, "Favoritos de Neko"),
    ("Ración de Pan Chino (4u)", 1.00, "Favoritos de Neko"),
    ("Refresco 1 Lt", 1.20, "Bebidas"),
    ("Refresco 1.5 Lt", 1.80, "Bebidas"),
    ("Refresco 2 Lt", 2.20, "Bebidas"),
    ("Delivery 0.5", 0.50, "Delivery"),
    ("Delivery 1", 1.00, "Delivery"),
    ("Delivery 1.5", 1.50, "Delivery"),
    ("Delivery 2", 2.00, "Delivery"),
    ("Delivery 2.5", 2.50, "Delivery"),
    ("Delivery 3", 3.00, "Delivery"),
    ("Delivery 3.5", 3.50, "Delivery"),
    ("Extra de Salsa", 0.25, "Extras"),
]


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


def es_categoria_delivery(categoria):
    return (categoria or "").strip().lower() == "delivery"


def es_producto_delivery_legacy(nombre, categoria=None):
    nombre_limpio = (nombre or "").strip().lower()
    if es_categoria_delivery(categoria):
        return True
    return bool(re.fullmatch(r"delivery\s+\d+(?:[.,]\d{1,2})?", nombre_limpio))


def normalizar_monto_delivery(valor):
    texto = str(valor if valor is not None else "").strip().replace(",", ".")
    if texto == "":
        texto = "0"
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", texto):
        raise ValueError("El monto de delivery debe ser cero o positivo, con maximo 2 decimales.")
    monto = round(float(texto), 2)
    if monto < 0:
        raise ValueError("El monto de delivery no puede ser negativo.")
    if monto > DELIVERY_MONTO_MAXIMO:
        raise ValueError(f"El monto de delivery no puede superar ${DELIVERY_MONTO_MAXIMO:.2f}.")
    return monto


def calcular_totales_visuales_delivery(items, delivery_usd):
    venta_restaurante = 0.0
    delivery_legacy = 0.0
    for item in items:
        producto = item[0]
        precio = a_float(item[1])
        categoria = item[4] if len(item) > 4 else None
        if es_producto_delivery_legacy(producto, categoria):
            delivery_legacy += precio
        else:
            venta_restaurante += precio
    delivery_explicit = a_float(delivery_usd)
    return {
        "venta_restaurante_usd": round(venta_restaurante, 2),
        "delivery_usd": round(delivery_explicit, 2),
        "delivery_legacy_usd": round(delivery_legacy, 2),
        "total_cliente_usd": round(venta_restaurante + delivery_legacy + delivery_explicit, 2),
    }


def calcular_totales_financieros_delivery(items, tasa, descuento_bs, delivery_usd):
    tasa_cobro = a_float(tasa)
    if tasa_cobro <= 0:
        raise ValueError("La tasa de cobro debe ser mayor a 0")

    descuento_bs = round(a_float(descuento_bs), 2)
    delivery_explicit = round(a_float(delivery_usd), 2)
    if delivery_explicit < 0:
        raise ValueError("El monto de delivery no puede ser negativo")

    subtotal_restaurante_usd = 0.0
    delivery_legacy_usd = 0.0
    for item in items:
        producto = item[0]
        precio = a_float(item[1])
        categoria = item[2] if len(item) > 2 else None
        if es_producto_delivery_legacy(producto, categoria):
            delivery_legacy_usd += precio
        else:
            subtotal_restaurante_usd += precio

    subtotal_restaurante_usd = round(subtotal_restaurante_usd, 2)
    delivery_legacy_usd = round(delivery_legacy_usd, 2)
    tiene_delivery_legacy = delivery_legacy_usd > TOLERANCIA_COBRO

    if tiene_delivery_legacy:
        if delivery_explicit > TOLERANCIA_COBRO:
            raise ValueError("Esta orden contiene delivery legacy y delivery explicito. Corrige la orden antes de cobrar.")
        precios_legacy = [item[1] for item in items]
        totales_legacy = calcular_totales_cobro(precios_legacy, tasa_cobro, descuento_bs)
        return {
            "modo": "legacy",
            "tasa": tasa_cobro,
            "subtotal_restaurante_usd": totales_legacy["subtotal_usd"],
            "descuento_bs": totales_legacy["descuento_bs"],
            "venta_restaurante_usd": totales_legacy["total_usd"],
            "delivery_usd": 0.0,
            "delivery_legacy_usd": delivery_legacy_usd,
            "total_cliente_usd": totales_legacy["total_usd"],
            "venta_restaurante_bs": totales_legacy["total_bs"],
            "delivery_bs": 0.0,
            "total_cliente_bs": totales_legacy["total_bs"],
            "subtotal_snapshot_usd": totales_legacy["subtotal_usd"],
            "total_usd": totales_legacy["total_usd"],
            "total_bs": totales_legacy["total_bs"],
            "snapshot_delivery_usd": None,
            "snapshot_venta_restaurante_usd": None,
            "snapshot_total_cliente_usd": None,
        }

    subtotal_restaurante_bs = round(subtotal_restaurante_usd * tasa_cobro, 2)
    venta_restaurante_bs = round(max(subtotal_restaurante_bs - descuento_bs, 0.0), 2)
    venta_restaurante_usd = round((venta_restaurante_bs / tasa_cobro) if tasa_cobro else 0.0, 2)
    delivery_bs = round(delivery_explicit * tasa_cobro, 2)
    total_cliente_bs = round(venta_restaurante_bs + delivery_bs, 2)
    total_cliente_usd = round(venta_restaurante_usd + delivery_explicit, 2)

    return {
        "modo": "explicito",
        "tasa": tasa_cobro,
        "subtotal_restaurante_usd": subtotal_restaurante_usd,
        "descuento_bs": descuento_bs,
        "venta_restaurante_usd": venta_restaurante_usd,
        "delivery_usd": delivery_explicit,
        "delivery_legacy_usd": 0.0,
        "total_cliente_usd": total_cliente_usd,
        "venta_restaurante_bs": venta_restaurante_bs,
        "delivery_bs": delivery_bs,
        "total_cliente_bs": total_cliente_bs,
        "subtotal_snapshot_usd": subtotal_restaurante_usd,
        "total_usd": venta_restaurante_usd,
        "total_bs": venta_restaurante_bs,
        "snapshot_delivery_usd": delivery_explicit,
        "snapshot_venta_restaurante_usd": venta_restaurante_usd,
        "snapshot_total_cliente_usd": total_cliente_usd,
    }


def es_combo_con_favorito(nombre):
    return (nombre or "").strip() in COMBOS_CON_FAVORITO


def normalizar_sabor_refresco(sabor):
    sabor_limpio = (sabor or "").strip()
    if not sabor_limpio or len(sabor_limpio) > 40:
        return ""

    for opcion in SABORES_REFRESCO:
        if sabor_limpio.lower() == opcion.lower():
            return opcion

    sabor_limpio = sabor_limpio.replace("<", "").replace(">", "")
    return sabor_limpio.strip()


def normalizar_indicacion_item(indicacion):
    indicacion = (indicacion or "").strip()
    indicacion = re.sub(r"\s+", " ", indicacion)
    return indicacion[:500]


def deserializar_indicacion(indicacion):
    texto = (indicacion or "").strip()
    if not texto or not texto.startswith("{"):
        return None
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    if datos.get("version") != 1:
        return None
    return datos


def es_indicacion_json(indicacion):
    return deserializar_indicacion(indicacion) is not None


def serializar_indicacion(datos):
    if not isinstance(datos, dict):
        return ""
    datos = dict(datos)
    datos.setdefault("version", 1)
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def datos_combo_desde_indicacion(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    datos = deserializar_indicacion(indicacion)
    if not datos or datos.get("tipo") != "combo":
        return None
    if COMBOS_JSON.get(producto) != datos.get("producto"):
        return None
    acompanantes = datos.get("acompanantes")
    bebida = datos.get("bebida")
    if not isinstance(acompanantes, list) or not isinstance(bebida, str):
        return None
    lineas = [str(valor).strip() for valor in acompanantes if str(valor).strip()]
    bebida = bebida.strip()
    if bebida:
        lineas.append(bebida)
    if not lineas:
        return None
    return {"datos": datos, "lineas": lineas}


def texto_descripcion_combo_orden(producto, indicacion):
    combo = datos_combo_desde_indicacion(producto, indicacion)
    if not combo:
        return ""
    return "\n".join(f"• {linea}" for linea in combo["lineas"])


def texto_descripcion_combo_cocina(producto, indicacion):
    combo = datos_combo_desde_indicacion(producto, indicacion)
    if not combo:
        return ""
    datos = combo["datos"]
    lineas = [
        f"    - {str(acompanante).strip()}"
        for acompanante in datos.get("acompanantes", [])
        if str(acompanante).strip()
    ]
    bebida = (datos.get("bebida") or "").strip()
    if bebida:
        lineas.append(f"    [{bebida}]")
    return "\n".join(lineas)


def texto_descripcion_combo_factura(producto, indicacion):
    combo = datos_combo_desde_indicacion(producto, indicacion)
    if not combo:
        return ""
    return "\n".join(f"• {linea}" for linea in combo["lineas"])


def datos_promocion_desde_indicacion(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    datos = deserializar_indicacion(indicacion)
    if not datos or datos.get("tipo") != "promocion":
        return None
    if PROMOCIONES_JSON.get(producto) != datos.get("producto"):
        return None
    pollo = datos.get("pollo")
    arroces = datos.get("arroces")
    bebidas = datos.get("bebidas")
    if pollo is not None and not isinstance(pollo, str):
        return None
    if not isinstance(arroces, list) or not isinstance(bebidas, list):
        return None
    lineas = []
    pollo = (pollo or "").strip()
    if pollo:
        lineas.append(pollo)
    lineas.extend(f"Arroz {str(arroz).strip()}" for arroz in arroces if str(arroz).strip())
    lineas.extend(str(bebida).strip() for bebida in bebidas if str(bebida).strip())
    if not lineas:
        return None
    return {"datos": datos, "lineas": lineas}


def texto_descripcion_promocion_orden(producto, indicacion):
    promocion = datos_promocion_desde_indicacion(producto, indicacion)
    if not promocion:
        return ""
    return "\n".join(f"• {linea}" for linea in promocion["lineas"])


def texto_descripcion_promocion_cocina(producto, indicacion):
    promocion = datos_promocion_desde_indicacion(producto, indicacion)
    if not promocion:
        return ""
    datos = promocion["datos"]
    lineas = []
    pollo = (datos.get("pollo") or "").strip()
    if pollo:
        lineas.append(f"    - {pollo}")
    lineas.extend(
        f"    - Arroz {str(arroz).strip()}"
        for arroz in datos.get("arroces", [])
        if str(arroz).strip()
    )
    lineas.extend(
        f"    [{str(bebida).strip()}]"
        for bebida in datos.get("bebidas", [])
        if str(bebida).strip()
    )
    return "\n".join(lineas)


def texto_descripcion_promocion_factura(producto, indicacion):
    promocion = datos_promocion_desde_indicacion(producto, indicacion)
    if not promocion:
        return ""
    return "\n".join(f"• {linea}" for linea in promocion["lineas"])


def quitar_prefijo_cantidad_visual(texto):
    texto = (texto or "").strip()

    while True:
        limpio = re.sub(r"^1x\s+(\d+x\s+.+)$", r"\1", texto, flags=re.IGNORECASE)
        if limpio == texto:
            return texto
        texto = limpio.strip()


def separar_prefijo_cantidad(producto):
    producto = quitar_prefijo_cantidad_visual(producto)
    match = re.match(r"^(\d+)x\s+(.+)$", producto, flags=re.IGNORECASE)
    if not match:
        return 1, producto

    cantidad = int(match.group(1))
    producto_limpio = match.group(2).strip()
    return max(cantidad, 1), producto_limpio


def producto_sin_prefijo_cantidad(producto):
    _, producto_limpio = separar_prefijo_cantidad(producto)
    return producto_limpio


def texto_item_con_indicacion(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    indicacion = normalizar_indicacion_item(indicacion)
    if indicacion:
        return f"{producto} ({indicacion})"
    return producto


NOMBRES_COCINA_SIMPLIFICADOS = {
    "Neko Combo 1": "COMBO #1",
    "Neko Combo 2": "COMBO #2",
    "Neko Combo 3": "COMBO #3",
    "Wok para Dos": "WOK PARA DOS",
    "Familiar": "FAMILIAR",
    "Mega Familiar": "MEGA FAMILIAR",
}


def nombre_producto_cocina(producto):
    producto = producto_sin_prefijo_cantidad(producto)
    return NOMBRES_COCINA_SIMPLIFICADOS.get(producto, producto)


def indicacion_operativa_cocina(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    indicacion = normalizar_indicacion_item(indicacion)
    if not indicacion:
        return ""

    partes = [parte.strip() for parte in indicacion.split(";") if parte.strip()]

    if producto in COMBOS_PERSONALES:
        descripcion_combo = texto_descripcion_combo_cocina(producto, indicacion)
        if descripcion_combo:
            return descripcion_combo
        detalles = []
        bebidas = []
        for parte in partes:
            etiqueta, separador, valor = parte.partition(":")
            if not separador:
                continue
            etiqueta_limpia = etiqueta.strip().lower()
            valor_limpio = valor.strip()
            if not valor_limpio:
                continue
            if "bebida" in etiqueta_limpia:
                bebidas.append(f"    [{valor_limpio}]")
            elif etiqueta_limpia.startswith("favorito") or etiqueta_limpia.startswith("acompa"):
                detalles.append(f"    - {valor_limpio}")
        return "\n".join(detalles + bebidas)

    if producto in PROMOCIONES_NEKO:
        descripcion_promocion = texto_descripcion_promocion_cocina(producto, indicacion)
        if descripcion_promocion:
            return descripcion_promocion
        detalles = []
        bebidas = []
        for parte in partes:
            etiqueta, separador, valor = parte.partition(":")
            if not separador:
                continue
            etiqueta_limpia = etiqueta.strip()
            valor_limpio = valor.strip()
            etiqueta_lower = etiqueta_limpia.lower()
            if not valor_limpio:
                continue
            if etiqueta_lower.startswith("pollo"):
                detalles.append(f"    - {valor_limpio}")
                continue
            if etiqueta_lower.startswith("arroz"):
                if producto != "Mega Familiar" and etiqueta_lower == "arroz 1":
                    etiqueta_limpia = "Arroz"
                detalles.append(f"    - {etiqueta_limpia}: {valor_limpio}")
                continue
            if "refresco" in etiqueta_lower or "bebida" in etiqueta_lower:
                bebidas.append(f"    [{valor_limpio}]")
        return "\n".join(detalles + bebidas)

    if producto == PROMO_EXTRA_LUMPIAS_NOMBRE:
        return ""

    return indicacion


def agrupar_items_comanda(items, incluir_cantidad=True, observacion=""):
    grupos = []
    indices = {}

    items = list(items)
    i = 0
    while i < len(items):
        producto, indicacion = items[i]
        cantidad_producto, producto = separar_prefijo_cantidad(producto)
        indicacion = normalizar_indicacion_item(indicacion)
        indicacion_cocina = indicacion_operativa_cocina(producto, indicacion)
        siguiente_es_extra_promocion = False

        if producto in PROMOCIONES_NEKO and i + 1 < len(items):
            siguiente_producto_raw, siguiente_indicacion = items[i + 1]
            _, siguiente_producto = separar_prefijo_cantidad(siguiente_producto_raw)
            siguiente_indicacion = normalizar_indicacion_item(siguiente_indicacion)
            siguiente_es_extra_promocion = (
                siguiente_producto == PROMO_EXTRA_LUMPIAS_NOMBRE
                and siguiente_indicacion == f"Agregado con: {producto}"
            )
            if siguiente_es_extra_promocion:
                lineas_indicacion = indicacion_cocina.splitlines() if indicacion_cocina else []
                indice_bebida = next(
                    (
                        idx
                        for idx, linea in enumerate(lineas_indicacion)
                        if linea.strip().startswith("[")
                    ),
                    len(lineas_indicacion),
                )
                lineas_indicacion.insert(indice_bebida, "    + Extra de Lumpia")
                indicacion_cocina = "\n".join(lineas_indicacion)

        clave = (producto, indicacion_cocina)

        if clave not in indices:
            indices[clave] = len(grupos)
            grupos.append(
                {
                    "producto": producto,
                    "indicacion": indicacion_cocina,
                    "cantidad": 0,
                }
            )

        grupos[indices[clave]]["cantidad"] += cantidad_producto
        i += 2 if siguiente_es_extra_promocion else 1

    lineas = []
    for grupo in grupos:
        texto = nombre_producto_cocina(grupo["producto"])
        if grupo["indicacion"] and "\n" in grupo["indicacion"]:
            if incluir_cantidad and grupo["cantidad"] > 1:
                texto = f"{grupo['cantidad']}x {texto}"
            lineas.append(f"{texto}\n{grupo['indicacion']}")
            continue
        if grupo["indicacion"]:
            texto = f"{texto} ({grupo['indicacion']})"
        if incluir_cantidad:
            texto = f"{grupo['cantidad']}x {texto}"
        lineas.append(quitar_prefijo_cantidad_visual(texto))

    observacion = (observacion or "").strip()
    if observacion:
        lineas.append(f"    OBS: {observacion}")

    return lineas


def agrupar_items_factura(items):
    grupos = []
    indices = {}

    for producto, precio, indicacion in items:
        cantidad_producto, producto = separar_prefijo_cantidad(producto)
        indicacion = normalizar_indicacion_item(indicacion)
        precio = a_float(precio)
        clave = (producto, indicacion)

        if clave not in indices:
            indices[clave] = len(grupos)
            grupos.append(
                {
                    "producto": producto,
                    "indicacion": indicacion,
                    "cantidad": 0,
                    "precio_total": 0.0,
                }
            )

        grupos[indices[clave]]["cantidad"] += cantidad_producto
        grupos[indices[clave]]["precio_total"] += precio

    resultado = []
    for grupo in grupos:
        descripcion = (
            texto_descripcion_combo_factura(grupo["producto"], grupo["indicacion"])
            or texto_descripcion_promocion_factura(grupo["producto"], grupo["indicacion"])
        )
        if descripcion:
            texto = f"{grupo['cantidad']}x {producto_sin_prefijo_cantidad(grupo['producto'])}\n{descripcion}"
        else:
            texto = f"{grupo['cantidad']}x {texto_item_con_indicacion(grupo['producto'], grupo['indicacion'])}"
        resultado.append(
            {
                "texto": quitar_prefijo_cantidad_visual(texto),
                "precio_total": grupo["precio_total"],
            }
        )
    return resultado


def preparar_lineas_factura(items, venta_restaurante_usd=None, delivery_usd=None, total_cliente_usd=None):
    delivery_explicito = round(a_float(delivery_usd), 2)
    if delivery_explicito > TOLERANCIA_COBRO:
        consumo = (
            round(a_float(venta_restaurante_usd), 2)
            if venta_restaurante_usd is not None
            else round(sum(a_float(item[1]) for item in items), 2)
        )
        total = (
            round(a_float(total_cliente_usd), 2)
            if total_cliente_usd is not None
            else round(consumo + delivery_explicito, 2)
        )
        return [
            {"texto": "Consumo Neko Wok", "precio_total": consumo},
            {"texto": "Delivery", "precio_total": delivery_explicito},
        ], total

    items_agrupados = agrupar_items_factura(items)
    total = round(sum(a_float(i[1]) for i in items), 2)
    return items_agrupados, total


def etiqueta_metodo_pago(metodo):
    return ETIQUETAS_METODO_PAGO.get(normalizar_metodo_pago(metodo), metodo or "-")


def monto_formateado_segun_metodo(metodo, monto):
    metodo = normalizar_metodo_pago(metodo)
    monto = a_float(monto)
    if metodo == "usd":
        return f"$ {round(monto, 2)}"
    return f"Bs {round(monto, 2)}"


def formato_usd(monto):
    return f"$ {a_float(monto):,.2f}"


def formato_bs(monto):
    return f"Bs {a_float(monto):,.2f}"


def texto_fecha_corta(fecha):
    if not fecha:
        return "-"
    return str(fecha)[:16]


def estado_cxc_badge(estado):
    estado = (estado or "pendiente").lower()
    clases = {
        "pendiente": "estado-pendiente",
        "pagada": "estado-pagada",
        "anulada": "estado-anulada",
    }
    return (
        f'<span class="badge-estado {clases.get(estado, "estado-anulada")}">'
        f'{html_lib.escape(estado)}</span>'
    )


def convertir_pago_equivalente(metodo, monto, tasa):
    metodo = normalizar_metodo_pago(metodo)
    monto = a_float(monto)

    if metodo == "usd":
        return monto * tasa, monto

    if metodo in ("punto_venta", "bs_pago_movil", "bs_efectivo"):
        usd = (monto / tasa) if tasa else 0.0
        return monto, usd

    return 0.0, 0.0


def calcular_totales_cobro(precios_items, tasa, descuento_bs):
    subtotal_usd = round(sum(a_float(precio) for precio in precios_items), 2)
    tasa_cobro = a_float(tasa)
    if tasa_cobro <= 0:
        raise ValueError("La tasa de cobro debe ser mayor a 0")
    descuento_bs = round(a_float(descuento_bs), 2)
    total_bs = round(max((subtotal_usd * tasa_cobro) - descuento_bs, 0.0), 2)
    total_usd = round((total_bs / tasa_cobro) if tasa_cobro else 0.0, 2)

    return {
        "subtotal_usd": subtotal_usd,
        "tasa_cobro": tasa_cobro,
        "descuento_bs": descuento_bs,
        "total_usd": total_usd,
        "total_bs": total_bs,
    }


def obtener_tasa_actual(cursor):
    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()
    return float(row[0]) if row and row[0] else 1.0


def obtener_tasa_cobro(cursor):
    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise ValueError("Tasa de cobro no configurada")
    tasa = a_float(row[0])
    if tasa <= 0:
        raise ValueError("Tasa de cobro invalida")
    return tasa


MODOS_COBRO_VALIDOS = {"pagado", "parcial", "credito"}
TOLERANCIA_COBRO = 0.0001


def normalizar_modo_cobro(modo):
    modo = (modo or "pagado").strip().lower()
    return modo if modo in MODOS_COBRO_VALIDOS else ""


def obtener_cliente_para_cxc(cursor, cliente_id):
    try:
        cliente_id = int(cliente_id)
    except (TypeError, ValueError):
        raise ValueError("Debes seleccionar un cliente valido para la cuenta por cobrar")

    cursor.execute(
        """
        SELECT id, nombre
        FROM clientes
        WHERE id=? AND COALESCE(activo, 1)=1
        """,
        (cliente_id,),
    )
    cliente = cursor.fetchone()
    if not cliente:
        raise ValueError("Debes seleccionar un cliente valido para la cuenta por cobrar")
    return cliente


def listar_clientes_activos(cursor, busqueda=""):
    busqueda = (busqueda or "").strip().lower()
    params = []
    filtro = ""
    if busqueda:
        filtro = """
          AND (
              LOWER(nombre) LIKE ?
              OR LOWER(COALESCE(telefono, '')) LIKE ?
              OR LOWER(COALESCE(documento, '')) LIKE ?
          )
        """
        patron = f"%{busqueda}%"
        params = [patron, patron, patron]

    cursor.execute(
        f"""
        SELECT id, nombre, telefono, documento
        FROM clientes
        WHERE COALESCE(activo, 1)=1
        {filtro}
        ORDER BY LOWER(nombre), id
        LIMIT 100
        """,
        params,
    )
    return cursor.fetchall()


def cliente_json_desde_fila(cliente):
    return {
        "id": cliente[0],
        "nombre": cliente[1] or "",
        "telefono": cliente[2] or "",
        "documento": cliente[3] or "",
    }


def filtros_clientes_admin(busqueda, filtro):
    condiciones = []
    params = []
    busqueda = (busqueda or "").strip().lower()
    filtro = (filtro or "todos").strip().lower()

    if busqueda:
        condiciones.append(
            """
            (
                LOWER(c.nombre) LIKE ?
                OR LOWER(COALESCE(c.telefono, '')) LIKE ?
                OR LOWER(COALESCE(c.documento, '')) LIKE ?
            )
            """
        )
        patron = f"%{busqueda}%"
        params.extend([patron, patron, patron])

    if filtro == "activos":
        condiciones.append("COALESCE(c.activo, 1)=1")
    elif filtro == "inactivos":
        condiciones.append("COALESCE(c.activo, 1)=0")
    elif filtro == "con_saldo":
        condiciones.append(
            """
            EXISTS (
                SELECT 1 FROM cuentas_por_cobrar cxp
                WHERE cxp.cliente_id = c.id
                AND cxp.estado = 'pendiente'
                AND cxp.saldo_pendiente > 0
            )
            """
        )
    elif filtro == "sin_saldo":
        condiciones.append(
            """
            NOT EXISTS (
                SELECT 1 FROM cuentas_por_cobrar cxs
                WHERE cxs.cliente_id = c.id
                AND cxs.estado = 'pendiente'
                AND cxs.saldo_pendiente > 0
            )
            """
        )

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    return where, params


def listar_clientes_admin(cursor, busqueda="", filtro="todos"):
    where, params = filtros_clientes_admin(busqueda, filtro)
    cursor.execute(
        f"""
        SELECT
            c.id,
            c.nombre,
            COALESCE(c.telefono, ''),
            COALESCE(c.documento, ''),
            COALESCE(c.activo, 1),
            COALESCE(SUM(CASE
                WHEN cx.estado='pendiente' THEN cx.saldo_pendiente
                ELSE 0
            END), 0) AS saldo_pendiente_total,
            COALESCE(SUM(CASE
                WHEN cx.estado='pendiente' AND cx.saldo_pendiente > 0 THEN 1
                ELSE 0
            END), 0) AS cuentas_pendientes,
            COALESCE(SUM(CASE WHEN cx.estado='pagada' THEN 1 ELSE 0 END), 0) AS cuentas_pagadas
        FROM clientes c
        LEFT JOIN cuentas_por_cobrar cx ON cx.cliente_id = c.id
        {where}
        GROUP BY c.id, c.nombre, c.telefono, c.documento, c.activo
        ORDER BY COALESCE(c.activo, 1) DESC, LOWER(c.nombre), c.id
        LIMIT 300
        """,
        params,
    )
    return cursor.fetchall()


def obtener_cliente_admin(cursor, cliente_id):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(telefono, ''), COALESCE(documento, ''),
               COALESCE(notas, ''), COALESCE(activo, 1), fecha_creacion
        FROM clientes
        WHERE id=?
        """,
        (cliente_id,),
    )
    return cursor.fetchone()


def obtener_resumen_cliente(cursor, cliente_id):
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN estado='pendiente' THEN saldo_pendiente ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN estado='pendiente' AND saldo_pendiente > 0 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN estado='pagada' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(monto_original_deuda), 0)
        FROM cuentas_por_cobrar
        WHERE cliente_id=?
        """,
        (cliente_id,),
    )
    row = cursor.fetchone() or (0, 0, 0, 0)
    return {
        "saldo_pendiente": a_float(row[0]),
        "cuentas_pendientes": int(row[1] or 0),
        "cuentas_pagadas": int(row[2] or 0),
        "total_deuda_generada": a_float(row[3]),
    }


def listar_cuentas_cliente(cursor, cliente_id):
    cursor.execute(
        """
        SELECT cx.id, cx.orden_id, o.numero_orden, cx.fecha_generacion,
               cx.monto_original_deuda, cx.saldo_pendiente, cx.estado,
               cx.cliente_nombre_snapshot
        FROM cuentas_por_cobrar cx
        LEFT JOIN ordenes o ON o.id = cx.orden_id
        WHERE cx.cliente_id=?
        ORDER BY cx.fecha_generacion DESC, cx.id DESC
        """,
        (cliente_id,),
    )
    return cursor.fetchall()


def filtros_cxc_admin(busqueda, estado, cliente_id):
    condiciones = []
    params = []
    busqueda = (busqueda or "").strip().lower()
    estado = (estado or "pendiente").strip().lower()
    cliente_id = (str(cliente_id or "")).strip()

    if estado in ("pendiente", "pagada", "anulada"):
        condiciones.append("cx.estado=?")
        params.append(estado)

    if cliente_id:
        condiciones.append("cx.cliente_id=?")
        params.append(cliente_id)

    if busqueda:
        condiciones.append(
            """
            (
                LOWER(cx.cliente_nombre_snapshot) LIKE ?
                OR LOWER(COALESCE(c.nombre, '')) LIKE ?
                OR LOWER(COALESCE(c.telefono, '')) LIKE ?
                OR LOWER(COALESCE(c.documento, '')) LIKE ?
                OR LOWER(CAST(COALESCE(o.numero_orden, o.id) AS TEXT)) LIKE ?
            )
            """
        )
        patron = f"%{busqueda}%"
        params.extend([patron, patron, patron, patron, patron])

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    return where, params


def resumen_cuentas_por_cobrar(cursor):
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN estado='pendiente' THEN saldo_pendiente ELSE 0 END), 0),
            COUNT(DISTINCT CASE WHEN estado='pendiente' AND saldo_pendiente > 0 THEN cliente_id END),
            COALESCE(SUM(CASE WHEN estado='pendiente' AND saldo_pendiente > 0 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN estado='pagada' THEN 1 ELSE 0 END), 0)
        FROM cuentas_por_cobrar
        """
    )
    row = cursor.fetchone() or (0, 0, 0, 0)
    return {
        "saldo_total": a_float(row[0]),
        "clientes_con_deuda": int(row[1] or 0),
        "cuentas_pendientes": int(row[2] or 0),
        "cuentas_pagadas": int(row[3] or 0),
    }


def listar_cuentas_por_cobrar_admin(cursor, busqueda="", estado="pendiente", cliente_id=""):
    where, params = filtros_cxc_admin(busqueda, estado, cliente_id)
    cursor.execute(
        f"""
        SELECT
            cx.id,
            cx.cliente_id,
            cx.cliente_nombre_snapshot,
            COALESCE(c.nombre, ''),
            COALESCE(c.telefono, ''),
            COALESCE(c.documento, ''),
            cx.orden_id,
            o.numero_orden,
            cx.fecha_generacion,
            cx.monto_original_deuda,
            cx.saldo_pendiente,
            cx.estado
        FROM cuentas_por_cobrar cx
        LEFT JOIN clientes c ON c.id = cx.cliente_id
        LEFT JOIN ordenes o ON o.id = cx.orden_id
        {where}
        ORDER BY cx.fecha_generacion DESC, cx.id DESC
        LIMIT 300
        """,
        params,
    )
    return cursor.fetchall()


def calcular_suma_movimientos_cxc(cursor, cuenta_id):
    cursor.execute(
        """
        SELECT COALESCE(SUM(monto_saldo), 0)
        FROM cuentas_por_cobrar_movimientos
        WHERE cuenta_id=?
        """,
        (cuenta_id,),
    )
    row = cursor.fetchone()
    return round(a_float(row[0] if row else 0), 2)


def calcular_pagado_inicial_orden(cursor, orden_id, tasa_historica):
    cursor.execute(
        """
        SELECT metodo, monto
        FROM pagos
        WHERE orden_id=?
        ORDER BY id
        """,
        (orden_id,),
    )
    pagos = cursor.fetchall()
    total_usd = 0.0
    total_bs = 0.0
    for metodo, monto in pagos:
        pago_bs, pago_usd = convertir_pago_equivalente(metodo, monto, tasa_historica)
        total_bs += pago_bs
        total_usd += pago_usd
    return {
        "usd": round(total_usd, 2),
        "bs": round(total_bs, 2),
        "pagos": pagos,
    }


def obtener_detalle_cuenta_cxc(cursor, cuenta_id):
    cursor.execute(
        """
        SELECT
            cx.id, cx.orden_id, cx.cliente_id, cx.cliente_nombre_snapshot,
            cx.moneda_saldo, cx.monto_original_deuda, cx.saldo_pendiente,
            cx.fecha_generacion, cx.estado, COALESCE(cx.observacion, ''),
            COALESCE(c.nombre, ''), COALESCE(c.telefono, ''), COALESCE(c.documento, ''),
            o.numero_orden, o.fecha_venta, o.fecha_cobro, o.tasa_cobro,
            o.subtotal_usd, o.descuento_bs_snapshot, o.total_usd, o.total_bs
        FROM cuentas_por_cobrar cx
        LEFT JOIN clientes c ON c.id = cx.cliente_id
        LEFT JOIN ordenes o ON o.id = cx.orden_id
        WHERE cx.id=?
        """,
        (cuenta_id,),
    )
    cuenta = cursor.fetchone()
    if not cuenta:
        return None

    cursor.execute(
        """
        SELECT m.fecha, m.tipo, m.monto_saldo, m.moneda_pago, m.monto_pago,
               m.tasa_movimiento, m.metodo_pago, m.referencia,
               COALESCE(u.nombre, ''), COALESCE(m.observacion, '')
        FROM cuentas_por_cobrar_movimientos m
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE m.cuenta_id=?
        ORDER BY m.fecha ASC, m.id ASC
        """,
        (cuenta_id,),
    )
    movimientos = cursor.fetchall()
    suma_movimientos = calcular_suma_movimientos_cxc(cursor, cuenta_id)
    tasa_historica = a_float(cuenta[16])
    pagado_inicial = calcular_pagado_inicial_orden(cursor, cuenta[1], tasa_historica)
    inconsistente = abs(round(a_float(cuenta[6]) - suma_movimientos, 2)) > 0.01

    return {
        "cuenta": cuenta,
        "movimientos": movimientos,
        "suma_movimientos": suma_movimientos,
        "pagado_inicial": pagado_inicial,
        "inconsistente": inconsistente,
    }


def metodo_pago_es_usd(metodo):
    return normalizar_metodo_pago(metodo) == "usd"


def metodo_pago_es_bs(metodo):
    return normalizar_metodo_pago(metodo) in ("punto_venta", "bs_pago_movil", "bs_efectivo")


def moneda_pago_desde_metodo(metodo):
    metodo = normalizar_metodo_pago(metodo)
    if metodo_pago_es_usd(metodo):
        return "USD"
    if metodo_pago_es_bs(metodo):
        return "BS"
    return ""


def insertar_movimiento_abono_cxc(
    cursor,
    cuenta_id,
    monto_saldo,
    moneda_pago,
    monto_pago,
    tasa_movimiento,
    metodo_pago,
    referencia,
    fecha,
    usuario_id,
    observacion,
):
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar_movimientos (
            cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
            tasa_movimiento, metodo_pago, referencia, fecha,
            usuario_id, observacion, movimiento_revertido_id,
            referencia_externa_tipo, referencia_externa_id
        )
        VALUES (?, 'abono', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """,
        (
            cuenta_id,
            monto_saldo,
            moneda_pago,
            monto_pago,
            tasa_movimiento,
            metodo_pago,
            referencia,
            fecha,
            usuario_id,
            observacion,
        ),
    )


def actualizar_saldo_cxc(cursor, cuenta_id, nuevo_saldo, nuevo_estado):
    cursor.execute(
        """
        UPDATE cuentas_por_cobrar
        SET saldo_pendiente=?, estado=?
        WHERE id=?
        """,
        (nuevo_saldo, nuevo_estado, cuenta_id),
    )


def registrar_abono_cuenta(
    cursor,
    cuenta_id,
    metodo_pago,
    monto_recibido,
    referencia,
    observacion,
    usuario_id,
):
    cursor.execute(
        """
        SELECT id, saldo_pendiente, estado, moneda_saldo, cliente_nombre_snapshot
        FROM cuentas_por_cobrar
        WHERE id=?
        """,
        (cuenta_id,),
    )
    cuenta = cursor.fetchone()
    if not cuenta:
        raise ValueError("Cuenta por cobrar no encontrada")

    cuenta_id, saldo_actual, estado, moneda_saldo, cliente_nombre = cuenta
    saldo_actual = round(a_float(saldo_actual), 2)
    suma_movimientos = calcular_suma_movimientos_cxc(cursor, cuenta_id)

    if abs(round(saldo_actual - suma_movimientos, 2)) > 0.01:
        raise ValueError("La cuenta tiene una inconsistencia entre saldo y movimientos. No se puede registrar el abono.")
    if estado != "pendiente" or saldo_actual <= TOLERANCIA_COBRO:
        raise ValueError("Solo se pueden registrar abonos en cuentas pendientes con saldo.")
    if (moneda_saldo or "USD") != "USD":
        raise ValueError("La moneda de saldo de la cuenta no esta soportada para abonos.")

    metodo_pago = normalizar_metodo_pago(metodo_pago)
    if metodo_pago not in METODOS_PAGO_VALIDOS:
        raise ValueError("Metodo de pago invalido")

    monto_pago = a_float(monto_recibido)
    if monto_pago <= 0:
        raise ValueError("El monto del abono debe ser mayor a 0.")

    moneda_pago = moneda_pago_desde_metodo(metodo_pago)
    tasa_movimiento = None
    if moneda_pago == "USD":
        abono_usd = round(monto_pago, 2)
    elif moneda_pago == "BS":
        try:
            tasa_movimiento = obtener_tasa_cobro(cursor)
        except ValueError:
            raise ValueError("No hay una tasa de cambio valida para registrar el abono.")
        abono_usd = round(monto_pago / tasa_movimiento, 2)
    else:
        raise ValueError("Metodo de pago invalido")

    if abono_usd <= 0:
        raise ValueError("El monto del abono debe ser mayor a 0.")
    if abono_usd > saldo_actual + TOLERANCIA_COBRO:
        raise ValueError(f"El abono supera el saldo pendiente de {formato_usd(saldo_actual)}.")

    if abs(abono_usd - saldo_actual) <= TOLERANCIA_COBRO:
        abono_usd = saldo_actual

    nuevo_saldo = round(max(saldo_actual - abono_usd, 0.0), 2)
    nuevo_estado = "pagada" if nuevo_saldo <= TOLERANCIA_COBRO else "pendiente"
    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    observacion = (observacion or "").strip()
    referencia = (referencia or "").strip()

    insertar_movimiento_abono_cxc(
        cursor,
        cuenta_id,
        -abono_usd,
        moneda_pago,
        round(monto_pago, 2),
        tasa_movimiento,
        metodo_pago,
        referencia,
        fecha,
        usuario_id,
        observacion,
    )
    actualizar_saldo_cxc(cursor, cuenta_id, nuevo_saldo, nuevo_estado)

    return {
        "cuenta_id": cuenta_id,
        "cliente": cliente_nombre,
        "saldo_anterior": saldo_actual,
        "abono_usd": abono_usd,
        "nuevo_saldo": nuevo_saldo,
        "estado": nuevo_estado,
        "moneda_pago": moneda_pago,
        "monto_pago": round(monto_pago, 2),
        "tasa_movimiento": tasa_movimiento,
        "fecha": fecha,
    }


def obtener_cuenta_cxc_por_orden(cursor, orden_id):
    cursor.execute("SELECT id FROM cuentas_por_cobrar WHERE orden_id=?", (orden_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def validar_recobro_cxc(cursor, orden_id):
    cuenta_id = obtener_cuenta_cxc_por_orden(cursor, orden_id)
    if cuenta_id is None:
        return None

    raise ValueError(
        "Esta orden tiene una cuenta por cobrar asociada y no puede recobrarse directamente. "
        "Debe utilizarse un proceso administrativo de reversion."
    )


def insertar_movimiento_cxc_inicial(cursor, cuenta_id, saldo_usd, fecha, usuario_id):
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar_movimientos (
            cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
            tasa_movimiento, metodo_pago, referencia, fecha,
            usuario_id, observacion, movimiento_revertido_id,
            referencia_externa_tipo, referencia_externa_id
        )
        VALUES (?, 'cargo', ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL)
        """,
        (
            cuenta_id,
            saldo_usd,
            fecha,
            usuario_id,
            "Cargo inicial generado al cobrar la orden",
        ),
    )


def crear_cuenta_por_cobrar_inicial(
    cursor, orden_id, cliente_id, cliente_nombre, saldo_usd, fecha, usuario_id
):
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar (
            orden_id, cliente_id, cliente_nombre_snapshot, moneda_saldo,
            monto_original_deuda, saldo_pendiente, fecha_generacion,
            estado, usuario_id, observacion
        )
        VALUES (?, ?, ?, 'USD', ?, ?, ?, 'pendiente', ?, ?)
        """,
        (
            orden_id,
            cliente_id,
            cliente_nombre,
            saldo_usd,
            saldo_usd,
            fecha,
            usuario_id,
            "Cuenta por cobrar generada al cobrar la orden",
        ),
    )
    cuenta_id = obtener_ultimo_id(cursor, "cuentas_por_cobrar")
    insertar_movimiento_cxc_inicial(cursor, cuenta_id, saldo_usd, fecha, usuario_id)
    return cuenta_id


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


def limpiar_facturas_archivadas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET facturar=0 WHERE cierre_id IS NOT NULL")
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


def crear_tablas_cuentas_por_cobrar():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS clientes (
            id {pk_autoincrement_sql()},
            nombre TEXT NOT NULL,
            telefono TEXT,
            documento TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
            id {pk_autoincrement_sql()},
            orden_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            cliente_nombre_snapshot TEXT NOT NULL,
            moneda_saldo TEXT NOT NULL DEFAULT 'USD',
            monto_original_deuda REAL NOT NULL DEFAULT 0 CHECK (monto_original_deuda >= 0),
            saldo_pendiente REAL NOT NULL DEFAULT 0 CHECK (saldo_pendiente >= 0),
            fecha_generacion TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (estado IN ('pendiente', 'pagada', 'anulada')),
            usuario_id INTEGER,
            observacion TEXT,
            UNIQUE (orden_id)
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cuentas_por_cobrar_movimientos (
            id {pk_autoincrement_sql()},
            cuenta_id INTEGER NOT NULL,
            tipo TEXT NOT NULL
                CHECK (tipo IN ('cargo', 'abono', 'ajuste', 'reverso', 'compensacion')),
            -- Delta firmado del saldo de deuda, expresado en moneda_saldo de la cuenta.
            monto_saldo REAL NOT NULL DEFAULT 0,
            moneda_pago TEXT,
            monto_pago REAL,
            tasa_movimiento REAL,
            metodo_pago TEXT,
            referencia TEXT,
            fecha TEXT,
            usuario_id INTEGER,
            observacion TEXT,
            movimiento_revertido_id INTEGER,
            referencia_externa_tipo TEXT,
            referencia_externa_id INTEGER
        )
        """
    )

    conn.commit()
    conn.close()

    asegurar_columna("ordenes", "cliente_id", "INTEGER")
    asegurar_columna("ordenes", "fecha_venta", "TEXT")
    asegurar_columna("cuentas_por_cobrar_movimientos", "movimiento_revertido_id", "INTEGER")


def crear_tablas_delivery():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS repartidores (
            id {pk_autoincrement_sql()},
            nombre TEXT NOT NULL,
            telefono TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS delivery_movimientos (
            id {pk_autoincrement_sql()},
            orden_id INTEGER,
            repartidor_id INTEGER NOT NULL,
            tipo TEXT NOT NULL
                CHECK (tipo IN ('cargo', 'pago', 'ajuste', 'anulacion')),
            monto_usd REAL NOT NULL,
            fecha TEXT,
            usuario_id INTEGER,
            referencia TEXT,
            observacion TEXT,
            movimiento_revertido_id INTEGER
        )
        """
    )

    conn.commit()
    conn.close()

    asegurar_columna("ordenes", "venta_restaurante_usd", "REAL")
    asegurar_columna("ordenes", "delivery_usd", "REAL")
    asegurar_columna("ordenes", "total_cliente_usd", "REAL")
    asegurar_columna("ordenes", "delivery_repartidor_id", "INTEGER")


def listar_repartidores(cursor, solo_activos=False):
    where = "WHERE COALESCE(activo, 1)=1" if solo_activos else ""
    cursor.execute(
        f"""
        SELECT id, nombre, COALESCE(telefono, ''), COALESCE(notas, ''),
               COALESCE(activo, 1), fecha_creacion
        FROM repartidores
        {where}
        ORDER BY COALESCE(activo, 1) DESC, LOWER(nombre), id
        """
    )
    return cursor.fetchall()


def obtener_repartidor(cursor, repartidor_id):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(telefono, ''), COALESCE(notas, ''),
               COALESCE(activo, 1), fecha_creacion
        FROM repartidores
        WHERE id=?
        """,
        (repartidor_id,),
    )
    return cursor.fetchone()


def normalizar_nombre_repartidor(nombre):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del repartidor es obligatorio.")
    return nombre[:120]


def crear_repartidor(cursor, nombre, telefono="", notas="", activo=1):
    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO repartidores (nombre, telefono, notas, activo, fecha_creacion)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            normalizar_nombre_repartidor(nombre),
            (telefono or "").strip()[:80],
            (notas or "").strip()[:500],
            1 if int(a_float(activo, 1)) == 1 else 0,
            fecha,
        ),
    )
    return obtener_ultimo_id(cursor, "repartidores")


def orden_tiene_cxc(cursor, orden_id):
    cursor.execute("SELECT 1 FROM cuentas_por_cobrar WHERE orden_id=? LIMIT 1", (orden_id,))
    return cursor.fetchone() is not None


def orden_tiene_delivery_legacy(cursor, orden_id):
    cursor.execute(
        """
        SELECT oi.producto, c.nombre
        FROM orden_items oi
        LEFT JOIN productos p ON LOWER(p.nombre)=LOWER(oi.producto)
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE oi.orden_id=?
        """,
        (orden_id,),
    )
    return any(es_producto_delivery_legacy(producto, categoria) for producto, categoria in cursor.fetchall())


def validar_orden_delivery_modificable(cursor, orden_id):
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
        raise ValueError("Orden no encontrada")
    estado, cierre_id = orden_row
    if cierre_id is not None:
        raise ValueError("No puedes modificar delivery en una orden archivada en cierre de jornada.")
    if estado == "cerrada":
        raise ValueError("No puedes modificar delivery en una orden cerrada.")
    if orden_tiene_cxc(cursor, orden_id):
        raise ValueError("No puedes modificar delivery en una orden con cuenta por cobrar asociada.")
    return estado


def actualizar_delivery_orden(cursor, orden_id, monto_delivery, repartidor_id):
    validar_orden_delivery_modificable(cursor, orden_id)
    monto = normalizar_monto_delivery(monto_delivery)

    repartidor_id_final = None
    if monto > 0:
        if orden_tiene_delivery_legacy(cursor, orden_id):
            raise ValueError("Esta orden contiene un delivery agregado con el sistema anterior. No se puede agregar delivery explicito.")
        repartidor_id_texto = (str(repartidor_id or "")).strip()
        if repartidor_id_texto:
            repartidor_id_final = int(a_float(repartidor_id_texto))
            repartidor = obtener_repartidor(cursor, repartidor_id_final)
            if not repartidor or int(repartidor[4] or 0) != 1:
                raise ValueError("Debes seleccionar un repartidor activo para guardar delivery.")

    cursor.execute(
        """
        UPDATE ordenes
        SET delivery_usd=?, delivery_repartidor_id=?
        WHERE id=?
        """,
        (monto, repartidor_id_final, orden_id),
    )
    return {"delivery_usd": monto, "delivery_repartidor_id": repartidor_id_final}


def orden_tiene_movimientos_delivery(cursor, orden_id):
    cursor.execute("SELECT 1 FROM delivery_movimientos WHERE orden_id=? LIMIT 1", (orden_id,))
    return cursor.fetchone() is not None


def validar_recobro_delivery(cursor, orden_id):
    if orden_tiene_movimientos_delivery(cursor, orden_id):
        raise ValueError(
            "Esta orden tiene movimientos de delivery asociados y no puede recobrarse directamente. "
            "Debe utilizarse un proceso administrativo de reversion."
        )


def validar_repartidor_delivery_cobro(cursor, delivery_usd, repartidor_id):
    if a_float(delivery_usd) <= TOLERANCIA_COBRO:
        return None
    try:
        repartidor_id_int = int(a_float(repartidor_id))
    except Exception:
        repartidor_id_int = 0
    if repartidor_id_int <= 0:
        raise ValueError("Debes asignar un repartidor antes de cobrar esta orden.")
    repartidor = obtener_repartidor(cursor, repartidor_id_int)
    if not repartidor or int(repartidor[4] or 0) != 1:
        raise ValueError("Selecciona un repartidor activo para el delivery.")
    return repartidor_id_int


def insertar_cargo_delivery(cursor, orden_id, repartidor_id, monto_usd, fecha, usuario_id):
    monto_usd = round(a_float(monto_usd), 2)
    if monto_usd <= TOLERANCIA_COBRO:
        return None
    if orden_tiene_movimientos_delivery(cursor, orden_id):
        raise ValueError("Esta orden ya tiene movimientos de delivery asociados.")
    cursor.execute(
        """
        INSERT INTO delivery_movimientos (
            orden_id, repartidor_id, tipo, monto_usd, fecha,
            usuario_id, referencia, observacion, movimiento_revertido_id
        )
        VALUES (?, ?, 'cargo', ?, ?, ?, ?, ?, NULL)
        """,
        (
            orden_id,
            repartidor_id,
            monto_usd,
            fecha,
            usuario_id,
            f"orden:{orden_id}",
            "Cargo delivery generado al cerrar la orden",
        ),
    )
    return obtener_ultimo_id(cursor, "delivery_movimientos")


def resumen_delivery_admin(cursor):
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo='cargo' THEN monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo='pago' THEN ABS(monto_usd) ELSE 0 END), 0),
            COALESCE(SUM(monto_usd), 0),
            COALESCE(SUM(CASE WHEN tipo='cargo' AND orden_id IS NOT NULL THEN 1 ELSE 0 END), 0)
        FROM delivery_movimientos
        """
    )
    generado, pagado, pendiente, servicios = cursor.fetchone()
    return {
        "generado": a_float(generado),
        "pagado": a_float(pagado),
        "pendiente": a_float(pendiente),
        "servicios": int(servicios or 0),
    }


def resumen_delivery_por_repartidor(cursor):
    cursor.execute(
        """
        SELECT
            r.id,
            r.nombre,
            COALESCE(r.activo, 1),
            COALESCE(SUM(CASE WHEN dm.tipo='cargo' AND dm.orden_id IS NOT NULL THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dm.tipo='cargo' THEN dm.monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dm.tipo='pago' THEN ABS(dm.monto_usd) ELSE 0 END), 0),
            COALESCE(SUM(dm.monto_usd), 0)
        FROM repartidores r
        LEFT JOIN delivery_movimientos dm ON dm.repartidor_id = r.id
        GROUP BY r.id, r.nombre, r.activo
        ORDER BY COALESCE(SUM(dm.monto_usd), 0) DESC, LOWER(r.nombre), r.id
        """
    )
    return cursor.fetchall()


def detalle_delivery_repartidor(cursor, repartidor_id):
    repartidor = obtener_repartidor(cursor, repartidor_id)
    if not repartidor:
        return None

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo='cargo' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo='cargo' THEN monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo='pago' THEN ABS(monto_usd) ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo IN ('ajuste', 'anulacion') THEN monto_usd ELSE 0 END), 0),
            COALESCE(SUM(monto_usd), 0)
        FROM delivery_movimientos
        WHERE repartidor_id=?
        """,
        (repartidor_id,),
    )
    servicios, generado, pagado, ajustes_netos, pendiente = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            dm.fecha,
            dm.tipo,
            dm.orden_id,
            o.id,
            o.numero_orden,
            dm.monto_usd,
            dm.referencia,
            u.nombre,
            dm.observacion
        FROM delivery_movimientos dm
        LEFT JOIN ordenes o ON o.id = dm.orden_id
        LEFT JOIN usuarios u ON u.id = dm.usuario_id
        WHERE dm.repartidor_id=?
        ORDER BY dm.fecha DESC, dm.id DESC
        """,
        (repartidor_id,),
    )
    movimientos = cursor.fetchall()

    return {
        "repartidor": repartidor,
        "resumen": {
            "servicios": int(servicios or 0),
            "generado": a_float(generado),
            "pagado": a_float(pagado),
            "ajustes_netos": a_float(ajustes_netos),
            "pendiente": a_float(pendiente),
        },
        "movimientos": movimientos,
    }


def registrar_pago_delivery_repartidor(cursor, repartidor_id, monto_usd, referencia, observacion, usuario_id):
    repartidor = obtener_repartidor(cursor, repartidor_id)
    if not repartidor:
        raise ValueError("Repartidor no encontrado")

    monto = round(a_float(monto_usd), 2)
    if monto <= TOLERANCIA_COBRO:
        raise ValueError("El monto del pago debe ser mayor a 0.")

    detalle = detalle_delivery_repartidor(cursor, repartidor_id)
    saldo_actual = round(a_float(detalle["resumen"]["pendiente"] if detalle else 0), 2)
    if saldo_actual <= TOLERANCIA_COBRO:
        raise ValueError("Este repartidor no tiene saldo pendiente.")
    if monto > saldo_actual + TOLERANCIA_COBRO:
        raise ValueError("El pago no puede superar el saldo pendiente.")

    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO delivery_movimientos (
            orden_id, repartidor_id, tipo, monto_usd, fecha,
            usuario_id, referencia, observacion, movimiento_revertido_id
        )
        VALUES (NULL, ?, 'pago', ?, ?, ?, ?, ?, NULL)
        """,
        (
            repartidor_id,
            -monto,
            fecha,
            usuario_id,
            (referencia or "").strip()[:120],
            (observacion or "").strip()[:500],
        ),
    )
    return obtener_ultimo_id(cursor, "delivery_movimientos")


def crear_usuarios_iniciales():
    asegurar_columna("usuarios", "activo", "INTEGER DEFAULT 1")

    USUARIOS_NEKO_WOK = [
        ("Emmanuel", "0000", "master"),
        ("Ismaldo", "0000", "master"),
        ("Jonayker", "0000", "produccion"),
        ("Juan Luis", "0000", "produccion"),
    ]

    conn = get_connection()
    cursor = conn.cursor()

    for nombre, pin, rol in USUARIOS_NEKO_WOK:
        cursor.execute(
            "SELECT id FROM usuarios WHERE lower(trim(nombre))=lower(?) ORDER BY id LIMIT 1",
            (nombre,),
        )
        existe = cursor.fetchone()
        if existe:
            cursor.execute(
                "UPDATE usuarios SET nombre=?, pin=?, rol=?, activo=1 WHERE id=?",
                (nombre, pin, rol, existe[0]),
            )
        else:
            cursor.execute(
                "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)",
                (nombre, pin, rol),
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

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS recetas (
            id {pk_autoincrement_sql()},
            producto_menu TEXT,
            insumo TEXT,
            cantidad REAL,
            unidad TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS movimientos_inventario (
            id {pk_autoincrement_sql()},
            producto TEXT,
            tipo TEXT,
            cantidad REAL,
            stock_anterior REAL,
            stock_nuevo REAL,
            costo_promedio REAL,
            referencia TEXT,
            usuario TEXT,
            fecha TEXT,
            observacion TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def usuario_activo():
    return session.get("usuario_nombre", "")


def usuario_rol():
    if hasattr(g, "usuario_rol_actual"):
        return g.usuario_rol_actual

    usuario_id = session.get("usuario_id")
    if usuario_id:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT nombre, COALESCE(rol, 'mesonera')
                FROM usuarios
                WHERE id=?
                """,
                (usuario_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                rol_db = row[1] if row[1] in ROLES_USUARIO_VALIDOS else "mesonera"
                session["usuario_nombre"] = row[0]
                session["usuario"] = row[0]
                session["usuario_rol"] = rol_db
                g.usuario_rol_actual = rol_db
                return rol_db
        except Exception:
            pass

    rol = session.get("usuario_rol", "")
    if rol in ROLES_USUARIO_VALIDOS:
        g.usuario_rol_actual = rol
        return rol

    roles_por_nombre = {
        "Josue":    "master",
        "Emmanuel": "master",
        "Monica":   "mesonera_reportes",
        "Gaby":     "mesonera_reportes",
        "Jessica":  "cocina_reportes",
        "Ismaldo":  "master",
        "Jonayker": "produccion",
        "Juan Luis": "produccion",
    }
    rol = roles_por_nombre.get(session.get("usuario") or session.get("usuario_nombre"), "mesonera")
    session["usuario_rol"] = rol
    g.usuario_rol_actual = rol
    return rol


def usuario_es_master():
    return usuario_rol() == "master"


def usuario_es_mesonera():
    return usuario_rol() == "mesonera"


def usuario_es_cocina():
    return usuario_rol() == "cocina"


def usuario_es_socio():
    return usuario_rol() == "socio"


def usuario_es_produccion():
    return usuario_rol() == "produccion"


def usuario_puede_tomar_ordenes():
    return usuario_rol() in ("master", "mesonera", "socio", "mesonera_reportes")


def usuario_puede_ver_inventario():
    return usuario_rol() in ("master", "cocina", "cocina_reportes")


def usuario_puede_editar_inventario():
    return usuario_rol() == "master"


def usuario_puede_produccion():
    return usuario_rol() in ("master", "cocina", "cocina_reportes", "produccion")


def usuario_puede_ver_cocina():
    return usuario_rol() in ("master", "cocina", "cocina_reportes")


def usuario_puede_reportes():
    return usuario_rol() in ("master", "socio", "mesonera_reportes", "cocina_reportes")


def usuario_puede_admin_total():
    return usuario_rol() == "master"


def usuario_es_admin_cierre():
    return usuario_es_master()


def usuario_puede_reimprimir_cocina():
    return usuario_es_master()


def obtener_emergencias_activas():
    activas = session.get("emergencias_activas", [])
    return [str(item) for item in activas]


def emergencia_activa(orden_id):
    return usuario_es_admin_cierre() and str(orden_id) in obtener_emergencias_activas()


def activar_emergencia_sesion(orden_id):
    activas = obtener_emergencias_activas()
    orden_txt = str(orden_id)
    if orden_txt not in activas:
        activas.append(orden_txt)
    session["emergencias_activas"] = activas
    session.modified = True


def desactivar_emergencia_sesion(orden_id):
    orden_txt = str(orden_id)
    activas = [item for item in obtener_emergencias_activas() if item != orden_txt]
    session["emergencias_activas"] = activas
    session.modified = True


def registrar_auditoria_emergencia(cursor, orden_id, accion, observacion=""):
    usuario = usuario_activo() or session.get("usuario", "")
    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO auditoria_emergencias (orden_id, usuario, fecha, accion, observacion)
        VALUES (?, ?, ?, ?, ?)
        """,
        (orden_id, usuario, fecha, accion, observacion or ""),
    )


def registrar_movimiento_inventario(
    cursor,
    producto,
    tipo,
    cantidad,
    stock_anterior,
    stock_nuevo,
    costo_promedio,
    referencia,
    observacion="",
):
    usuario = usuario_activo() or session.get("usuario", "")
    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO movimientos_inventario (
            producto, tipo, cantidad, stock_anterior, stock_nuevo,
            costo_promedio, referencia, usuario, fecha, observacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            producto,
            tipo,
            a_float(cantidad),
            a_float(stock_anterior),
            a_float(stock_nuevo),
            a_float(costo_promedio),
            referencia or "",
            usuario or "",
            fecha,
            observacion or "",
        ),
    )


def descontar_inventario_por_orden(cursor, orden_id):
    cursor.execute(
        """
        SELECT inventario_descontado, numero_orden
        FROM ordenes
        WHERE id=?
        """,
        (orden_id,),
    )
    orden = cursor.fetchone()
    if not orden:
        return

    if int(orden[0] or 0) == 1:
        print(f"Inventario ya descontado para orden {orden_id}")
        return

    numero_orden = orden[1] if orden[1] is not None else orden_id
    referencia = f"orden:{numero_orden}"

    cursor.execute(
        """
        SELECT producto
        FROM orden_items
        WHERE orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()

    for item in items:
        cantidad_vendida, producto_limpio = separar_prefijo_cantidad(item[0])
        producto_limpio = producto_limpio.strip()

        cursor.execute(
            """
            SELECT insumo, cantidad, unidad
            FROM recetas
            WHERE lower(producto_menu)=lower(?)
            """,
            (producto_limpio,),
        )
        receta = cursor.fetchall()

        if not receta:
            print(f"WARNING inventario: producto sin receta: {producto_limpio}")
            continue

        for insumo, cantidad_receta, unidad in receta:
            cantidad_a_descontar = cantidad_vendida * a_float(cantidad_receta)

            cursor.execute(
                """
                SELECT id, stock_actual, costo_promedio
                FROM inventario
                WHERE lower(nombre)=lower(?)
                LIMIT 1
                """,
                (insumo,),
            )
            inventario_item = cursor.fetchone()

            if inventario_item:
                inventario_id = inventario_item[0]
                stock_anterior = a_float(inventario_item[1])
                costo_promedio = a_float(inventario_item[2])
            else:
                inventario_id = None
                stock_anterior = 0.0
                costo_promedio = 0.0
                print(f"WARNING inventario: insumo no existe en inventario: {insumo}")

            stock_nuevo = stock_anterior - cantidad_a_descontar

            if inventario_id is None:
                cursor.execute(
                    """
                    INSERT INTO inventario (nombre, stock_actual, unidad, costo_promedio)
                    VALUES (?, ?, ?, ?)
                    """,
                    (insumo, stock_nuevo, unidad or "", costo_promedio),
                )
            else:
                cursor.execute(
                    """
                    UPDATE inventario
                    SET stock_actual=?
                    WHERE id=?
                    """,
                    (stock_nuevo, inventario_id),
                )

            registrar_movimiento_inventario(
                cursor,
                insumo,
                "venta",
                -cantidad_a_descontar,
                stock_anterior,
                stock_nuevo,
                costo_promedio,
                referencia,
                f"{cantidad_vendida}x {producto_limpio}",
            )

    cursor.execute(
        """
        UPDATE ordenes
        SET inventario_descontado=1
        WHERE id=?
        """,
        (orden_id,),
    )


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


def calcular_costo_promedio_ponderado(stock_anterior, costo_anterior, cantidad, costo_nuevo):
    stock_anterior = a_float(stock_anterior)
    costo_anterior = a_float(costo_anterior)
    cantidad = a_float(cantidad)
    costo_nuevo = a_float(costo_nuevo)
    nuevo_stock = stock_anterior + cantidad

    if nuevo_stock <= 0:
        return costo_anterior

    return ((stock_anterior * costo_anterior) + costo_nuevo) / nuevo_stock


def sumar_inventario_con_costo(cursor, producto, cantidad, unidad, costo_total):
    producto = (producto or "").strip()
    unidad = (unidad or "unidad").strip() or "unidad"
    cantidad = a_float(cantidad)
    costo_total = a_float(costo_total)

    if not producto or cantidad <= 0:
        return

    cursor.execute(
        """
        SELECT id, stock_actual, costo_promedio
        FROM inventario
        WHERE lower(nombre) = lower(?)
        LIMIT 1
        """,
        (producto,),
    )
    item = cursor.fetchone()

    if item:
        stock_anterior = a_float(item[1])
        costo_anterior = a_float(item[2])
        nuevo_stock = stock_anterior + cantidad
        nuevo_costo = calcular_costo_promedio_ponderado(
            stock_anterior,
            costo_anterior,
            cantidad,
            costo_total,
        )
        cursor.execute(
            """
            UPDATE inventario
            SET stock_actual=?, unidad=?, costo_promedio=?
            WHERE id=?
            """,
            (nuevo_stock, unidad, nuevo_costo, item[0]),
        )
    else:
        costo_promedio = (costo_total / cantidad) if cantidad else 0.0
        cursor.execute(
            """
            INSERT INTO inventario (nombre, stock_actual, unidad, costo_promedio)
            VALUES (?, ?, ?, ?)
            """,
            (producto, cantidad, unidad, costo_promedio),
        )


def parsear_porciones_detalle(texto):
    total = 0.0
    lineas_validas = []

    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue

        numeros = re.findall(r"\d+(?:[.,]\d+)?", limpia)
        if len(numeros) >= 2:
            cantidad = a_float(numeros[0])
            tamano = a_float(numeros[1])
            total += cantidad * tamano
            lineas_validas.append(limpia)

    return total, "\n".join(lineas_validas)


def parsear_insumos_extra(texto):
    total = 0.0
    lineas_validas = []

    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue

        numeros = re.findall(r"\d+(?:[.,]\d+)?", limpia)
        costo = a_float(numeros[-1]) if numeros else 0.0
        total += costo
        lineas_validas.append(limpia)

    return total, "\n".join(lineas_validas)


def estilos_base():
    return """
    :root {
        --fondo-principal: #0F1115;
        --panel: #181B20;
        --panel-secundario: #20242B;
        --tarjeta: #20242B;
        --verde-neko: #3DDC84;
        --verde-oscuro: #2AC96F;
        --hover-neko: #2AC96F;
        --naranja: #F59E0B;
        --dorado: #f59e0b;
        --crema: #fef3c7;
        --verde: #3DDC84;
        --azul: #2563EB;
        --rojo: #DC2626;
        --carbon: #F4F4F4;
        --gris-fondo: #0F1115;
        --texto: #F4F4F4;
        --texto-secundario: #B0B6BE;
        --borde: #31363F;
        --sombra: 0 10px 24px rgba(0, 0, 0, 0.22);
        --sombra-suave: 0 1px 2px rgba(0, 0, 0, 0.20), 0 8px 20px rgba(0, 0, 0, 0.14);
    }
    * { box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
        color: var(--texto);
        background:
            radial-gradient(circle at top right, rgba(61, 220, 132, 0.035), transparent 28rem),
            linear-gradient(180deg, var(--fondo-principal) 0%, #11141A 100%);
        min-height: 100vh;
    }
    .header {
        background: rgba(24, 27, 32, 0.96);
        color: var(--texto);
        padding: 14px 22px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        border-bottom: 1px solid var(--borde);
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.20);
        position: sticky;
        top: 0;
        z-index: 20;
    }
    .titulo {
        font-size: 24px;
        font-weight: 900;
        letter-spacing: 0;
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--verde-neko);
        text-shadow: 0 0 10px rgba(61, 220, 132, 0.14);
    }
    .titulo span.brand-dot { color: var(--verde-neko); }
    .menu-top { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
    .menu-top a, .volver, .btn-accion, .btn-ver, .btn-cobrar, .btn-acceso {
        color: white;
        text-decoration: none;
        font-weight: 700;
        border-radius: 8px;
        min-height: 40px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.22);
    }
    .menu-top a { background: var(--panel-secundario); border: 1px solid var(--borde); padding: 8px 12px; font-size: 13px; transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease; }
    .menu-top a:hover { background: #262B33; border-color: #3C4350; color: var(--texto); }
    .contenido, .contenedor { max-width: 1280px; margin: 0 auto; }
    .card, .panel-izq, .panel-der, .panel, .login-box {
        background: var(--panel);
        color: var(--texto);
        border: 1px solid var(--borde);
        box-shadow: var(--sombra-suave);
    }
    h1, h2, h3 { letter-spacing: -0.3px; color: var(--carbon); }
    input, select, textarea {
        border: 1px solid var(--borde);
        min-height: 46px;
        background: var(--panel-secundario);
        color: var(--texto);
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 15px;
    }
    input::placeholder, textarea::placeholder { color: #7F8791; }
    input:focus, select:focus, textarea:focus {
        outline: none;
        border-color: var(--verde-neko);
        box-shadow: 0 0 0 3px rgba(61, 220, 132, 0.12);
    }
    button, .btn, .btn-agregar, .btn-guardar {
        font-weight: 800;
        min-height: 48px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.22);
        border-radius: 10px;
        cursor: pointer;
        transition: background 0.18s ease, border-color 0.18s ease, transform 0.1s, box-shadow 0.18s ease;
    }
    button:hover, .btn:hover, .btn-agregar:hover, .btn-guardar:hover { box-shadow: 0 8px 18px rgba(0, 0, 0, 0.20); }
    button:active, .btn:active { transform: scale(0.97); }
    table { color: var(--texto); }
    th { background: var(--panel-secundario); color: var(--verde-neko); border-bottom: 1px solid var(--borde); }
    td { border-bottom: 1px solid var(--borde); }
    tbody tr:nth-child(even) { background: rgba(255, 255, 255, 0.025); }
    tbody tr:hover { background: rgba(255, 255, 255, 0.055); }
    @media (min-width: 900px) {
        .contenedor { flex-direction: row !important; align-items: flex-start; padding: 18px !important; }
        .panel-izq { flex: 0 0 360px; }
        .panel-der { flex: 1; }
        .card { flex-direction: row !important; justify-content: space-between; align-items: center; }
    }
    @media (max-width: 768px) {
        .header { position: static; flex-direction: column; align-items: stretch; }
        .titulo { font-size: 21px; }
        .menu-top { justify-content: stretch; }
        .menu-top a { flex: 1 1 42%; }
    }
    """


def barra_superior(extra_links=""):
    return f"""
    <style>{estilos_base()}</style>
    <div class="header">
        <div class="titulo">🐱 Neko Wok <span class="brand-dot">·</span> <span style="font-size:14px;font-weight:500;opacity:0.85;">POS</span></div>
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
            <div style="font-size:13px; opacity:0.85;">👤 <b>{usuario_activo()}</b></div>
            <div class="menu-top">
                {extra_links}
                <a href="/logout">🚪 Salir</a>
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

    total_punto_venta_bs = 0.0
    total_pago_movil_bs = 0.0
    total_efectivo_bs = 0.0
    total_efectivo_usd = 0.0
    auditoria_pagos = []

    for orden_id, numero_orden, cliente, metodo, monto, referencia, fecha in filas_pagos:
        metodo = normalizar_metodo_pago(metodo)
        monto = a_float(monto)

        if metodo == "punto_venta":
            total_punto_venta_bs += monto
        elif metodo == "bs_pago_movil":
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
        total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs + (total_efectivo_usd * tasa)
    )
    total_cobrado_equiv_usd = total_efectivo_usd + (
        ((total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs) / tasa) if tasa else 0.0
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
        "total_punto_venta_bs": round(total_punto_venta_bs, 2),
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
    total_punto_venta_bs = 0.0
    total_pago_movil_bs = 0.0
    total_efectivo_bs = 0.0
    total_efectivo_usd = 0.0

    for orden_id, numero_orden, fecha_hora, cliente, metodo, monto, referencia, fecha_pago in pagos_db:
        metodo = normalizar_metodo_pago(metodo)
        monto = a_float(monto)
        equiv_bs, equiv_usd = convertir_pago_equivalente(metodo, monto, tasa)

        if metodo == "punto_venta":
            total_punto_venta_bs += monto
        elif metodo == "bs_pago_movil":
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

    total_equiv_bs = total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs + (total_efectivo_usd * tasa)
    total_equiv_usd = total_efectivo_usd + (
        ((total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs) / tasa) if tasa else 0.0
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
        "total_punto_venta_bs": round(total_punto_venta_bs, 2),
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
    # Endpoints publicos para login y scripts locales/API.
    rutas_publicas = {
        "login",
        "static",
        "ordenes_cocina",
        "facturas_pendientes",
        "desactivar_factura",
        "api_tasa",
    }

    # Administracion total y operaciones destructivas.
    solo_master = {
        "cierre",
        "cerrar_jornada",
        "cerrar_dia",
        "exportar",
        "exportar_reporte",
        "revertir_orden_cierre",
        "eliminar_orden",
        "recetas",
        "eliminar_receta",
        "movimientos_inventario",
        "compras",
        "proveedores",
        "productos_base",
        "menu",
        "agregar_producto",
        "eliminar_producto",
        "editar_producto",
        "reimprimir_cocina",
        "cambiar_tasa",
        "usuarios",
        "crear_usuario",
        "editar_usuario",
        "activar_usuario",
        "clientes",
        "crear_cliente",
        "detalle_cliente",
        "editar_cliente",
        "activar_cliente",
        "cuentas_por_cobrar_admin",
        "detalle_cuenta_por_cobrar",
        "registrar_abono_cxc",
        "delivery_admin",
        "delivery_repartidor_detalle",
        "registrar_pago_delivery",
        "repartidores",
        "nuevo_repartidor",
        "editar_repartidor",
        "activar_repartidor",
        "activar_edicion_emergencia",
        "ordenes_listas",
        "reset_neko",
    }

    # Lectura gerencial sin acciones destructivas para socios.
    master_socio = {"reportes", "dashboard"}

    # Operacion de inventario/produccion para master y cocina.
    master_cocina = {"inventario", "produccion"}

    # Flujo de venta y atencion de ordenes.
    toma_ordenes = {
        "index",
        "crear_orden",
        "nueva_orden",
        "orden",
        "agregar",
        "enviar_cocina",
        "activar_factura",
        "reimprimir_factura",
        "factura",
        "cobrar",
        "api_clientes",
        "api_repartidores",
        "editar_orden",
        "actualizar_delivery",
        "actualizar_indicacion_item",
        "eliminar_item",
    }

    # Pantalla operativa de cocina.
    acceso_cocina = {"cocina", "pantalla_cocina", "marcar_listo"}

    if request.endpoint in {"login", "static"}:
        return

    if not session.get("usuario_id"):
        if request.endpoint in rutas_publicas:
            return
        return redirect("/login")

    if usuario_es_produccion() and request.endpoint not in {"produccion", "logout"}:
        print(
            f"[PERMISO BLOQUEADO] "
            f"endpoint={request.endpoint} "
            f"rol={usuario_rol()} "
            f"path={request.path}"
        )
        return redirect("/produccion")

    if request.endpoint in solo_master and not usuario_es_master():
        print(
            f"[PERMISO BLOQUEADO] "
            f"endpoint={request.endpoint} "
            f"rol={usuario_rol()} "
            f"path={request.path}"
        )
        return "Acceso denegado", 403

    if request.endpoint in master_socio and not usuario_puede_reportes():
        print(
            f"[PERMISO BLOQUEADO] "
            f"endpoint={request.endpoint} "
            f"rol={usuario_rol()} "
            f"path={request.path}"
        )
        return "Acceso denegado", 403

    if request.endpoint in master_cocina:
        if request.endpoint == "inventario" and not usuario_puede_ver_inventario():
            print(
                f"[PERMISO BLOQUEADO] "
                f"endpoint={request.endpoint} "
                f"rol={usuario_rol()} "
                f"path={request.path}"
            )
            return "Acceso denegado", 403
        if request.endpoint == "produccion" and not usuario_puede_produccion():
            print(
                f"[PERMISO BLOQUEADO] "
                f"endpoint={request.endpoint} "
                f"rol={usuario_rol()} "
                f"path={request.path}"
            )
            return "Acceso denegado", 403

    if request.endpoint in toma_ordenes and not usuario_puede_tomar_ordenes():
        print(
            f"[PERMISO BLOQUEADO] "
            f"endpoint={request.endpoint} "
            f"rol={usuario_rol()} "
            f"path={request.path}"
        )
        return "Acceso denegado", 403

    if request.endpoint in acceso_cocina and not usuario_puede_ver_cocina():
        print(
            f"[PERMISO BLOQUEADO] "
            f"endpoint={request.endpoint} "
            f"rol={usuario_rol()} "
            f"path={request.path}"
        )
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
            precio REAL,
            indicacion TEXT
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

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS auditoria_emergencias (
            id {pk_autoincrement_sql()},
            orden_id INTEGER,
            usuario TEXT,
            fecha TEXT,
            accion TEXT,
            observacion TEXT
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
    asegurar_columna("ordenes", "factura_reimpresion_token", "TEXT")
    asegurar_columna("ordenes", "inventario_descontado", "INTEGER DEFAULT 0")
    asegurar_columna("ordenes", "fecha_cobro", "TEXT")
    asegurar_columna("ordenes", "tasa_cobro", "REAL")
    asegurar_columna("ordenes", "subtotal_usd", "REAL")
    asegurar_columna("ordenes", "descuento_bs_snapshot", "REAL")
    asegurar_columna("ordenes", "total_usd", "REAL")
    asegurar_columna("ordenes", "total_bs", "REAL")
    asegurar_columna("orden_items", "indicacion", "TEXT")
    asegurar_columna("usuarios", "rol", "TEXT")
    asegurar_columna("usuarios", "activo", "INTEGER DEFAULT 1")
    asegurar_columna_facturar()
    limpiar_facturas_archivadas()
    crear_tablas_cierre_jornada()
    crear_tablas_cuentas_por_cobrar()
    crear_tablas_delivery()
    crear_tablas_inventario()
    asegurar_columna("inventario", "costo_promedio", "REAL DEFAULT 0")
    asegurar_columna("producciones", "merma", "REAL DEFAULT 0")
    asegurar_columna("producciones", "porcentaje_merma", "REAL DEFAULT 0")
    asegurar_columna("producciones", "costo_unitario_resultado", "REAL DEFAULT 0")
    asegurar_columna("producciones", "insumos_extra", "TEXT")
    asegurar_columna("producciones", "costo_insumos_extra", "REAL DEFAULT 0")
    asegurar_columna("producciones", "porciones_detalle", "TEXT")
    crear_usuarios_iniciales()
    crear_datos_base_inventario()
    asegurar_columna("categorias", "activo", "INTEGER DEFAULT 1")
    asegurar_columna("productos", "activo", "INTEGER DEFAULT 1")


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


def asegurar_menu_neko_wok():
    """Sincroniza el menú Neko Wok sin eliminar productos ni datos históricos."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT nombre FROM categorias")
    categorias_existentes = {row[0] for row in cursor.fetchall()}

    for cat in ORDEN_CATEGORIAS_POS:
        if cat not in categorias_existentes:
            cursor.execute("INSERT INTO categorias (nombre) VALUES (?)", (cat,))

    conn.commit()

    cursor.execute("SELECT id, nombre FROM categorias")
    cat_dict = {nombre: cat_id for cat_id, nombre in cursor.fetchall()}

    categorias_menu_controlado = [
        "Neko Combos", "Promociones Neko", "Neko Dúo", "Neko Clan",
        "Favoritos de Neko", "Bebidas",
    ]
    placeholders = ",".join("?" * len(categorias_menu_controlado))
    cursor.execute(
        f"""
        UPDATE productos SET activo=0
        WHERE categoria_id IN (
            SELECT id FROM categorias WHERE nombre IN ({placeholders})
        )
        """,
        categorias_menu_controlado,
    )

    for nombre, precio, categoria in PRODUCTOS_MENU_NEKO:
        categoria_id = cat_dict.get(categoria)
        cursor.execute(
            "SELECT id FROM productos WHERE lower(nombre)=lower(?) ORDER BY id LIMIT 1",
            (nombre,),
        )
        producto = cursor.fetchone()
        if producto:
            cursor.execute(
                "UPDATE productos SET nombre=?, precio=?, categoria_id=?, activo=1 WHERE id=?",
                (nombre, precio, categoria_id, producto[0]),
            )
        else:
            cursor.execute(
                "INSERT INTO productos (nombre, precio, categoria_id, activo) VALUES (?, ?, ?, 1)",
                (nombre, precio, categoria_id),
            )

    for cat in ORDEN_CATEGORIAS_POS:
        cursor.execute("UPDATE categorias SET activo=1 WHERE nombre=?", (cat,))
    conn.commit()
    conn.close()


def desactivar_menu_china_house():
    """Marca categorías y productos del menú antiguo China House como activo=0. Idempotente."""
    categorias_antiguas = ["Solo para ti", "Para compartir", "Banquete imperial", "Platos adicionales"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE categorias SET activo=1 WHERE activo IS NULL")
    cursor.execute("UPDATE productos SET activo=1 WHERE activo IS NULL")

    for cat_nombre in categorias_antiguas:
        cursor.execute("UPDATE categorias SET activo=0 WHERE nombre=?", (cat_nombre,))

    placeholders = ",".join("?" * len(categorias_antiguas))
    cursor.execute(
        f"""
        UPDATE productos SET activo=0
        WHERE categoria_id IN (
            SELECT id FROM categorias WHERE nombre IN ({placeholders})
        )
        """,
        categorias_antiguas,
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
          AND estado IN ('en cocina', 'listo', 'cerrada')
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
    cursor.execute("SELECT id, nombre FROM usuarios WHERE COALESCE(activo, 1) = 1 ORDER BY nombre")
    usuarios = cursor.fetchall()

    error = ""

    if request.method == "POST":
        usuario_id = request.form.get("usuario_id")
        pin = request.form.get("pin", "").strip()

        cursor.execute(
            """
            SELECT id, nombre, COALESCE(rol, 'mesonera')
            FROM usuarios
            WHERE id=? AND pin=? AND COALESCE(activo, 1) = 1
            """,
            (usuario_id, pin),
        )
        usuario = cursor.fetchone()

        if usuario:
            session["usuario_id"] = usuario[0]
            session["usuario_nombre"] = usuario[1]
            session["usuario"] = usuario[1]
            session["usuario_rol"] = usuario[2] or "mesonera"
            conn.close()
            if session["usuario_rol"] == "produccion":
                return redirect("/produccion")
            if session["usuario_rol"] in ("cocina", "cocina_reportes"):
                return redirect("/cocina")
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
    body {
        margin: 0;
        min-height: 100vh;
        display: flex;
        justify-content: center;
        align-items: center;
        background:
            radial-gradient(circle at 20% 80%, rgba(61, 220, 132, 0.06), transparent 40%),
            linear-gradient(160deg, #0F1115 0%, #151820 100%);
    }
    .login-wrap {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 24px;
        width: 92%;
        max-width: 420px;
    }
    .brand-logo {
        text-align: center;
        color: var(--texto);
    }
    .brand-logo .brand-icon { font-size: 52px; line-height: 1; filter: drop-shadow(0 0 8px rgba(61, 220, 132, 0.14)); }
    .brand-logo h1 {
        margin: 8px 0 2px;
        font-size: 32px;
        font-weight: 900;
        letter-spacing: -1px;
        color: var(--verde-neko);
        text-shadow: 0 0 8px rgba(61, 220, 132, 0.12);
    }
    .brand-logo .brand-sub {
        font-size: 13px;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: var(--texto-secundario);
        font-weight: 600;
    }
    .brand-logo .brand-accent { color: var(--verde-neko); }
    .login-box {
        background: var(--panel);
        width: 100%;
        padding: 32px 28px;
        border-radius: 16px;
        border: 1px solid var(--borde);
        box-shadow: 0 22px 48px rgba(0, 0, 0, 0.32);
    }
    .login-box h2 {
        margin: 0 0 20px;
        font-size: 18px;
        font-weight: 700;
        color: var(--texto);
        text-align: center;
    }
    label { display: block; font-size: 13px; font-weight: 700; color: var(--texto-secundario); margin-bottom: 4px; margin-top: 14px; text-transform: uppercase; letter-spacing: 0.5px; }
    input, select { width: 100%; padding: 13px 16px; border-radius: 10px; border: 1.5px solid var(--borde); font-size: 16px; box-sizing: border-box; transition: border-color 0.15s, box-shadow 0.15s; background: var(--panel-secundario); color: var(--texto); }
    input:focus, select:focus { outline: none; border-color: var(--verde-neko); box-shadow: 0 0 0 3px rgba(61,220,132,0.12); }
    .btn-login {
        width: 100%;
        padding: 15px;
        background: var(--verde-neko);
        color: #0F1115;
        border: none;
        border-radius: 12px;
        font-size: 17px;
        font-weight: 800;
        margin-top: 20px;
        cursor: pointer;
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.20);
        transition: transform 0.1s, box-shadow 0.1s;
    }
    .btn-login:hover { background: var(--hover-neko); box-shadow: 0 8px 18px rgba(0, 0, 0, 0.24); }
    .btn-login:active { transform: scale(0.98); }
    .error { background: #fef2f2; color: #dc2626; padding: 12px 14px; border-radius: 8px; margin-bottom: 4px; text-align: center; font-weight: 600; border: 1px solid #fecaca; }
    .login-footer { color: rgba(255,255,255,0.45); font-size: 12px; text-align: center; }
    </style>
    </head>
    <body>
    <div class="login-wrap">
        <div class="brand-logo">
            <div class="brand-icon">🐱</div>
            <h1>Neko <span class="brand-accent">Wok</span></h1>
            <div class="brand-sub">Sistema POS</div>
        </div>
        <div class="login-box">
            <h2>🔐 Iniciar sesión</h2>
    """

    if error:
        html += f"<div class='error'>⚠️ {error}</div>"

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
                <input type="password" name="pin" required placeholder="••••••">
                <button class="btn-login" type="submit">Entrar →</button>
            </form>
        </div>
        <div class="login-footer">Neko Wok POS · Sistema de gestión</div>
    </div>
    </body>
    </html>
    """

    return html


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


def opciones_roles_usuario(rol_actual=""):
    opciones = []
    for rol in ROLES_USUARIO_VALIDOS:
        seleccionado = " selected" if rol == rol_actual else ""
        opciones.append(f'<option value="{rol}"{seleccionado}>{rol}</option>')
    return "".join(opciones)


def rol_desde_formulario():
    rol = (request.form.get("rol") or "").strip().lower()
    if rol not in ROLES_USUARIO_VALIDOS:
        return ""
    return rol


def estilos_admin_cxc():
    return """
    body { margin:0; background:var(--gris-fondo); color:var(--texto); }
    .contenido { padding:18px; max-width:1180px; margin:auto; }
    .toolbar { display:flex; gap:10px; flex-wrap:wrap; align-items:end; margin:0 0 14px; }
    .toolbar > div { flex:1 1 180px; }
    .card-admin { background:var(--tarjeta); border:1px solid var(--borde); border-radius:10px; padding:16px; box-shadow:var(--sombra-suave); margin-bottom:14px; overflow:auto; }
    .metricas { display:grid; grid-template-columns:repeat(4, minmax(140px, 1fr)); gap:10px; margin:12px 0; }
    .metrica { background:var(--panel-secundario); border:1px solid var(--borde); border-radius:8px; padding:14px; }
    .metrica small { color:var(--texto-secundario); font-weight:800; text-transform:uppercase; font-size:11px; }
    .metrica b { display:block; font-size:24px; margin-top:6px; }
    table { width:100%; border-collapse:collapse; min-width:760px; }
    th, td { padding:10px; border-bottom:1px solid var(--borde); text-align:left; vertical-align:top; }
    th { color:var(--verde-neko); background:var(--panel-secundario); font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
    .monto { text-align:right; white-space:nowrap; font-weight:800; }
    .acciones { display:flex; gap:8px; flex-wrap:wrap; }
    .btn-mini { display:inline-block; padding:8px 12px; border-radius:7px; background:var(--azul); color:white; text-decoration:none; font-weight:800; border:0; cursor:pointer; }
    .btn-sec { background:var(--panel-secundario); color:var(--texto); border:1px solid var(--borde); }
    .btn-danger { background:#b91c1c; color:white; }
    .badge-estado { display:inline-block; padding:4px 9px; border-radius:999px; font-size:12px; font-weight:900; text-transform:uppercase; }
    .estado-pendiente { background:#fef3c7; color:#92400e; }
    .estado-pagada { background:#dcfce7; color:#166534; }
    .estado-anulada { background:#fee2e2; color:#991b1b; }
    .tabs-cxc { display:grid; grid-template-columns:repeat(3, minmax(150px, 1fr)); gap:10px; margin:12px 0 16px; }
    .tab-cxc { background:var(--panel-secundario); border:1px solid var(--borde); border-radius:8px; color:var(--texto); min-height:58px; padding:12px; text-decoration:none; display:flex; align-items:center; justify-content:center; text-align:center; font-weight:900; }
    .tab-cxc.activo { background:var(--verde-neko); color:#0F1115; border-color:var(--verde-neko); }
    .form-grid { display:grid; grid-template-columns:repeat(2, minmax(180px, 1fr)); gap:12px; }
    .full { grid-column:1 / -1; }
    .nota-alerta { background:#fff7ed; color:#7c2d12; border:1px solid #fed7aa; border-radius:8px; padding:12px; margin:10px 0; }
    @media (max-width: 760px) {
        .metricas, .form-grid { grid-template-columns:1fr; }
        .contenido { padding:12px; }
    }
    """


def tabs_cuentas_por_cobrar(activo):
    items = [
        ("cuentas", "/cuentas_por_cobrar", "Cuentas"),
        ("clientes", "/cuentas_por_cobrar/clientes", "Cartera de clientes"),
    ]
    return (
        '<div class="tabs-cxc">'
        + "".join(
            f'<a class="tab-cxc{" activo" if clave == activo else ""}" href="{url}">{texto}</a>'
            for clave, url, texto in items
        )
        + "</div>"
    )


def opciones_filtro_cliente(filtro_actual):
    opciones = [
        ("todos", "Todos"),
        ("con_saldo", "Con saldo pendiente"),
        ("sin_saldo", "Sin saldo pendiente"),
        ("activos", "Activos"),
        ("inactivos", "Inactivos"),
    ]
    return "".join(
        f'<option value="{valor}"{" selected" if valor == filtro_actual else ""}>{texto}</option>'
        for valor, texto in opciones
    )


def opciones_estado_cxc(estado_actual):
    opciones = [
        ("pendiente", "Pendientes"),
        ("pagada", "Pagadas"),
        ("anulada", "Anuladas"),
        ("todas", "Todas"),
    ]
    return "".join(
        f'<option value="{valor}"{" selected" if valor == estado_actual else ""}>{texto}</option>'
        for valor, texto in opciones
    )


@app.route("/clientes")
@app.route("/cuentas_por_cobrar/clientes")
def clientes():
    if request.path == "/clientes":
        return redirect("/cuentas_por_cobrar/clientes")

    conn = get_connection()
    cursor = conn.cursor()
    busqueda = (request.args.get("q") or "").strip()
    filtro = (request.args.get("filtro") or "todos").strip().lower()
    clientes_rows = listar_clientes_admin(cursor, busqueda, filtro)
    conn.close()

    filas = ""
    for row in clientes_rows:
        cliente_id, nombre, telefono, documento, activo, saldo, cuentas, pagadas = row
        estado = "Activo" if activo else "Inactivo"
        filas += f"""
        <tr>
            <td><b>{html_lib.escape(nombre or '')}</b></td>
            <td>{html_lib.escape(telefono or '-')}</td>
            <td>{html_lib.escape(documento or '-')}</td>
            <td>{estado}</td>
            <td class="monto">{formato_usd(saldo)}</td>
            <td class="monto">{int(cuentas or 0)}</td>
            <td class="acciones">
                <a class="btn-mini" href="/cuentas_por_cobrar/clientes/{cliente_id}">Ver</a>
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes/{cliente_id}/editar">Editar</a>
            </td>
        </tr>
        """
    if not filas:
        filas = '<tr><td colspan="7">No hay clientes para este filtro.</td></tr>'

    return f"""
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>Cuentas por cobrar</h1>
        {tabs_cuentas_por_cobrar("clientes")}
        <h2>Cartera de clientes</h2>
        <div class="card-admin">
            <form method="get" class="toolbar">
                <div><label>Buscar</label><input name="q" value="{html_lib.escape(busqueda, quote=True)}" placeholder="Nombre, telefono o documento"></div>
                <div><label>Filtro</label><select name="filtro">{opciones_filtro_cliente(filtro)}</select></div>
                <button type="submit">Buscar</button>
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Limpiar</a>
                <a class="btn-mini" href="/cuentas_por_cobrar/clientes/nuevo">Nuevo cliente</a>
            </form>
        </div>
        <div class="card-admin">
            <table>
                <thead><tr><th>Cliente</th><th>Telefono</th><th>Documento</th><th>Estado</th><th>Saldo pendiente</th><th>Cuentas</th><th>Acciones</th></tr></thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
    </div></body></html>
    """


@app.route("/clientes/nuevo", methods=["GET", "POST"])
@app.route("/cuentas_por_cobrar/clientes/nuevo", methods=["GET", "POST"])
def crear_cliente():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()
        documento = (request.form.get("documento") or "").strip()
        notas = (request.form.get("notas") or "").strip()
        activo = 1 if request.form.get("activo", "1") == "1" else 0
        if not nombre:
            return "El nombre del cliente es obligatorio", 400
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clientes (nombre, telefono, documento, notas, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nombre, telefono, documento, notas, activo, ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")),
        )
        cliente_id = obtener_ultimo_id(cursor, "clientes")
        conn.commit()
        conn.close()
        return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

    return render_form_cliente()


@app.route("/clientes/<int:cliente_id>")
@app.route("/cuentas_por_cobrar/clientes/<int:cliente_id>")
def detalle_cliente(cliente_id):
    if request.path.startswith("/clientes/"):
        return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

    conn = get_connection()
    cursor = conn.cursor()
    cliente = obtener_cliente_admin(cursor, cliente_id)
    if not cliente:
        conn.close()
        return "Cliente no encontrado", 404
    resumen = obtener_resumen_cliente(cursor, cliente_id)
    cuentas = listar_cuentas_cliente(cursor, cliente_id)
    conn.close()

    filas = ""
    for cuenta in cuentas:
        cuenta_id, orden_id, numero, fecha, original, saldo, estado, snapshot = cuenta
        filas += f"""
        <tr>
            <td><a href="/cuentas_por_cobrar/{cuenta_id}">#{html_lib.escape(str(numero or orden_id))}</a></td>
            <td>{texto_fecha_corta(fecha)}</td>
            <td class="monto">{formato_usd(original)}</td>
            <td class="monto">{formato_usd(saldo)}</td>
            <td>{estado_cxc_badge(estado)}</td>
            <td>{html_lib.escape(snapshot or '')}</td>
        </tr>
        """
    if not filas:
        filas = '<tr><td colspan="6">Este cliente no tiene cuentas por cobrar.</td></tr>'

    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>Cuentas por cobrar</h1>
        {tabs_cuentas_por_cobrar("clientes")}
        <h1>{html_lib.escape(cliente[1] or '')}</h1>
        <div class="acciones" style="margin-bottom:12px;">
            <a class="btn-mini" href="/cuentas_por_cobrar/clientes/{cliente_id}/editar">Editar cliente</a>
            <a class="btn-mini btn-sec" href="/cuentas_por_cobrar?cliente_id={cliente_id}&estado=todas">Ver sus cuentas</a>
            <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Volver a cartera</a>
        </div>
        <div class="card-admin">
            <h2>Datos</h2>
            <p><b>Telefono:</b> {html_lib.escape(cliente[2] or '-')}</p>
            <p><b>Documento:</b> {html_lib.escape(cliente[3] or '-')}</p>
            <p><b>Notas:</b> {html_lib.escape(cliente[4] or '-')}</p>
            <p><b>Estado:</b> {'Activo' if cliente[5] else 'Inactivo'}</p>
        </div>
        <div class="metricas">
            <div class="metrica"><small>Saldo pendiente</small><b>{formato_usd(resumen["saldo_pendiente"])}</b></div>
            <div class="metrica"><small>Cuentas pendientes</small><b>{resumen["cuentas_pendientes"]}</b></div>
            <div class="metrica"><small>Cuentas pagadas</small><b>{resumen["cuentas_pagadas"]}</b></div>
            <div class="metrica"><small>Deuda historica</small><b>{formato_usd(resumen["total_deuda_generada"])}</b></div>
        </div>
        <div class="card-admin">
            <h2>Cuentas por cobrar</h2>
            <table>
                <thead><tr><th>Orden</th><th>Generada</th><th>Original</th><th>Pendiente</th><th>Estado</th><th>Snapshot cliente</th></tr></thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
    </div></body></html>
    """


def render_form_cliente(cliente=None):
    cliente = cliente or ("", "", "", "", "", 1, "")
    cliente_id = cliente[0] or ""
    titulo = "Nuevo cliente" if not cliente_id else "Editar cliente"
    activo = int(cliente[5] if len(cliente) > 5 else 1)
    opciones_activo = (
        f'<option value="1"{" selected" if activo else ""}>Activo</option>'
        f'<option value="0"{" selected" if not activo else ""}>Inactivo</option>'
    )
    accion_desactivar = ""
    if cliente_id:
        etiqueta = "Desactivar" if activo else "Activar"
        estilo = "btn-danger" if activo else ""
        accion_desactivar = f"""
        <form method="post" action="/cuentas_por_cobrar/clientes/{cliente_id}/activar" style="margin-top:12px;">
            <button type="submit" class="btn-mini {estilo}">{etiqueta}</button>
        </form>
        """

    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>Cuentas por cobrar</h1>
        {tabs_cuentas_por_cobrar("clientes")}
        <h2>{titulo}</h2>
        <div class="card-admin">
            <form method="post" class="form-grid">
                <div><label>Nombre</label><input name="nombre" required value="{html_lib.escape(cliente[1] or '', quote=True)}"></div>
                <div><label>Telefono</label><input name="telefono" value="{html_lib.escape(cliente[2] or '', quote=True)}"></div>
                <div><label>Documento</label><input name="documento" value="{html_lib.escape(cliente[3] or '', quote=True)}"></div>
                <div><label>Estado</label><select name="activo">{opciones_activo}</select></div>
                <div class="full"><label>Notas</label><textarea name="notas">{html_lib.escape(cliente[4] or '')}</textarea></div>
                <div class="acciones full">
                    <button type="submit">Guardar</button>
                    <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Cancelar</a>
                </div>
            </form>
            {accion_desactivar}
        </div>
    </div></body></html>
    """


@app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@app.route("/cuentas_por_cobrar/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
def editar_cliente(cliente_id):
    conn = get_connection()
    cursor = conn.cursor()
    cliente = obtener_cliente_admin(cursor, cliente_id)
    if not cliente:
        conn.close()
        return "Cliente no encontrado", 404

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()
        documento = (request.form.get("documento") or "").strip()
        notas = (request.form.get("notas") or "").strip()
        activo = 1 if request.form.get("activo", "1") == "1" else 0
        if not nombre:
            conn.close()
            return "El nombre del cliente es obligatorio", 400
        cursor.execute(
            """
            UPDATE clientes
            SET nombre=?, telefono=?, documento=?, notas=?, activo=?
            WHERE id=?
            """,
            (nombre, telefono, documento, notas, activo, cliente_id),
        )
        conn.commit()
        conn.close()
        return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

    conn.close()
    return render_form_cliente(cliente)


@app.route("/clientes/<int:cliente_id>/activar", methods=["POST"])
@app.route("/cuentas_por_cobrar/clientes/<int:cliente_id>/activar", methods=["POST"])
def activar_cliente(cliente_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(activo, 1) FROM clientes WHERE id=?", (cliente_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Cliente no encontrado", 404
    nuevo_activo = 0 if row[0] else 1
    cursor.execute("UPDATE clientes SET activo=? WHERE id=?", (nuevo_activo, cliente_id))
    conn.commit()
    conn.close()
    return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")


@app.route("/cuentas_por_cobrar")
@app.route("/cuentas_por_cobrar/cuentas")
def cuentas_por_cobrar_admin():
    conn = get_connection()
    cursor = conn.cursor()
    busqueda = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "pendiente").strip().lower()
    cliente_id = (request.args.get("cliente_id") or "").strip()
    resumen = resumen_cuentas_por_cobrar(cursor)
    cuentas = listar_cuentas_por_cobrar_admin(cursor, busqueda, estado, cliente_id)
    clientes_filtro = listar_clientes_admin(cursor, "", "todos")
    conn.close()

    opciones_cliente = ['<option value="">Todos los clientes</option>']
    for cliente in clientes_filtro:
        selected = " selected" if str(cliente[0]) == cliente_id else ""
        opciones_cliente.append(
            f'<option value="{cliente[0]}"{selected}>{html_lib.escape(cliente[1] or "")}</option>'
        )

    filas = ""
    for row in cuentas:
        cuenta_id, cli_id, snapshot, nombre_actual, telefono, documento, orden_id, numero, fecha, original, saldo, estado_row = row
        cliente_texto = snapshot or nombre_actual or "Cliente"
        filas += f"""
        <tr>
            <td><a href="/cuentas_por_cobrar/clientes/{cli_id}">{html_lib.escape(cliente_texto)}</a><br><small>{html_lib.escape(telefono or documento or '')}</small></td>
            <td>#{html_lib.escape(str(numero or orden_id))}</td>
            <td>{texto_fecha_corta(fecha)}</td>
            <td class="monto">{formato_usd(original)}</td>
            <td class="monto">{formato_usd(saldo)}</td>
            <td>{estado_cxc_badge(estado_row)}</td>
            <td><a class="btn-mini" href="/cuentas_por_cobrar/{cuenta_id}">Ver</a></td>
        </tr>
        """
    if not filas:
        filas = '<tr><td colspan="7">No hay cuentas por cobrar para este filtro.</td></tr>'

    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>Cuentas por cobrar</h1>
        {tabs_cuentas_por_cobrar("cuentas")}
        <div class="metricas">
            <div class="metrica"><small>Saldo total pendiente</small><b>{formato_usd(resumen["saldo_total"])}</b></div>
            <div class="metrica"><small>Clientes con deuda</small><b>{resumen["clientes_con_deuda"]}</b></div>
            <div class="metrica"><small>Cuentas pendientes</small><b>{resumen["cuentas_pendientes"]}</b></div>
            <div class="metrica"><small>Cuentas pagadas</small><b>{resumen["cuentas_pagadas"]}</b></div>
        </div>
        {f'''
        <div class="card-admin">
            <form method="get" class="toolbar">
                <div><label>Buscar</label><input name="q" value="{html_lib.escape(busqueda, quote=True)}" placeholder="Cliente, orden, telefono o documento"></div>
                <div><label>Estado</label><select name="estado">{opciones_estado_cxc(estado)}</select></div>
                <div><label>Cliente</label><select name="cliente_id">{''.join(opciones_cliente)}</select></div>
                <button type="submit">Filtrar</button>
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar">Limpiar</a>
            </form>
        </div>
        <div class="card-admin">
            <h2>Cuentas</h2>
            <table>
                <thead><tr><th>Cliente</th><th>Orden</th><th>Generada</th><th>Original</th><th>Pendiente</th><th>Estado</th><th>Accion</th></tr></thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
        '''}
    </div></body></html>
    """


@app.route("/cuentas_por_cobrar/<int:cuenta_id>")
def detalle_cuenta_por_cobrar(cuenta_id):
    conn = get_connection()
    cursor = conn.cursor()
    detalle = obtener_detalle_cuenta_cxc(cursor, cuenta_id)
    conn.close()
    if not detalle:
        return "Cuenta por cobrar no encontrada", 404

    c = detalle["cuenta"]
    movimientos = ""
    for mov in detalle["movimientos"]:
        fecha, tipo, monto_saldo, moneda_pago, monto_pago, tasa_mov, metodo, referencia, usuario, observacion = mov
        signo = "+" if a_float(monto_saldo) > 0 else ""
        movimientos += f"""
        <tr>
            <td>{texto_fecha_corta(fecha)}</td>
            <td>{html_lib.escape(tipo or '')}</td>
            <td class="monto">{signo}{formato_usd(monto_saldo)}</td>
            <td>{html_lib.escape(moneda_pago or '-')}</td>
            <td class="monto">{monto_formateado_segun_metodo(metodo, monto_pago) if monto_pago is not None else '-'}</td>
            <td>{a_float(tasa_mov) if tasa_mov else '-'}</td>
            <td>{html_lib.escape(etiqueta_metodo_pago(metodo))}</td>
            <td>{html_lib.escape(referencia or '-')}</td>
            <td>{html_lib.escape(usuario or '-')}</td>
            <td>{html_lib.escape(observacion or '-')}</td>
        </tr>
        """
    if not movimientos:
        movimientos = '<tr><td colspan="10">No hay movimientos registrados.</td></tr>'

    alerta = ""
    if detalle["inconsistente"]:
        print(
            f"[CXC INCONSISTENTE] cuenta_id={c[0]} saldo={c[6]} suma_movimientos={detalle['suma_movimientos']}"
        )
        alerta = (
            '<div class="nota-alerta">Atencion: el saldo cacheado no coincide con '
            'la suma de movimientos. Revisar administrativamente.</div>'
        )

    numero_orden = c[13] or c[1]
    pagado = detalle["pagado_inicial"]
    fecha_venta = c[14] or c[7]
    acciones_abono = ""
    if not detalle["inconsistente"] and c[8] == "pendiente" and a_float(c[6]) > TOLERANCIA_COBRO:
        acciones_abono = f"""
        <div class="card-admin">
            <h2>Acciones</h2>
            <div class="acciones">
                <a class="btn-mini" href="/cuentas_por_cobrar/{cuenta_id}/abono">Registrar abono</a>
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/{cuenta_id}/abono?completo=1">Pagar saldo completo</a>
            </div>
        </div>
        """
    elif c[8] == "pagada" or a_float(c[6]) <= TOLERANCIA_COBRO:
        acciones_abono = '<div class="card-admin"><h2>Cuenta pagada</h2><p>No hay saldo pendiente para abonar.</p></div>'
    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>Cuenta por cobrar #{cuenta_id}</h1>
        {tabs_cuentas_por_cobrar("cuentas")}
        {alerta}
        <div class="acciones" style="margin-bottom:12px;">
            <a class="btn-mini" href="/cuentas_por_cobrar/clientes/{c[2]}">Ver cliente</a>
            <a class="btn-mini btn-sec" href="/cuentas_por_cobrar">Volver a cuentas</a>
            <a class="btn-mini btn-sec" href="/orden/{c[1]}">Ver orden</a>
        </div>
        <div class="metricas">
            <div class="metrica"><small>Valor de venta</small><b>{formato_usd(c[19])}</b></div>
            <div class="metrica"><small>Cobrado al cerrar</small><b>{formato_usd(pagado["usd"])}</b></div>
            <div class="metrica"><small>Deuda generada</small><b>{formato_usd(c[5])}</b></div>
            <div class="metrica"><small>Saldo actual</small><b>{formato_usd(c[6])}</b></div>
        </div>
        {acciones_abono}
        <div class="card-admin">
            <h2>Cliente</h2>
            <p><b>Snapshot:</b> {html_lib.escape(c[3] or '')}</p>
            <p><b>Nombre actual:</b> {html_lib.escape(c[10] or '-')}</p>
            <p><b>Telefono:</b> {html_lib.escape(c[11] or '-')}</p>
            <p><b>Documento:</b> {html_lib.escape(c[12] or '-')}</p>
        </div>
        <div class="card-admin">
            <h2>Venta origen</h2>
            <p><b>Orden:</b> #{html_lib.escape(str(numero_orden))}</p>
            <p><b>Fecha de venta:</b> {texto_fecha_corta(fecha_venta)}</p>
            <p><b>Total original de venta:</b> {formato_usd(c[19])} / {formato_bs(c[20])}</p>
            <p><b>Pagado al momento:</b> {formato_usd(pagado["usd"])} / {formato_bs(pagado["bs"])}</p>
            <p><b>Tasa historica:</b> {a_float(c[16])}</p>
        </div>
        <div class="card-admin">
            <h2>Estado actual</h2>
            <p><b>Deuda original:</b> {formato_usd(c[5])}</p>
            <p><b>Saldo pendiente:</b> {formato_usd(c[6])}</p>
            <p><b>Suma movimientos:</b> {formato_usd(detalle["suma_movimientos"])}</p>
            <p><b>Estado:</b> {estado_cxc_badge(c[8])}</p>
        </div>
        <div class="card-admin">
            <h2>Movimientos</h2>
            <table>
                <thead><tr><th>Fecha</th><th>Tipo</th><th>Monto saldo</th><th>Moneda pago</th><th>Monto pago</th><th>Tasa</th><th>Metodo</th><th>Referencia</th><th>Usuario</th><th>Observacion</th></tr></thead>
                <tbody>{movimientos}</tbody>
            </table>
        </div>
    </div></body></html>
    """


def opciones_metodos_abono(metodo_actual="usd"):
    opciones = []
    for metodo in METODOS_PAGO_VALIDOS:
        etiqueta = etiqueta_metodo_pago(metodo)
        selected = " selected" if metodo == metodo_actual else ""
        opciones.append(f'<option value="{metodo}"{selected}>{html_lib.escape(etiqueta)}</option>')
    return "".join(opciones)


def render_form_abono_cxc(cuenta_id, detalle, error="", completo=False, valores=None):
    valores = valores or {}
    c = detalle["cuenta"]
    tasa_actual = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        tasa_actual = obtener_tasa_cobro(cursor)
        conn.close()
    except Exception:
        tasa_actual = None

    metodo = valores.get("metodo_pago") or "usd"
    monto_val = valores.get("monto") or (str(round(a_float(c[6]), 2)) if completo else "")
    referencia = valores.get("referencia") or ""
    observacion = valores.get("observacion") or ""
    equivalente_bs = formato_bs(a_float(c[6]) * tasa_actual) if tasa_actual else "Tasa no disponible"
    titulo = "Pagar saldo completo" if completo else "Registrar abono"

    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/cuentas_por_cobrar">Cuentas</a><a href="/cuentas_por_cobrar/clientes">Cartera de clientes</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>Cuentas por cobrar</h1>
        {tabs_cuentas_por_cobrar("cuentas")}
        <h2>{titulo}</h2>
        {"<div class='error'>" + html_lib.escape(error) + "</div>" if error else ""}
        <div class="metricas">
            <div class="metrica"><small>Cliente</small><b>{html_lib.escape(c[3] or c[10] or "-")}</b></div>
            <div class="metrica"><small>Orden origen</small><b>#{html_lib.escape(str(c[13] or c[1]))}</b></div>
            <div class="metrica"><small>Deuda original</small><b>{formato_usd(c[5])}</b></div>
            <div class="metrica"><small>Saldo pendiente</small><b>{formato_usd(c[6])}</b></div>
        </div>
        <div class="card-admin">
            <p><b>Equivalente para pago completo en Bs:</b> {equivalente_bs}</p>
            <form method="post" class="form-grid" id="formAbonoCxc">
                <div>
                    <label>Metodo de pago</label>
                    <select name="metodo_pago" id="metodo_pago_abono">{opciones_metodos_abono(metodo)}</select>
                </div>
                <div>
                    <label>Monto recibido</label>
                    <input name="monto" id="monto_abono" type="number" step="0.01" min="0.01" value="{html_lib.escape(str(monto_val), quote=True)}" required>
                </div>
                <div>
                    <label>Referencia</label>
                    <input name="referencia" value="{html_lib.escape(referencia, quote=True)}">
                </div>
                <div>
                    <label>Observaci&oacute;n</label>
                    <input name="observacion" value="{html_lib.escape(observacion, quote=True)}">
                </div>
                <div class="acciones full">
                    <button type="submit">Confirmar</button>
                    <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/{cuenta_id}">Cancelar</a>
                </div>
            </form>
        </div>
    </div>
    <script>
    const formAbono = document.getElementById("formAbonoCxc");
    const metodoAbono = document.getElementById("metodo_pago_abono");
    const montoAbono = document.getElementById("monto_abono");
    const saldoActual = {round(a_float(c[6]), 2)};
    const tasaActual = {json.dumps(tasa_actual)};
    function metodoBs(metodo) {{
        return metodo === "punto_venta" || metodo === "bs_pago_movil" || metodo === "bs_efectivo";
    }}
    function numeroAbono(valor) {{
        const n = parseFloat(String(valor || "0").replace(",", "."));
        return Number.isFinite(n) ? n : 0;
    }}
    formAbono.addEventListener("submit", function(event) {{
        const monto = numeroAbono(montoAbono.value);
        let equivalente = monto;
        let mensaje = "Registrar abono de $" + equivalente.toFixed(2) + "\\n";
        if (metodoBs(metodoAbono.value)) {{
            if (!tasaActual || tasaActual <= 0) {{
                event.preventDefault();
                alert("No hay una tasa de cambio valida para registrar el abono.");
                return;
            }}
            equivalente = monto / tasaActual;
            mensaje = "Pago recibido: " + monto.toFixed(2) + " Bs\\nTasa: " + tasaActual.toFixed(2) + " Bs/$\\nAbono equivalente: $" + equivalente.toFixed(2) + "\\n";
        }}
        const nuevoSaldo = Math.max(saldoActual - equivalente, 0);
        mensaje += "Saldo anterior: $" + saldoActual.toFixed(2) + "\\nNuevo saldo: $" + nuevoSaldo.toFixed(2) + "\\nConfirmar?";
        if (!confirm(mensaje)) {{
            event.preventDefault();
        }}
    }});
    </script>
    </body></html>
    """


@app.route("/cuentas_por_cobrar/<int:cuenta_id>/abono", methods=["GET", "POST"])
def registrar_abono_cxc(cuenta_id):
    conn = get_connection()
    cursor = conn.cursor()
    detalle = obtener_detalle_cuenta_cxc(cursor, cuenta_id)
    if not detalle:
        conn.close()
        return "Cuenta por cobrar no encontrada", 404

    completo = request.args.get("completo") == "1"
    if request.method == "GET":
        conn.close()
        return render_form_abono_cxc(cuenta_id, detalle, completo=completo)

    valores = {
        "metodo_pago": request.form.get("metodo_pago", ""),
        "monto": request.form.get("monto", ""),
        "referencia": request.form.get("referencia", ""),
        "observacion": request.form.get("observacion", ""),
    }
    try:
        registrar_abono_cuenta(
            cursor,
            cuenta_id,
            valores["metodo_pago"],
            valores["monto"],
            valores["referencia"],
            valores["observacion"],
            session.get("usuario_id"),
        )
        conn.commit()
        conn.close()
        return redirect(f"/cuentas_por_cobrar/{cuenta_id}")
    except ValueError as exc:
        conn.rollback()
        detalle = obtener_detalle_cuenta_cxc(cursor, cuenta_id)
        conn.close()
        return render_form_abono_cxc(cuenta_id, detalle, error=str(exc), completo=completo, valores=valores), 400
    except Exception:
        conn.rollback()
        conn.close()
        raise


@app.route("/usuarios")
def usuarios():
    if not usuario_es_master():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(rol, 'mesonera'), pin, COALESCE(activo, 1)
        FROM usuarios
        ORDER BY COALESCE(activo, 1) DESC, rol ASC, nombre ASC
        """
    )
    filas_usuarios = cursor.fetchall()
    conn.close()

    filas_activos = ""
    filas_inactivos = ""
    for usuario_id, nombre, rol, pin, activo in filas_usuarios:
        pin_estado = "Configurado" if pin else "Sin configurar"
        badge_activo = (
            '<span style="background:#dcfce7;color:#166534;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:700;">Activo</span>'
            if activo else
            '<span style="background:#fee2e2;color:#991b1b;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:700;">Inactivo</span>'
        )
        toggle_label = "Desactivar" if activo else "Activar"
        toggle_style = "background:#ef4444;" if activo else "background:#16a34a;"
        fila = f"""
        <tr>
            <td>{html_lib.escape(nombre or '')}</td>
            <td><code style="font-size:13px;">{html_lib.escape(rol or 'mesonera')}</code></td>
            <td>{pin_estado}</td>
            <td>{badge_activo}</td>
            <td style="display:flex;gap:6px;flex-wrap:wrap;">
                <a class="btn-accion btn-editar" href="/editar_usuario/{usuario_id}">✏️ Editar</a>
                <form method="post" action="/activar_usuario/{usuario_id}" style="margin:0;">
                    <button type="submit" class="btn-accion" style="{toggle_style}color:white;border:none;cursor:pointer;">{toggle_label}</button>
                </form>
            </td>
        </tr>
        """
        if activo:
            filas_activos += fila
        else:
            filas_inactivos += fila

    if not filas_activos:
        filas_activos = '<tr><td colspan="5">No hay usuarios activos.</td></tr>'
    if not filas_inactivos:
        filas_inactivos = '<tr><td colspan="5">No hay usuarios inactivos.</td></tr>'

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; max-width:960px; margin:auto; }}
    .card {{ background:var(--tarjeta); color:var(--texto); padding:18px; border-radius:10px; box-shadow:var(--sombra-suave); border:1px solid var(--borde); overflow:auto; margin-bottom:16px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid var(--borde); padding:10px; text-align:left; vertical-align:middle; }}
    th {{ background:var(--panel-secundario); color:var(--verde-neko); font-weight:800; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; }}
    .form-grid {{ display:grid; grid-template-columns:1fr 1fr 1fr 1fr auto; gap:10px; align-items:end; }}
    .btn-accion {{ display:inline-block; padding:7px 12px; border-radius:6px; text-decoration:none; font-weight:700; font-size:13px; }}
    .btn-editar {{ color:white; background:var(--azul); }}
    .seccion-titulo {{ font-size:13px; font-weight:800; color:var(--texto-secundario); text-transform:uppercase; letter-spacing:0.5px; margin:0 0 12px 0; }}
    @media (max-width: 760px) {{ .form-grid {{ grid-template-columns:1fr; }} }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">🏠 Inicio</a>')}
    <div class="contenido">
        <h1>👥 Usuarios</h1>
        <div class="card">
            <h2>➕ Crear usuario</h2>
            <form method="post" action="/crear_usuario" class="form-grid">
                <div>
                    <label>Nombre</label>
                    <input name="nombre" required>
                </div>
                <div>
                    <label>PIN</label>
                    <input name="pin" required>
                </div>
                <div>
                    <label>Rol</label>
                    <select name="rol" required>{opciones_roles_usuario('mesonera_reportes')}</select>
                </div>
                <div>
                    <label>Estado</label>
                    <select name="activo">
                        <option value="1">Activo</option>
                        <option value="0">Inactivo</option>
                    </select>
                </div>
                <button type="submit" style="align-self:end;">➕ Crear</button>
            </form>
        </div>
        <div class="card">
            <p class="seccion-titulo">✅ Usuarios activos</p>
            <table>
                <thead><tr><th>Nombre</th><th>Rol</th><th>PIN</th><th>Estado</th><th>Acciones</th></tr></thead>
                <tbody>{filas_activos}</tbody>
            </table>
        </div>
        <div class="card">
            <p class="seccion-titulo">🚫 Usuarios inactivos</p>
            <table>
                <thead><tr><th>Nombre</th><th>Rol</th><th>PIN</th><th>Estado</th><th>Acciones</th></tr></thead>
                <tbody>{filas_inactivos}</tbody>
            </table>
        </div>
        <div class="card" style="border:2px solid #f97316;background:#fff7ed;">
            <h2 style="color:#c2410c;margin-top:0;">⚠️ Zona de peligro</h2>
            <p style="color:#7c2d12;margin:0 0 14px 0;">Reinicia la base de datos y deja el sistema limpio con solo el menú Neko Wok. Borra órdenes, pagos, cierres e inventario. <b>No se puede deshacer.</b></p>
            <a href="/reset_neko" style="display:inline-block;background:#dc2626;color:white;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold;">⚠️ Reset Neko</a>
        </div>
    </div>
    </body>
    </html>
    """


@app.route("/crear_usuario", methods=["POST"])
def crear_usuario():
    if not usuario_es_master():
        return "Acceso denegado", 403

    nombre = (request.form.get("nombre") or "").strip()
    pin = (request.form.get("pin") or "").strip()
    rol = rol_desde_formulario()
    activo = 1 if request.form.get("activo", "1") == "1" else 0

    if not nombre or not pin or not rol:
        return "Datos invalidos", 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (nombre, pin, rol, activo)
        VALUES (?, ?, ?, ?)
        """,
        (nombre, pin, rol, activo),
    )
    conn.commit()
    conn.close()
    return redirect("/usuarios")


@app.route("/editar_usuario/<int:usuario_id>", methods=["GET", "POST"])
def editar_usuario(usuario_id):
    if not usuario_es_master():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        pin = (request.form.get("pin") or "").strip()
        rol = rol_desde_formulario()

        if not nombre or not rol:
            conn.close()
            return "Datos invalidos", 400

        if pin:
            cursor.execute(
                """
                UPDATE usuarios
                SET nombre=?, pin=?, rol=?
                WHERE id=?
                """,
                (nombre, pin, rol, usuario_id),
            )
        else:
            cursor.execute(
                """
                UPDATE usuarios
                SET nombre=?, rol=?
                WHERE id=?
                """,
                (nombre, rol, usuario_id),
            )

        conn.commit()
        conn.close()
        return redirect("/usuarios")

    cursor.execute(
        """
        SELECT id, nombre, COALESCE(rol, 'mesonera'), pin
        FROM usuarios
        WHERE id=?
        """,
        (usuario_id,),
    )
    usuario = cursor.fetchone()
    conn.close()

    if not usuario:
        return "Usuario no encontrado", 404

    pin_estado = "Configurado" if usuario[3] else "Sin configurar"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; max-width:620px; margin:auto; }}
    .card {{ background:white; padding:18px; border-radius:10px; box-shadow:var(--sombra); }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/usuarios">👥 Usuarios</a><a href="/">🏠 Inicio</a>')}
    <div class="contenido">
        <h1>✏️ Editar usuario</h1>
        <div class="card">
            <form method="post">
                <label>Nombre</label>
                <input name="nombre" value="{html_lib.escape(usuario[1] or '', quote=True)}" required>
                <label>Rol</label>
                <select name="rol" required>{opciones_roles_usuario(usuario[2] or 'mesonera')}</select>
                <label>PIN actual</label>
                <input value="{pin_estado}" disabled>
                <label>Nuevo PIN</label>
                <input name="pin" placeholder="Dejar vacio para mantener el PIN actual">
                <button type="submit">💾 Guardar</button>
            </form>
        </div>
    </div>
    </body>
    </html>
    """


@app.route("/activar_usuario/<int:usuario_id>", methods=["POST"])
def activar_usuario(usuario_id):
    if not usuario_es_master():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(activo, 1) FROM usuarios WHERE id=?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Usuario no encontrado", 404

    nuevo_activo = 0 if row[0] else 1
    cursor.execute("UPDATE usuarios SET activo=? WHERE id=?", (nuevo_activo, usuario_id))
    conn.commit()
    conn.close()
    return redirect("/usuarios")


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
    """ + estilos_base() + """
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--gris-fondo); color: var(--texto); }
    .contenedor { display: flex; padding: 14px; gap: 14px; flex-direction: column; max-width: 1280px; margin: 0 auto; }
    .panel-izq { background: var(--panel); padding: 20px; border-radius: 14px; box-shadow: var(--sombra); border: 1px solid var(--borde); }
    .panel-der { background: transparent; }
    .panel-izq h3, .panel-der h3 { margin: 0 0 14px; font-size: 16px; font-weight: 800; color: var(--texto); display: flex; align-items: center; gap: 6px; }
    input, select { width: 100%; padding: 12px 14px; margin: 5px 0 10px; border-radius: 10px; border: 1.5px solid var(--borde); font-size: 15px; box-sizing: border-box; background: var(--panel-secundario); color: var(--texto); }
    input:focus, select:focus { outline: none; border-color: var(--verde-neko); box-shadow: 0 0 0 3px rgba(61,220,132,0.12); }
    .btn-nueva-orden { width: 100%; padding: 15px; background: var(--verde-neko); color: #0F1115; border: none; border-radius: 10px; font-size: 17px; font-weight: 800; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.20); transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.1s; }
    .btn-nueva-orden:hover { background: var(--hover-neko); box-shadow: 0 8px 18px rgba(0,0,0,0.22); }
    .card { background: var(--tarjeta); color: var(--texto); padding: 16px; margin-bottom: 10px; border-radius: 12px; box-shadow: var(--sombra-suave); display: flex; flex-direction: column; gap: 10px; font-size: 16px; border: 1px solid var(--borde); border-left: 4px solid var(--borde); }
    .card.abierta { border-left-color: var(--naranja); }
    .card.en-cocina { border-left-color: var(--verde-neko); background: var(--tarjeta); }
    .card.listo { border-left-color: var(--azul); background: var(--tarjeta); }
    .estado { padding: 4px 10px; border-radius: 20px; color: white; font-size: 11px; font-weight: 800; display: inline-block; letter-spacing: 0.5px; text-transform: uppercase; }
    .btn-ver { display: block; width: 100%; text-align: center; padding: 11px; border-radius: 9px; text-decoration: none; margin-bottom: 6px; font-weight: 700; background: #1d4ed8; color: white; }
    .btn-cobrar { display: block; width: 100%; text-align: center; padding: 11px; border-radius: 9px; text-decoration: none; font-weight: 700; background: var(--verde-neko); color: #0F1115; }
    .btn-cierre-jornada { display:block; width:100%; padding:14px; background: var(--panel-secundario); color:var(--texto); text-decoration:none; text-align:center; border-radius:10px; margin-top:12px; font-size:16px; font-weight:800; box-sizing:border-box; border:1px solid var(--borde); box-shadow:var(--sombra-suave); }
    .mesonera { font-size: 13px; color: var(--texto-secundario); margin-top: 3px; }
    .seccion-titulo { font-size: 13px; font-weight: 800; color: var(--texto-secundario); letter-spacing: 1px; text-transform: uppercase; margin: 16px 0 8px; }
    .historial-item { background: var(--tarjeta); color: var(--texto); padding: 12px 14px; margin-bottom: 8px; border-radius: 10px; box-shadow: var(--sombra-suave); border: 1px solid var(--borde); display: flex; justify-content: space-between; align-items: center; }
    .historial-item a { color: var(--azul); text-decoration: none; font-weight: 700; font-size: 14px; }
    .menu-master { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .menu-card { background: var(--tarjeta); border-radius: 12px; padding: 16px 14px; text-decoration: none; color: var(--texto); font-weight: 700; font-size: 14px; display: flex; align-items: center; gap: 10px; box-shadow: var(--sombra-suave); border: 1.5px solid var(--borde); transition: background 0.15s, box-shadow 0.15s, transform 0.1s, border-color 0.15s; }
    .menu-card:hover { background:#252A32; box-shadow: 0 8px 18px rgba(0,0,0,0.22); border-color:#3C4350; transform: translateY(-1px); }
    .menu-card .mc-icon { font-size: 22px; width: 42px; height: 42px; display: flex; align-items: center; justify-content: center; border-radius: 10px; flex-shrink: 0; }
    .mc-verde, .mc-naranja, .mc-azul, .mc-morado, .mc-gris { background: var(--panel-secundario); color: var(--texto-secundario); box-shadow: inset 0 0 0 1px var(--borde); }
    @media (min-width: 900px) {
        .contenedor { flex-direction: row !important; align-items: flex-start; padding: 18px !important; }
        .panel-izq { flex: 0 0 340px; }
        .panel-der { flex: 1; }
        .card { flex-direction: row !important; justify-content: space-between; align-items: center; }
    }
    </style>
    </head>
    <body>
    """

    menu_links = '<a href="/">🏠 Inicio</a>'
    rol_actual = usuario_rol()
    if rol_actual == "master":
        menu_links += """
        <a href="/cambiar_tasa">💲 Tasa</a>
        <a href="/exportar">📤 Exportar</a>
        <a href="/cierre">📦 Cierre</a>
        <a href="/reportes">📊 Reportes</a>
        <a href="/dashboard">📈 Dashboard</a>
        <a href="/cerrar_jornada">🔒 Cerrar jornada</a>
        <a href="/menu">🍜 Menú</a>
        <a href="/inventario">📦 Inventario</a>
        <a href="/compras">🛒 Compras</a>
        <a href="/produccion">👨‍🍳 Producción</a>
        <a href="/recetas">🧾 Recetas</a>
        <a href="/movimientos_inventario">📋 Movimientos</a>
        <a href="/usuarios">👥 Usuarios</a>
        <a href="/cocina">🍳 Cocina</a>
        """
        menu_links += '<a href="/cuentas_por_cobrar">💰 Cuentas por cobrar</a>'
        menu_links += '<a href="/delivery">🛵 Delivery</a>'
    elif rol_actual == "socio":
        menu_links += '<a href="/reportes">📊 Reportes</a><a href="/dashboard">📈 Dashboard</a>'
    elif rol_actual == "mesonera_reportes":
        menu_links += '<a href="/reportes">📊 Reportes</a><a href="/dashboard">📈 Dashboard</a>'
    elif rol_actual == "cocina_reportes":
        menu_links += (
            '<a href="/cocina">🍳 Cocina</a>'
            '<a href="/produccion">👨‍🍳 Producción</a>'
            '<a href="/inventario">📦 Inventario</a>'
            '<a href="/reportes">📊 Reportes</a>'
            '<a href="/dashboard">📈 Dashboard</a>'
        )

    html += barra_superior(menu_links)

    boton_cerrar_jornada = ""
    if usuario_es_admin_cierre():
        boton_cerrar_jornada = (
            '<a href="/cerrar_jornada" class="btn-cierre-jornada">🔒 Cerrar jornada</a>'
        )

    boton_ordenes_listas = ""
    if usuario_es_master():
        boton_ordenes_listas = (
            '<a href="/ordenes_listas" class="btn-cierre-jornada">Listas por cobrar</a>'
        )

    panel_izq_extra = ""
    if rol_actual == "master":
        panel_izq_extra = """
        <div style="margin-top:20px;">
            <div class="seccion-titulo">Accesos rápidos</div>
            <div class="menu-master">
                <a href="/" class="menu-card"><div class="mc-icon mc-verde">🏠</div><span>Inicio</span></a>
                <a href="/cambiar_tasa" class="menu-card"><div class="mc-icon mc-naranja">💲</div><span>Tasa</span></a>
                <a href="/exportar" class="menu-card"><div class="mc-icon mc-azul">📤</div><span>Exportar</span></a>
                <a href="/cierre" class="menu-card"><div class="mc-icon mc-gris">📦</div><span>Cierre</span></a>
                <a href="/reportes" class="menu-card"><div class="mc-icon mc-azul">📊</div><span>Reportes</span></a>
                <a href="/dashboard" class="menu-card"><div class="mc-icon mc-verde">📈</div><span>Dashboard</span></a>
                <a href="/menu" class="menu-card"><div class="mc-icon mc-naranja">🍜</div><span>Menú</span></a>
                <a href="/inventario" class="menu-card"><div class="mc-icon mc-gris">📦</div><span>Inventario</span></a>
                <a href="/compras" class="menu-card"><div class="mc-icon mc-naranja">🛒</div><span>Compras</span></a>
                <a href="/produccion" class="menu-card"><div class="mc-icon mc-verde">👨‍🍳</div><span>Producción</span></a>
                <a href="/recetas" class="menu-card"><div class="mc-icon mc-azul">🧾</div><span>Recetas</span></a>
                <a href="/movimientos_inventario" class="menu-card"><div class="mc-icon mc-gris">📋</div><span>Movimientos</span></a>
                <a href="/usuarios" class="menu-card"><div class="mc-icon mc-morado">👥</div><span>Usuarios</span></a>
                <a href="/cocina" class="menu-card"><div class="mc-icon mc-naranja">🍳</div><span>Cocina</span></a>
            </div>
        </div>
        """
    elif rol_actual == "mesonera_reportes":
        panel_izq_extra = """
        <div style="margin-top:20px;">
            <div class="seccion-titulo">Accesos rápidos</div>
            <div class="menu-master">
                <a href="/reportes" class="menu-card"><div class="mc-icon mc-azul">📊</div><span>Reportes</span></a>
                <a href="/dashboard" class="menu-card"><div class="mc-icon mc-verde">📈</div><span>Dashboard</span></a>
            </div>
        </div>
        """
    elif rol_actual == "cocina_reportes":
        panel_izq_extra = """
        <div style="margin-top:20px;">
            <div class="seccion-titulo">Accesos rápidos</div>
            <div class="menu-master">
                <a href="/cocina" class="menu-card"><div class="mc-icon mc-naranja">🍳</div><span>Cocina</span></a>
                <a href="/produccion" class="menu-card"><div class="mc-icon mc-verde">👨‍🍳</div><span>Producción</span></a>
                <a href="/inventario" class="menu-card"><div class="mc-icon mc-gris">📦</div><span>Inventario</span></a>
                <a href="/reportes" class="menu-card"><div class="mc-icon mc-azul">📊</div><span>Reportes</span></a>
                <a href="/dashboard" class="menu-card"><div class="mc-icon mc-verde">📈</div><span>Dashboard</span></a>
            </div>
        </div>
        """

    html += f"""
    <div class="contenedor">
        <div class="panel-izq">
            <h3>🧾 Nueva orden</h3>
            <form action="/crear_orden" method="post">
                <label style="font-size:13px;font-weight:700;color:#6b7280;">Tipo</label>
                <select name="tipo">
                    <option value="Mesa">🪑 Mesa</option>
                    <option value="Delivery">🛵 Delivery</option>
                    <option value="Para llevar">🥡 Pick Up</option>
                </select>
                <label style="font-size:13px;font-weight:700;color:#6b7280;">Referencia</label>
                <input name="referencia" placeholder="Ej: Mesa 3, Juan...">
                <label style="font-size:13px;font-weight:700;color:#6b7280;">👤 Cliente</label>
                <input name="cliente" placeholder="Nombre del cliente">
                <button class="btn-nueva-orden" type="submit">➕ Crear orden</button>
            </form>
            {boton_cerrar_jornada}
            {boton_ordenes_listas}
            {panel_izq_extra}
        </div>
        <div class="panel-der">
    """

    abierta_html = ""
    cocina_html = ""
    listo_html = ""
    historial_html = ""

    for o in ordenes:
        if o[6] == "abierta":
            abierta_html += f"""
            <div class="card abierta">
                <div>
                    <b>Orden {texto_numero_orden(o[1])}</b> &nbsp; <span style="color:#6b7280;font-size:14px;">{o[3]} · {o[4]}</span><br>
                    <span style="font-size:15px;">👤 {o[5] if o[5] else '—'}</span>
                    <div class="mesonera">👩 {o[9] if o[9] else '—'}</div>
                </div>
                <div style="min-width:160px;">
                    <span class="estado" style="background:#f97316; margin-bottom:8px;">Abierta</span>
                    <a href="/orden/{o[0]}" class="btn-ver">🔍 Ver detalle</a>
                    <a href="/cobrar/{o[0]}" class="btn-cobrar" onclick="return confirm('⚠️ Esta orden aún no ha sido enviada a cocina. ¿Continuar?')">💵 Cobrar</a>
                </div>
            </div>
            """
        elif o[6] == "en cocina":
            cocina_html += f"""
            <div class="card en-cocina">
                <div>
                    <b>Orden {texto_numero_orden(o[1])}</b> &nbsp; <span style="color:#6b7280;font-size:14px;">{o[3]} · {o[4]}</span><br>
                    <span style="font-size:15px;">👤 {o[5] if o[5] else '—'}</span>
                    <div class="mesonera">👩 {o[9] if o[9] else '—'}</div>
                </div>
                <div style="min-width:160px;">
                    <span class="estado" style="background:#1a6b4a; margin-bottom:8px;">En cocina</span>
                    <a href="/orden/{o[0]}" class="btn-ver">🔍 Ver detalle</a>
                    <a href="/cobrar/{o[0]}" class="btn-cobrar">💵 Cobrar</a>
                </div>
            </div>
            """
        elif o[6] == "listo":
            listo_html += f"""
            <div class="card listo">
                <div>
                    <b>Orden {texto_numero_orden(o[1])}</b> &nbsp; <span style="color:#6b7280;font-size:14px;">{o[3]} · {o[4]}</span><br>
                    <span style="font-size:15px;">👤 {o[5] if o[5] else '—'}</span>
                    <div class="mesonera">👩 {o[9] if o[9] else '—'}</div>
                </div>
                <div style="min-width:160px;">
                    <span class="estado" style="background:#1d4ed8; margin-bottom:8px;">Lista</span>
                    <a href="/orden/{o[0]}" class="btn-ver">🔍 Ver detalle</a>
                    <a href="/cobrar/{o[0]}" class="btn-cobrar">💵 Cobrar</a>
                </div>
            </div>
            """
        elif o[6] == "cerrada":
            historial_html += f"""
            <div class="historial-item">
                <div>
                    <b>Orden {texto_numero_orden(o[1])}</b> — {o[5] if o[5] else '—'}
                    <div class="mesonera">👩 {o[9] if o[9] else '—'}</div>
                </div>
                <a href="/orden/{o[0]}">🔍 Ver</a>
            </div>
            """

    if abierta_html:
        html += f'<div class="seccion-titulo">🟠 Órdenes abiertas</div>{abierta_html}'
    if cocina_html:
        html += f'<div class="seccion-titulo">🍳 En cocina</div>{cocina_html}'
    if listo_html:
        html += f'<div class="seccion-titulo">Listas por cobrar</div>{listo_html}'
    if historial_html:
        html += f'<div class="seccion-titulo">📚 Historial del día</div>{historial_html}'
    if not abierta_html and not cocina_html and not listo_html:
        html += '<div style="text-align:center;padding:40px;color:#9ca3af;font-size:16px;">Sin órdenes activas</div>'

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
    """ + estilos_base() + """
    body { margin: 0; }
    .contenido { padding: 18px; max-width: 960px; margin: 0 auto; }
    .card { background: var(--tarjeta); color: var(--texto); padding: 20px; margin-bottom: 14px; border-radius: 14px; box-shadow: var(--sombra-suave); border: 1px solid var(--borde); }
    .card h3 { margin: 0 0 14px; font-size: 16px; color: var(--texto); }
    input, select { width: 100%; padding: 12px 14px; margin: 6px 0 10px; border-radius: 10px; border: 1.5px solid var(--borde); font-size: 15px; box-sizing: border-box; background: var(--panel-secundario); color: var(--texto); }
    .btn-add { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 10px; background: var(--verde-neko); color: #0F1115; cursor: pointer; font-weight: 800; box-shadow: 0 4px 12px rgba(0,0,0,0.20); }
    .productos-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
    .producto { background: var(--tarjeta); color: var(--texto); padding: 14px 16px; border-radius: 12px; border: 1.5px solid var(--borde); box-shadow: var(--sombra-suave); transition:background 0.16s ease, border-color 0.16s ease, transform 0.1s ease; }
    .producto:hover { background:#252A32; border-color:rgba(61,220,132,0.38); transform:translateY(-1px); }
    .producto-nombre { font-size: 16px; font-weight: 700; color: var(--texto); margin-bottom: 2px; }
    .producto-precio { font-size: 20px; font-weight: 800; color: var(--texto-secundario); margin-bottom: 4px; }
    .producto-cat { font-size: 12px; color: var(--texto-secundario); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; background: var(--panel-secundario); display: inline-block; padding: 2px 8px; border-radius: 20px; margin-bottom: 10px; border:1px solid var(--borde); }
    .acciones { display: flex; gap: 8px; }
    .acciones a { text-decoration: none; color: white; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: 700; flex: 1; text-align: center; }
    .editar { background: var(--azul); }
    .eliminar { background: var(--rojo); }
    .page-title { font-size: 22px; font-weight: 900; color: var(--texto); margin: 0 0 18px; display: flex; align-items: center; gap: 8px; }
    </style>
    </head>
    <body>
    """

    html += barra_superior('<a href="/">🏠 Inicio</a>')
    html += """
    <div class="contenido">
    <div class="page-title">🍜 Menú Neko Wok</div>
    <div class="card">
        <h3>➕ Agregar producto</h3>
        <form method="post">
            <input name="nombre" placeholder="Nombre del producto" required>
            <input name="precio" type="number" step="0.01" placeholder="Precio USD" required>
            <select name="categoria">
    """

    for c in categorias:
        html += f"<option value='{c[0]}'>{c[1]}</option>"

    html += """
            </select>
            <button class="btn-add">➕ Agregar producto</button>
        </form>
    </div>
    <div class="page-title" style="font-size:18px; margin-bottom:12px;">🍽️ Productos</div>
    <div class="productos-grid">
    """

    for p in productos:
        html += f"""
        <div class="producto">
            <div class="producto-nombre">{p[1]}</div>
            <div class="producto-precio">${p[2]}</div>
            <div class="producto-cat">{p[3] if p[3] else 'Sin categoría'}</div>
            <div class="acciones">
                <a class="editar" href="/editar_producto/{p[0]}">✏️ Editar</a>
                <a class="eliminar" href="/eliminar_producto/{p[0]}">🗑️ Eliminar</a>
            </div>
        </div>
        """

    html += """
    </div>
    <a href="/" class="volver" style="display:inline-block;margin-top:18px;padding:12px 16px;background:#1a6b4a;color:white;text-decoration:none;border-radius:10px;font-weight:700;">🏠 Volver al inicio</a>
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
        SELECT nombre, stock_actual, unidad, costo_promedio
        FROM inventario
        ORDER BY nombre ASC
        """
    )
    productos = cursor.fetchall()
    valor_total_inventario = sum(a_float(p[1]) * a_float(p[3]) for p in productos)
    conn.close()

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    """ + estilos_base() + """
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--gris-fondo); color: var(--texto); }
    .contenido { padding: 14px; max-width: 960px; margin: 0 auto; }
    .card { background: var(--tarjeta); color: var(--texto); padding: 18px; margin-bottom: 12px; border-radius: 14px; box-shadow: var(--sombra-suave); border: 1px solid var(--borde); }
    .accesos { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
    .btn-acceso { display: block; text-align: center; padding: 16px; background: var(--panel-secundario); color: var(--texto); text-decoration: none; border-radius: 12px; font-size: 16px; font-weight: 800; box-shadow: var(--sombra-suave); border:1px solid var(--borde); transition:background 0.16s ease, border-color 0.16s ease; }
    .btn-acceso:hover { background:#252A32; border-color:#3C4350; box-shadow:0 8px 18px rgba(0,0,0,0.22); }
    .resumen-inventario { background: var(--panel-secundario); border-left: 5px solid var(--verde-neko); padding: 14px; border-radius: 10px; margin-bottom: 12px; font-size: 17px; font-weight: 700; }
    .volver { display: inline-block; text-align: center; margin-top: 14px; padding: 12px 16px; background: var(--panel-secundario); color: var(--texto); text-decoration: none; border-radius: 10px; font-weight: 700; border:1px solid var(--borde); }
    @media (max-width: 768px) { .accesos { grid-template-columns: 1fr; } }
    </style>
    </head>
    <body>
    """

    produccion_link = ""
    if usuario_es_admin_cierre():
        produccion_link = (
            '<a href="/produccion">👨‍🍳 Producción</a>'
            '<a href="/recetas">🧾 Recetas</a>'
            '<a href="/movimientos_inventario">📋 Movimientos</a>'
        )
    inventario_links = '<a href="/cocina">🍳 Cocina</a>'
    if usuario_es_master():
        inventario_links = '<a href="/">🏠 Inicio</a><a href="/compras">🛒 Compras</a>'
    html += barra_superior(
        f'{inventario_links}{produccion_link}'
    )
    html += """
    <div class="contenido">
        <h1>📦 Inventario</h1>
        <div class="accesos">
            <a href="/productos_base" class="btn-acceso">📦 Productos base</a>
            <a href="/proveedores" class="btn-acceso">🤝 Proveedores</a>
        </div>
        <div class="resumen-inventario">Valor total inventario: $ {round(valor_total_inventario, 2)}</div>
    """

    if not productos:
        html += """
        <div class="card">
            No hay productos registrados en inventario.
        </div>
        """
    else:
        for producto in productos:
            stock_actual = a_float(producto[1])
            costo_promedio = a_float(producto[3])
            valor_total = stock_actual * costo_promedio
            html += f"""
            <div class="card">
                <b>{producto[0]}</b><br>
                Stock actual: {round(stock_actual, 2)}<br>
                Unidad: {producto[2] if producto[2] else '-'}<br>
                Costo promedio: $ {round(costo_promedio, 4)}<br>
                Valor total: $ {round(valor_total, 2)}
            </div>
            """

    html += """
        <a href="/" class="volver">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


@app.route("/recetas", methods=["GET", "POST"])
def recetas():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    error = ""

    if request.method == "POST":
        producto_menu = (request.form.get("producto_menu") or "").strip()
        insumo = (request.form.get("insumo") or "").strip()
        cantidad = a_float(request.form.get("cantidad"))
        unidad = (request.form.get("unidad") or "").strip()

        if not producto_menu or not insumo or cantidad <= 0:
            error = "Debes seleccionar producto, insumo y cantidad valida"
        else:
            cursor.execute(
                """
                INSERT INTO recetas (producto_menu, insumo, cantidad, unidad)
                VALUES (?, ?, ?, ?)
                """,
                (producto_menu, insumo, cantidad, unidad),
            )
            conn.commit()
            conn.close()
            return redirect("/recetas")

    cursor.execute(
        """
        SELECT nombre
        FROM productos
        ORDER BY nombre ASC
        """
    )
    productos_menu = cursor.fetchall()

    cursor.execute(
        """
        SELECT nombre, unidad
        FROM inventario
        ORDER BY nombre ASC
        """
    )
    insumos = cursor.fetchall()

    cursor.execute(
        """
        SELECT id, producto_menu, insumo, cantidad, unidad
        FROM recetas
        ORDER BY producto_menu ASC, insumo ASC, id ASC
        """
    )
    recetas_db = cursor.fetchall()
    conn.close()

    recetas_html = ""
    producto_actual = None
    for receta in recetas_db:
        if receta[1] != producto_actual:
            if producto_actual is not None:
                recetas_html += "</tbody></table></div>"
            producto_actual = receta[1]
            recetas_html += f"""
            <div class="card">
                <h3>{html_lib.escape(producto_actual)}</h3>
                <table>
                    <thead>
                        <tr><th>Insumo</th><th>Cantidad</th><th>Unidad</th><th>Accion</th></tr>
                    </thead>
                    <tbody>
            """

        recetas_html += f"""
            <tr>
                <td>{html_lib.escape(receta[2])}</td>
                <td>{round(a_float(receta[3]), 4)}</td>
                <td>{html_lib.escape(receta[4] or '')}</td>
                <td><a class="btn-eliminar" href="/eliminar_receta/{receta[0]}" onclick="return confirm('Eliminar esta linea de receta?')">🗑️ Eliminar</a></td>
            </tr>
        """

    if producto_actual is not None:
        recetas_html += "</tbody></table></div>"
    else:
        recetas_html = '<div class="card">No hay recetas configuradas.</div>'

    opciones_productos = "".join(
        f"<option value='{html_lib.escape(p[0], quote=True)}'>{html_lib.escape(p[0])}</option>"
        for p in productos_menu
    )
    opciones_insumos = "".join(
        f"<option value='{html_lib.escape(i[0], quote=True)}' data-unidad='{html_lib.escape(i[1] or '', quote=True)}'>{html_lib.escape(i[0])}</option>"
        for i in insumos
    )

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; max-width:1100px; margin:auto; }}
    .card {{ background:white; padding:18px; border-radius:10px; margin-bottom:14px; box-shadow:var(--sombra); }}
    .grid-form {{ display:grid; grid-template-columns:2fr 2fr 1fr 1fr auto; gap:10px; align-items:end; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid #e5e7eb; padding:10px; text-align:left; }}
    th {{ background:#f0fdf4; color:#1a6b4a; font-weight:800; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
    .btn-eliminar {{ background:#c0392b; color:white; padding:8px 10px; border-radius:6px; text-decoration:none; font-weight:bold; }}
    .error {{ background:#fdecea; color:#c0392b; padding:10px; border-radius:6px; margin-bottom:10px; }}
    @media (max-width: 768px) {{ .grid-form {{ grid-template-columns:1fr; }} }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">🏠 Inicio</a><a href="/inventario">📦 Inventario</a><a href="/movimientos_inventario">📋 Movimientos</a>')}
    <div class="contenido">
        <h1>🧾 Recetas de inventario</h1>
        <div class="card">
            {"<div class='error'>" + error + "</div>" if error else ""}
            <form method="post">
                <div class="grid-form">
                    <div>
                        <label>Producto del menu</label>
                        <select name="producto_menu" required>
                            <option value="">Seleccione producto</option>
                            {opciones_productos}
                        </select>
                    </div>
                    <div>
                        <label>Insumo de inventario</label>
                        <select id="insumo" name="insumo" required>
                            <option value="">Seleccione insumo</option>
                            {opciones_insumos}
                        </select>
                    </div>
                    <div>
                        <label>Cantidad</label>
                        <input name="cantidad" type="number" step="0.0001" min="0.0001" required>
                    </div>
                    <div>
                        <label>Unidad</label>
                        <input id="unidad" name="unidad">
                    </div>
                    <button type="submit">💾 Guardar</button>
                </div>
            </form>
        </div>
        {recetas_html}
    </div>
    <script>
    const insumo = document.getElementById("insumo");
    const unidad = document.getElementById("unidad");
    if (insumo && unidad) {{
        insumo.addEventListener("change", function() {{
            const selected = insumo.options[insumo.selectedIndex];
            unidad.value = selected ? (selected.dataset.unidad || "") : "";
        }});
    }}
    </script>
    </body>
    </html>
    """


@app.route("/eliminar_receta/<int:receta_id>")
def eliminar_receta(receta_id):
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recetas WHERE id=?", (receta_id,))
    conn.commit()
    conn.close()
    return redirect("/recetas")


@app.route("/movimientos_inventario")
def movimientos_inventario():
    if not usuario_es_admin_cierre():
        return "Acceso denegado", 403

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fecha, producto, tipo, cantidad, stock_anterior, stock_nuevo,
               referencia, usuario, observacion
        FROM movimientos_inventario
        ORDER BY id DESC
        LIMIT 300
        """
    )
    movimientos = cursor.fetchall()
    conn.close()

    filas = ""
    for mov in movimientos:
        filas += f"""
        <tr>
            <td>{html_lib.escape(mov[0] or '')}</td>
            <td>{html_lib.escape(mov[1] or '')}</td>
            <td>{html_lib.escape(mov[2] or '')}</td>
            <td>{round(a_float(mov[3]), 4)}</td>
            <td>{round(a_float(mov[4]), 4)}</td>
            <td>{round(a_float(mov[5]), 4)}</td>
            <td>{html_lib.escape(mov[6] or '')}</td>
            <td>{html_lib.escape(mov[7] or '')}</td>
            <td>{html_lib.escape(mov[8] or '')}</td>
        </tr>
        """

    if not filas:
        filas = '<tr><td colspan="9">No hay movimientos registrados.</td></tr>'

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; }}
    .card {{ background:white; padding:18px; border-radius:10px; box-shadow:var(--sombra); overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:900px; }}
    th, td {{ border-bottom:1px solid #e5e7eb; padding:10px; text-align:left; }}
    th {{ background:#f0fdf4; color:#1a6b4a; font-weight:800; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">🏠 Inicio</a><a href="/inventario">📦 Inventario</a><a href="/recetas">🧾 Recetas</a>')}
    <div class="contenido">
        <h1>📋 Movimientos de inventario</h1>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Fecha</th><th>Producto</th><th>Tipo</th><th>Cantidad</th>
                        <th>Stock anterior</th><th>Stock nuevo</th><th>Referencia</th>
                        <th>Usuario</th><th>Observacion</th>
                    </tr>
                </thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
    </div>
    </body>
    </html>
    """


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

            cantidad = a_float(request.form.get("cantidad"))
            precio_total = a_float(request.form.get("precio_total"))

            if producto_base_id == "" or cantidad <= 0 or precio_total <= 0:
                error = "Debes seleccionar un producto, cantidad y precio total validos"
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
                                "precio_total": precio_total,
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
                            item.get("precio_total", 0),
                            item["proveedor"],
                            fecha,
                            usuario_id,
                        ),
                    )

                    sumar_inventario_con_costo(
                        cursor,
                        item["producto"],
                        item["cantidad"],
                        item["unidad"],
                        item.get("precio_total", 0),
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
    .grid-form { display: grid; grid-template-columns: 2fr 1fr 1fr 2fr; gap: 10px; align-items: end; }
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

    produccion_link = '<a href="/produccion">👨‍🍳 Producción</a>' if usuario_es_admin_cierre() else ""
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

    if not productos_base:
        html += """
            Debes registrar al menos un producto base antes de cargar compras.
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
                        <label>Precio total</label>
                        <input name="precio_total" type="number" step="0.01" min="0.01" placeholder="0.00" required>
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
            precio_total = a_float(compra.get("precio_total"))
            html += f"""
            <div class="item-lista">
                <div class="detalle-item">
                    <b>{compra["producto"]}</b><br>
                    {round(compra["cantidad"] or 0, 2)} {compra["unidad"]}
                    <small>Precio total: $ {round(precio_total, 2)} | Costo unitario: $ {round((precio_total / a_float(compra["cantidad"])) if a_float(compra["cantidad"]) else 0, 4)} | Proveedor: {compra["proveedor"] if compra["proveedor"] else 'Sin proveedor'}</small>
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
                Costo unitario: ${round((a_float(compra[2]) / a_float(compra[1])) if a_float(compra[1]) else 0, 4)}<br>
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
        SELECT id, nombre, unidad, stock_actual, costo_promedio
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
        cantidad_origen = a_float(request.form.get("cantidad_origen"))
        cantidad_resultado = a_float(request.form.get("cantidad_resultado"))
        porciones_total, porciones_detalle = parsear_porciones_detalle(
            request.form.get("porciones_detalle", "")
        )
        costo_insumos_extra, insumos_extra = parsear_insumos_extra(
            request.form.get("insumos_extra", "")
        )

        if cantidad_resultado <= 0 and porciones_total > 0:
            cantidad_resultado = porciones_total

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
                SELECT id, nombre, stock_actual, unidad, costo_promedio
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
            elif cantidad_resultado > cantidad_origen:
                error = "La cantidad resultado no puede ser mayor que la cantidad origen"
            else:
                producto_origen = origen[1]
                producto_resultado = resultado_base[1]
                unidad_resultado = resultado_base[2] if resultado_base[2] else "unidad"
                costo_promedio_origen = a_float(origen[4])
                costo_total = (costo_promedio_origen * cantidad_origen) + costo_insumos_extra
                costo_unitario_resultado = (
                    costo_total / cantidad_resultado if cantidad_resultado > 0 else 0
                )
                merma = cantidad_origen - cantidad_resultado
                porcentaje_merma = (merma / cantidad_origen * 100) if cantidad_origen else 0.0
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

                sumar_inventario_con_costo(
                    cursor,
                    producto_resultado,
                    cantidad_resultado,
                    unidad_resultado,
                    costo_total,
                )

                cursor.execute(
                    """
                    INSERT INTO producciones (
                        producto_origen, cantidad_origen, producto_resultado,
                        cantidad_resultado, costo_total, fecha, usuario_id,
                        merma, porcentaje_merma, costo_unitario_resultado,
                        insumos_extra, costo_insumos_extra, porciones_detalle
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        producto_origen,
                        cantidad_origen,
                        producto_resultado,
                        cantidad_resultado,
                        costo_total,
                        fecha,
                        usuario_id,
                        merma,
                        porcentaje_merma,
                        costo_unitario_resultado,
                        insumos_extra,
                        costo_insumos_extra,
                        porciones_detalle,
                    ),
                )

                conn.commit()
                conn.close()
                if usuario_es_produccion():
                    return redirect("/produccion")
                return redirect("/inventario")

    cursor.execute(
        """
        SELECT producto_origen, cantidad_origen, producto_resultado, cantidad_resultado,
               costo_total, fecha, COALESCE(merma, 0), COALESCE(porcentaje_merma, 0),
               COALESCE(costo_unitario_resultado, 0), COALESCE(insumos_extra, ''),
               COALESCE(costo_insumos_extra, 0), COALESCE(porciones_detalle, '')
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
    """ + estilos_base() + """
    body { font-family: Arial; margin: 0; background: var(--gris-fondo); color: var(--texto); }
    .contenido { padding: 10px; }
    .card { background: var(--tarjeta); color: var(--texto); padding: 15px; margin-bottom: 10px; border-radius: 10px; box-shadow: var(--sombra-suave); border: 1px solid var(--borde); }
    input, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 8px; border: 1px solid var(--borde); font-size: 16px; box-sizing: border-box; background: var(--panel-secundario); color: var(--texto); }
    button { width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 8px; background: var(--verde-neko); color: #0F1115; cursor: pointer; }
    .error { background: #fdecea; color: #c0392b; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
    .grid-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    textarea { width: 100%; min-height: 90px; padding: 12px; margin: 5px 0; border-radius: 8px; border: 1px solid var(--borde); font-size: 16px; box-sizing: border-box; background: var(--panel-secundario); color: var(--texto); }
    .ayuda { color:var(--texto-secundario); font-size:13px; margin:2px 0 8px; }
    .volver { display: block; text-align: center; margin-top: 15px; padding: 12px; background: var(--panel-secundario); color: var(--texto); text-decoration: none; border-radius: 8px; border: 1px solid var(--borde); }
    @media (max-width: 768px) { .grid-form { grid-template-columns: 1fr; } }
    </style>
    </head>
    <body>
    """

    produccion_links = ""
    if usuario_es_master():
        produccion_links = '<a href="/">🏠 Inicio</a><a href="/inventario">📦 Inventario</a><a href="/compras">🛒 Compras</a>'
    elif not usuario_es_produccion():
        produccion_links = '<a href="/cocina">🍳 Cocina</a><a href="/inventario">📦 Inventario</a>'

    html += barra_superior(produccion_links)
    html += """
    <div class="contenido">
        <h1>👨‍🍳 Producción</h1>
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
                <label>Cantidad origen</label>
                <input name="cantidad_origen" type="number" step="0.01" min="0.01" placeholder="Cantidad origen" required>
                <label>Cantidad resultado</label>
                <input name="cantidad_resultado" type="number" step="0.01" min="0" placeholder="Cantidad resultado">
                <div class="ayuda">Puedes dejar cantidad resultado en blanco si cargas porciones abajo.</div>
                <label>Porciones producidas</label>
                <textarea name="porciones_detalle" placeholder="Ejemplo:&#10;19 bolsas de 2 kg&#10;1 bolsa de 1 kg"></textarea>
                <div class="ayuda">El sistema suma cantidad x tamano de cada linea para calcular el resultado.</div>
                <label>Insumos extra opcionales</label>
                <textarea name="insumos_extra" placeholder="Ejemplo:&#10;Vinagre, 1.50&#10;Anis, 0.80&#10;Colorante, 0.40"></textarea>
                <div class="ayuda">Se suma el ultimo numero de cada linea al costo total de produccion.</div>
                <button type="submit">👨‍🍳 Registrar producción</button>
            </form>
        </div>
        <h2>👨‍🍳 Ultimas producciones</h2>
    """

    if not historial:
        html += """
        <div class="card">
            No hay producciones registradas.
        </div>
        """
    else:
        for prod in historial:
            costo_unitario = a_float(prod[8]) or ((float(prod[4] or 0) / float(prod[3])) if prod[3] else 0)
            porciones_html = ""
            if prod[11]:
                porciones_html = f"<br>Porciones:<br><pre style='white-space:pre-wrap; margin:6px 0;'>{html_lib.escape(prod[11])}</pre>"
            insumos_html = ""
            if prod[9]:
                insumos_html = f"<br>Insumos extra: $ {round(prod[10] or 0, 2)}<br><pre style='white-space:pre-wrap; margin:6px 0;'>{html_lib.escape(prod[9])}</pre>"
            html += f"""
            <div class="card">
                <b>{prod[0]}</b> -> <b>{prod[2]}</b><br>
                Origen: {round(prod[1] or 0, 2)}<br>
                Resultado: {round(prod[3] or 0, 2)}<br>
                Merma: {round(prod[6] or 0, 2)} ({round(prod[7] or 0, 2)}%)<br>
                Costo total: ${round(prod[4] or 0, 2)}<br>
                Costo unitario resultado: ${round(costo_unitario, 4)}<br>
                Fecha: {prod[5]}
                {porciones_html}
                {insumos_html}
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
    <h1>✏️ Editar producto</h1>
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
        <button>💾 Guardar</button>
    </form>
    <a href="/menu">🏠 Volver</a>
    </div>
    </body>
    </html>
    """
    return html


def delivery_estado_badge(activo):
    if int(activo or 0) == 1:
        return '<span class="badge-estado estado-pagada">Activo</span>'
    return '<span class="badge-estado estado-anulada">Inactivo</span>'


@app.route("/delivery")
def delivery_admin():
    conn = get_connection()
    cursor = conn.cursor()
    resumen = resumen_delivery_admin(cursor)
    repartidores_resumen = resumen_delivery_por_repartidor(cursor)
    conn.close()

    filas = ""
    for row in repartidores_resumen:
        repartidor_id, nombre, activo, servicios, generado, pagado, pendiente = row
        filas += f"""
        <tr>
            <td><b>{html_lib.escape(nombre or '')}</b></td>
            <td class="monto">{int(servicios or 0)}</td>
            <td class="monto">{formato_usd(generado)}</td>
            <td class="monto">{formato_usd(pagado)}</td>
            <td class="monto">{formato_usd(pendiente)}</td>
            <td>{delivery_estado_badge(activo)}</td>
            <td><a class="btn-mini" href="/delivery/repartidor/{repartidor_id}">Ver</a></td>
        </tr>
        """

    if not filas:
        filas = '<tr><td colspan="7">No hay repartidores ni movimientos de delivery registrados.</td></tr>'

    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>🛵 Delivery</h1>
        <div class="metricas">
            <div class="metrica"><small>Delivery generado</small><b>{formato_usd(resumen["generado"])}</b></div>
            <div class="metrica"><small>Delivery pagado</small><b>{formato_usd(resumen["pagado"])}</b></div>
            <div class="metrica"><small>Pendiente actual</small><b>{formato_usd(resumen["pendiente"])}</b></div>
            <div class="metrica"><small>Cantidad de servicios</small><b>{resumen["servicios"]}</b></div>
        </div>
        <div class="card-admin">
            <div class="acciones" style="margin-bottom:12px;">
                <a class="btn-mini" href="/repartidores/nuevo">Nuevo repartidor</a>
                <a class="btn-mini btn-sec" href="/repartidores">Administrar repartidores</a>
            </div>
            <h2>Repartidores</h2>
            <table>
                <thead><tr><th>Repartidor</th><th>Servicios</th><th>Generado</th><th>Pagado</th><th>Pendiente</th><th>Estado</th><th>Accion</th></tr></thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
    </div></body></html>
    """


@app.route("/delivery/repartidor/<int:repartidor_id>")
def delivery_repartidor_detalle(repartidor_id):
    conn = get_connection()
    cursor = conn.cursor()
    detalle = detalle_delivery_repartidor(cursor, repartidor_id)
    conn.close()

    if not detalle:
        return "Repartidor no encontrado", 404

    repartidor = detalle["repartidor"]
    resumen = detalle["resumen"]
    movimientos_html = ""
    for mov in detalle["movimientos"]:
        fecha, tipo, orden_id, orden_existente_id, numero_orden, monto, referencia, usuario, observacion = mov
        orden_texto = "-"
        if orden_id:
            orden_label = html_lib.escape(str(numero_orden or orden_id))
            orden_texto = (
                f'<a href="/orden/{orden_existente_id}">#{orden_label}</a>'
                if orden_existente_id
                else f"#{html_lib.escape(str(orden_id))}"
            )
        signo = "+" if a_float(monto) > 0 else ""
        movimientos_html += f"""
        <tr>
            <td>{texto_fecha_corta(fecha)}</td>
            <td>{html_lib.escape(tipo or '')}</td>
            <td>{orden_texto}</td>
            <td class="monto">{signo}{formato_usd(monto)}</td>
            <td>{html_lib.escape(referencia or '-')}</td>
            <td>{html_lib.escape(usuario or '-')}</td>
            <td>{html_lib.escape(observacion or '-')}</td>
        </tr>
        """

    if not movimientos_html:
        movimientos_html = '<tr><td colspan="7">Este repartidor no tiene movimientos de delivery.</td></tr>'

    formulario_pago = ""
    if resumen["pendiente"] > TOLERANCIA_COBRO:
        formulario_pago = f"""
        <div class="card-admin">
            <h2>Registrar pago</h2>
            <form method="post" action="/delivery/repartidor/{repartidor[0]}/pago" class="form-grid">
                <div><label>Monto USD</label><input name="monto_usd" type="number" min="0.01" step="0.01" required></div>
                <div><label>Referencia</label><input name="referencia" maxlength="120"></div>
                <div class="full"><label>Observacion</label><textarea name="observacion" maxlength="500"></textarea></div>
                <div class="acciones full">
                    <button type="submit">Registrar pago</button>
                </div>
            </form>
        </div>
        """
    else:
        formulario_pago = """
        <div class="card-admin">
            <h2>Registrar pago</h2>
            <p>No hay saldo pendiente para pagar.</p>
        </div>
        """

    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
    <body>
    {barra_superior('<a href="/delivery">Delivery</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>🛵 Delivery</h1>
        <div class="card-admin">
            <h2>{html_lib.escape(repartidor[1] or '')}</h2>
            <p><b>Telefono:</b> {html_lib.escape(repartidor[2] or '-')}</p>
            <p><b>Estado:</b> {delivery_estado_badge(repartidor[4])}</p>
            <div class="acciones" style="margin-top:12px;">
                <a class="btn-mini btn-sec" href="/delivery">Volver a Delivery</a>
                <a class="btn-mini" href="/repartidores/{repartidor[0]}/editar">Editar repartidor</a>
            </div>
        </div>
        <div class="metricas">
            <div class="metrica"><small>Servicios</small><b>{resumen["servicios"]}</b></div>
            <div class="metrica"><small>Generado</small><b>{formato_usd(resumen["generado"])}</b></div>
            <div class="metrica"><small>Pagado</small><b>{formato_usd(resumen["pagado"])}</b></div>
            <div class="metrica"><small>Ajustes netos</small><b>{formato_usd(resumen["ajustes_netos"])}</b></div>
            <div class="metrica"><small>Pendiente actual</small><b>{formato_usd(resumen["pendiente"])}</b></div>
        </div>
        {formulario_pago}
        <div class="card-admin">
            <h2>Historial de movimientos</h2>
            <table>
                <thead><tr><th>Fecha</th><th>Tipo</th><th>Orden</th><th>Monto</th><th>Referencia</th><th>Usuario</th><th>Observacion</th></tr></thead>
                <tbody>{movimientos_html}</tbody>
            </table>
        </div>
    </div></body></html>
    """


@app.route("/delivery/repartidor/<int:repartidor_id>/pago", methods=["POST"])
def registrar_pago_delivery(repartidor_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        registrar_pago_delivery_repartidor(
            cursor,
            repartidor_id,
            request.form.get("monto_usd"),
            request.form.get("referencia"),
            request.form.get("observacion"),
            session.get("usuario_id"),
        )
        conn.commit()
    except ValueError as exc:
        conn.rollback()
        conn.close()
        return str(exc), 400
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return redirect(f"/delivery/repartidor/{repartidor_id}")


@app.route("/repartidores")
def repartidores():
    conn = get_connection()
    cursor = conn.cursor()
    repartidores_db = listar_repartidores(cursor)
    conn.close()

    filas = ""
    for rep in repartidores_db:
        rep_id, nombre, telefono, notas, activo, fecha = rep
        estado = "Activo" if int(activo or 0) == 1 else "Inactivo"
        texto_accion = "Desactivar" if int(activo or 0) == 1 else "Activar"
        filas += f"""
        <tr>
            <td>{html_lib.escape(nombre)}</td>
            <td>{html_lib.escape(telefono or '-')}</td>
            <td>{html_lib.escape(notas or '-')}</td>
            <td>{estado}</td>
            <td>{html_lib.escape(fecha or '-')}</td>
            <td>
                <a class="btn-mini" href="/repartidores/{rep_id}/editar">Editar</a>
                <form method="post" action="/repartidores/{rep_id}/activar" style="display:inline;">
                    <button class="btn-mini btn-sec" type="submit">{texto_accion}</button>
                </form>
            </td>
        </tr>
        """

    if not filas:
        filas = '<tr><td colspan="6">No hay repartidores registrados.</td></tr>'

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; max-width:980px; margin:0 auto; }}
    .panel-admin {{ background:var(--tarjeta); border:1px solid var(--borde); border-radius:12px; padding:18px; box-shadow:var(--sombra-suave); }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:11px; border-bottom:1px solid var(--borde); text-align:left; }}
    .btn-mini {{ display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:8px 11px; border-radius:8px; background:var(--verde-neko); color:#0F1115; text-decoration:none; font-weight:800; border:none; cursor:pointer; }}
    .btn-sec {{ background:var(--panel-secundario); color:var(--texto); border:1px solid var(--borde); }}
    .acciones {{ display:flex; gap:8px; margin-bottom:14px; }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">Inicio</a><a href="/menu">Menú</a>')}
    <div class="contenido">
        <h1>🛵 Delivery</h1>
        <h2>Repartidores</h2>
        <div class="acciones">
            <a class="btn-mini btn-sec" href="/delivery">Resumen delivery</a>
            <a class="btn-mini" href="/repartidores/nuevo">Nuevo repartidor</a>
        </div>
        <div class="panel-admin">
            <table>
                <thead><tr><th>Nombre</th><th>Teléfono</th><th>Notas</th><th>Estado</th><th>Creado</th><th>Acciones</th></tr></thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
    </div>
    </body>
    </html>
    """


@app.route("/repartidores/nuevo", methods=["GET", "POST"])
def nuevo_repartidor():
    error = ""
    nombre_val = ""
    telefono_val = ""
    notas_val = ""

    if request.method == "POST":
        nombre_val = (request.form.get("nombre") or "").strip()
        telefono_val = (request.form.get("telefono") or "").strip()
        notas_val = (request.form.get("notas") or "").strip()
        conn = get_connection()
        cursor = conn.cursor()
        try:
            crear_repartidor(cursor, nombre_val, telefono_val, notas_val, 1)
            conn.commit()
            conn.close()
            return redirect("/repartidores")
        except ValueError as exc:
            conn.rollback()
            conn.close()
            error = str(exc)

    return formulario_repartidor("Nuevo repartidor", "/repartidores/nuevo", nombre_val, telefono_val, notas_val, error)


@app.route("/repartidores/<int:repartidor_id>/editar", methods=["GET", "POST"])
def editar_repartidor(repartidor_id):
    conn = get_connection()
    cursor = conn.cursor()
    rep = obtener_repartidor(cursor, repartidor_id)
    if not rep:
        conn.close()
        return "Repartidor no encontrado", 404

    error = ""
    nombre_val = rep[1]
    telefono_val = rep[2]
    notas_val = rep[3]

    if request.method == "POST":
        nombre_val = (request.form.get("nombre") or "").strip()
        telefono_val = (request.form.get("telefono") or "").strip()
        notas_val = (request.form.get("notas") or "").strip()
        try:
            cursor.execute(
                """
                UPDATE repartidores
                SET nombre=?, telefono=?, notas=?
                WHERE id=?
                """,
                (
                    normalizar_nombre_repartidor(nombre_val),
                    telefono_val[:80],
                    notas_val[:500],
                    repartidor_id,
                ),
            )
            conn.commit()
            conn.close()
            return redirect("/repartidores")
        except ValueError as exc:
            conn.rollback()
            error = str(exc)

    conn.close()
    return formulario_repartidor(
        "Editar repartidor",
        f"/repartidores/{repartidor_id}/editar",
        nombre_val,
        telefono_val,
        notas_val,
        error,
    )


def formulario_repartidor(titulo, action, nombre, telefono, notas, error=""):
    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; max-width:620px; margin:0 auto; }}
    .panel-admin {{ background:var(--tarjeta); border:1px solid var(--borde); border-radius:12px; padding:18px; box-shadow:var(--sombra-suave); }}
    input, textarea {{ width:100%; margin:6px 0 12px; }}
    .btn-form {{ width:100%; border:none; background:var(--verde-neko); color:#0F1115; padding:13px; border-radius:10px; font-weight:900; }}
    .error {{ background:#3b1616; color:#fecaca; border:1px solid #7f1d1d; padding:10px; border-radius:8px; margin-bottom:12px; }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/repartidores">Repartidores</a><a href="/">Inicio</a>')}
    <div class="contenido">
        <h1>{html_lib.escape(titulo)}</h1>
        <div class="panel-admin">
            {"<div class='error'>" + html_lib.escape(error) + "</div>" if error else ""}
            <form method="post" action="{html_lib.escape(action, quote=True)}">
                <label>Nombre</label>
                <input name="nombre" value="{html_lib.escape(nombre or '', quote=True)}" required>
                <label>Teléfono</label>
                <input name="telefono" value="{html_lib.escape(telefono or '', quote=True)}">
                <label>Notas</label>
                <textarea name="notas">{html_lib.escape(notas or '')}</textarea>
                <button class="btn-form" type="submit">Guardar</button>
            </form>
        </div>
    </div>
    </body>
    </html>
    """


@app.route("/repartidores/<int:repartidor_id>/activar", methods=["POST"])
def activar_repartidor(repartidor_id):
    conn = get_connection()
    cursor = conn.cursor()
    rep = obtener_repartidor(cursor, repartidor_id)
    if not rep:
        conn.close()
        return "Repartidor no encontrado", 404
    nuevo_estado = 0 if int(rep[4] or 0) == 1 else 1
    cursor.execute("UPDATE repartidores SET activo=? WHERE id=?", (nuevo_estado, repartidor_id))
    conn.commit()
    conn.close()
    return redirect("/repartidores")


@app.route("/api/repartidores", methods=["GET", "POST"])
def api_repartidores():
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            repartidor_id = crear_repartidor(
                cursor,
                data.get("nombre"),
                data.get("telefono", ""),
                data.get("notas", ""),
                1,
            )
            conn.commit()
            repartidor = obtener_repartidor(cursor, repartidor_id)
            conn.close()
            return jsonify({"ok": True, "repartidor": repartidor_json_desde_fila(repartidor)})
        except ValueError as exc:
            conn.rollback()
            conn.close()
            return jsonify({"ok": False, "error": str(exc)}), 400

    repartidores_activos = [
        repartidor_json_desde_fila(rep)
        for rep in listar_repartidores(cursor, solo_activos=True)
    ]
    conn.close()
    return jsonify({"ok": True, "repartidores": repartidores_activos})


def repartidor_json_desde_fila(rep):
    return {
        "id": rep[0],
        "nombre": rep[1] or "",
        "telefono": rep[2] or "",
        "notas": rep[3] or "",
        "activo": int(rep[4] or 0),
    }


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
               o.estado, o.observacion, o.descuento, u.nombre, o.cierre_id,
               o.delivery_usd, o.delivery_repartidor_id
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
        WHERE COALESCE(p.activo, 1) = 1
          AND COALESCE(c.activo, 1) = 1
        """
    )
    productos = cursor.fetchall()

    cursor.execute(
        """
        SELECT oi.producto, oi.precio, oi.id, COALESCE(oi.indicacion, ''), c.nombre
        FROM orden_items oi
        LEFT JOIN productos p ON LOWER(p.nombre)=LOWER(oi.producto)
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE oi.orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()

    repartidores_activos = listar_repartidores(cursor, solo_activos=True)
    repartidor_delivery_actual = obtener_repartidor(cursor, o[12]) if o[12] else None
    tasa = obtener_tasa_actual(cursor)
    conn.close()

    delivery_usd = a_float(o[11])
    delivery_repartidor_id = o[12]
    totales_visuales = calcular_totales_visuales_delivery(items, delivery_usd)
    total_usd = totales_visuales["venta_restaurante_usd"]
    total_bs = total_usd * tasa
    total_cliente_usd = totales_visuales["total_cliente_usd"]
    total_cliente_bs = total_cliente_usd * tasa
    delivery_legacy_usd = totales_visuales["delivery_legacy_usd"]
    tiene_delivery_legacy = delivery_legacy_usd > TOLERANCIA_COBRO
    descuento = o[8] if o[8] else 0
    total_bs_final = max(total_bs - descuento, 0)
    bloqueada_por_cierre = o[10] is not None
    edicion_emergencia_activa = emergencia_activa(orden_id)
    puede_modificar_orden = (not bloqueada_por_cierre) and (
        estado != "cerrada" or edicion_emergencia_activa
    )

    boton_reimprimir = ""
    if usuario_puede_reimprimir_cocina() and estado in ("en cocina", "listo", "cerrada"):
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
    {estilos_base()}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--gris-fondo); color: var(--texto); }}
    .contenedor {{ display: flex; gap: 0; }}
    .productos {{ width: 60%; padding: 18px; }}
    .panel {{ width: 40%; padding: 18px; background: var(--panel); min-height: calc(100vh - 70px); box-sizing: border-box; border-left: 1px solid var(--borde); box-shadow: -4px 0 18px rgba(0,0,0,0.24); }}
    .btn {{ width: 100%; padding: 14px; margin: 6px 0; background: var(--tarjeta); color: var(--texto); border: 1px solid var(--borde); border-radius: 12px; font-weight: 800; font-size: 15px; cursor: pointer; box-shadow:var(--sombra-suave); transition:background 0.16s ease, border-color 0.16s ease, transform 0.1s ease; }}
    .btn:hover {{ background:#252A32; border-color:rgba(61,220,132,0.38); }}
    .categoria {{ font-weight: 800; margin-top: 14px; background: var(--panel-secundario) !important; color: var(--texto-secundario); padding: 8px 12px; border-radius: 999px; font-size: 13px; letter-spacing: 0.5px; border: 1px solid var(--borde); display:inline-flex; }}
    .grid-productos {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .acciones-superiores {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }}
    .btn-accion {{ display: block; padding: 14px 12px; margin: 5px 0; text-align: center; color: white; text-decoration: none; border-radius: 10px; font-weight: 800; font-size: 15px; }}
    .cocina {{ background: var(--naranja); color:#0F1115; border:none; }}
    .cobrar {{ background: var(--verde-neko); color:#0F1115; border:none; }}
    .editar {{ background: var(--azul); border:none; }}
    .eliminar {{ background: var(--rojo); border:none; }}
    .volver {{ background: var(--panel-secundario); border:1px solid var(--borde); }}
    .total {{ font-size: 20px; margin-top: 12px; font-weight: 800; color: var(--texto); }}
    .info-cierre {{ background:#2A2417; border:1px solid var(--naranja); padding:12px; border-radius:10px; margin-bottom:14px; color:#F8D083; font-weight:600; }}
    .modal-refresco {{ position:fixed; inset:0; background:rgba(17,24,39,0.62); display:none; align-items:center; justify-content:center; padding:18px; z-index:1000; }}
    .modal-refresco.activo {{ display:flex; }}
    .modal-contenido {{ width:min(620px, 100%); max-height:85vh; overflow-y:auto; background:var(--panel); color:var(--texto); border:1px solid var(--borde); border-radius:16px; padding:18px; box-shadow:0 24px 50px rgba(0,0,0,0.42); }}
    .modal-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:14px; }}
    .modal-top h2 {{ margin:0; color:var(--verde-neko); }}
    .modal-top p {{ margin:5px 0 0; color:var(--texto-secundario); }}
    .cerrar-modal {{ width:auto; min-height:44px; padding:8px 14px; border:none; border-radius:8px; background:#6b7280; color:white; cursor:pointer; font-weight:700; }}
    .sabores-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
    .sabor-btn {{ min-height:68px; padding:14px; border:none; border-radius:12px; background:var(--tarjeta); color:var(--texto); font-size:16px; font-weight:900; cursor:pointer; text-align:center; display:flex; align-items:center; justify-content:center; box-shadow:var(--sombra-suave); transition:opacity 0.16s ease, transform 0.16s ease, border-color 0.16s ease; }}
    .sabor-btn:hover {{ opacity:0.90; transform:translateY(-1px); }}
    .sabor-btn:active {{ transform:translateY(0); }}
    .sabor-coca-cola {{ background:#E50914; }}
    .sabor-chinotto {{ background:#111827; }}
    .sabor-frescolita {{ background:#FF4C4C; }}
    .sabor-naranja {{ background:#f97316; color:#1c1917; }}
    .sabor-uva {{ background:#6A0DAD; }}
    .sabor-btn.otro {{ background:#7c3aed; }}
    .item-orden {{ display:flex; justify-content:space-between; align-items:flex-start; margin:5px 0; gap:10px; border-bottom:1px solid var(--borde); padding:8px 0; }}
    .item-detalle {{ flex:1; min-width:0; }}
    .item-indicacion {{ color:var(--verde-neko); font-size:13px; margin-top:3px; font-weight:700; }}
    .item-descripcion {{ color:var(--verde-neko); font-size:14px; margin-top:4px; font-weight:800; line-height:1.35; white-space:pre-line; }}
    .acciones-item {{ display:flex; gap:6px; align-items:center; flex:0 0 auto; }}
    .btn-item {{ color:white; border:none; border-radius:8px; padding:8px 10px; cursor:pointer; width:auto; min-height:38px; box-shadow:none; font-weight:700; }}
    .combo-config {{ display:grid; grid-template-columns:1fr; gap:12px; }}
    .combo-config-seccion {{ margin:0; }}
    .combo-config-seccion label {{ display:block; margin:0 0 6px; color:var(--texto-secundario); font-size:13px; font-weight:800; letter-spacing:0.3px; text-transform:uppercase; }}
    .combo-select {{ width:100%; min-height:50px; padding:11px 12px; border:1px solid var(--borde); border-radius:10px; background:var(--panel-secundario); color:var(--texto); font-size:16px; font-weight:800; box-sizing:border-box; }}
    .combo-select:focus {{ outline:none; border-color:var(--verde-neko); box-shadow:0 0 0 3px rgba(61,220,132,0.12); }}
    .extra-lumpia-opciones {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .extra-lumpia-btn {{ min-height:50px; padding:11px 12px; border:1px solid var(--borde); border-radius:10px; background:var(--panel-secundario); color:var(--texto); font-size:15px; font-weight:900; cursor:pointer; transition:background 0.16s ease, border-color 0.16s ease; }}
    .extra-lumpia-btn:hover {{ background:#252A32; border-color:#3C4350; }}
    .extra-lumpia-btn.activo {{ background:var(--verde-neko); color:white; border-color:var(--verde-neko); }}
    .combo-aceptar {{ width:100%; margin-top:4px; background:var(--verde-neko); color:#0F1115; position:sticky; bottom:0; }}
    .delivery-panel {{ border:1px solid var(--borde); background:var(--panel-secundario); border-radius:12px; padding:14px; margin:14px 0; }}
    .delivery-panel h3 {{ margin-top:0; }}
    .delivery-grid {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; margin:8px 0; }}
    .delivery-monto-btn {{ min-height:44px; border:1px solid var(--borde); border-radius:9px; background:var(--tarjeta); color:var(--texto); font-weight:900; cursor:pointer; }}
    .delivery-monto-btn.activo {{ background:var(--verde-neko); color:#0F1115; border-color:var(--verde-neko); }}
    .delivery-form-row {{ display:grid; grid-template-columns:1fr; gap:8px; }}
    .delivery-actions {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }}
    .delivery-help {{ color:var(--texto-secundario); font-size:13px; margin:6px 0; }}
    .delivery-alerta {{ background:#3b2b12; color:#fde68a; border:1px solid #92400e; border-radius:8px; padding:10px; margin:8px 0; }}
    .delivery-nuevo {{ display:none; margin-top:10px; border-top:1px solid var(--borde); padding-top:10px; }}
    .delivery-nuevo.activo {{ display:block; }}
    .total-cliente {{ color:var(--verde-neko); }}
    @media (max-width: 768px) {{
        .contenedor {{ flex-direction: column; }}
        .productos, .panel {{ width: 100%; min-height: auto; border-left: none; }}
        .sabores-grid {{ grid-template-columns:1fr 1fr; }}
        .extra-lumpia-opciones {{ grid-template-columns:1fr; }}
        .delivery-grid, .delivery-actions {{ grid-template-columns:1fr 1fr; }}
        .modal-refresco {{ padding:12px; }}
        .modal-contenido {{ width:calc(100% - 24px); padding:14px; }}
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
            Esta orden ya pertenece a un cierre de jornada. Primero debes revertirla desde reportes.
        </div>
        """
    elif estado == "cerrada" and edicion_emergencia_activa:
        html += """
        <div class="info-cierre">
            Edicion de emergencia activa. Corrige la orden y vuelve a cobrar para actualizar los pagos.
        </div>
        """

    cats_dict = defaultdict(list)
    for p in productos:
        cat_nombre = p[3] if p[3] else "Sin categoria"
        if es_producto_delivery_legacy(p[1], cat_nombre):
            continue
        cats_dict[cat_nombre].append(p)

    orden_cat_map = {nombre: i for i, nombre in enumerate(ORDEN_CATEGORIAS_POS)}
    cats_ordenadas = sorted(
        cats_dict.items(),
        key=lambda x: (orden_cat_map.get(x[0], 999), x[0]),
    )

    if puede_modificar_orden:
        for categoria, lista in cats_ordenadas:
            color_cat = COLORES_CATEGORIAS_POS.get(categoria, "#374151")
            html += f"<div class='categoria' style='background:{color_cat};'>{categoria}</div>"
            html += "<div class='grid-productos'>"

            for p in lista:
                precio_fmt = f"${p[2]:.2f}".rstrip("0").rstrip(".")
                if es_producto_refresco(p[1]):
                    html += f"""
                    <button class="btn btn-refresco" type="button" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{html_lib.escape(p[1], quote=True)}">
                        {p[1]} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    """
                elif p[1] in COMBOS_PERSONALES:
                    acompanantes_data = html_lib.escape("|".join(ACOMPANANTES_COMBO), quote=True)
                    bebidas_data = html_lib.escape("|".join(BEBIDAS_COMBO), quote=True)
                    cantidad_acompanantes = COMBOS_CANTIDAD_ACOMPANANTES.get(p[1], 1)
                    html += f"""
                    <button class="btn btn-configurable" type="button" data-tipo="combo" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{html_lib.escape(p[1], quote=True)}" data-acompanantes="{acompanantes_data}" data-cantidad-acompanantes="{cantidad_acompanantes}" data-bebidas="{bebidas_data}">
                        {p[1]} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    """
                elif p[1] in PROMOCIONES_NEKO:
                    promo = PROMOCIONES_NEKO[p[1]]
                    pollos_data = html_lib.escape("|".join(POLLOS_PROMOCION if p[1] in PROMOCIONES_CON_POLLO else []), quote=True)
                    arroces_data = html_lib.escape("|".join(ARROCES_PROMOCION), quote=True)
                    html += f"""
                    <button class="btn btn-configurable" type="button" data-tipo="promocion" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{html_lib.escape(p[1], quote=True)}" data-pollos="{pollos_data}" data-arroces="{arroces_data}" data-cantidad-arroces="{promo['cantidad_arroces']}" data-cantidad-refrescos="{promo['cantidad_refrescos']}" data-refresco="{promo['refresco']}">
                        {p[1]} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    """
                else:
                    html += f"""
                    <a href="/agregar/{orden_id}/{p[0]}">
                        <button class="btn" type="button">{p[1]} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span></button>
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

    boton_editar_orden = ""
    if puede_modificar_orden:
        boton_editar_orden = f'<a href="/editar_orden/{orden_id}" class="btn-accion editar">✏️ Editar orden</a>'

    boton_emergencia = ""
    if usuario_es_admin_cierre() and estado == "cerrada" and not bloqueada_por_cierre:
        if edicion_emergencia_activa:
            boton_emergencia = '<div class="btn-accion" style="background:#DC2626;">🚨 Emergencia activa</div>'
        else:
            boton_emergencia = f"""
            <form method="post" action="/activar_edicion_emergencia/{orden_id}" class="form-emergencia" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-accion" style="width:100%; border:none; cursor:pointer; background:#DC2626;">🚨 Editar emergencia</button>
            </form>
            """

    repartidor_options = '<option value="">Sin repartidor</option>'
    for rep in repartidores_activos:
        selected = "selected" if rep[0] == delivery_repartidor_id else ""
        repartidor_options += (
            f'<option value="{rep[0]}" {selected}>{html_lib.escape(rep[1])}</option>'
        )

    if delivery_usd > TOLERANCIA_COBRO and not delivery_repartidor_id:
        delivery_estado_repartidor = "Repartidor: Pendiente de asignar"
    elif delivery_repartidor_id and repartidor_delivery_actual:
        delivery_estado_repartidor = f"Repartidor: {html_lib.escape(repartidor_delivery_actual[1] or '')}"
    else:
        delivery_estado_repartidor = "Repartidor: Sin delivery"

    botones_delivery = ""
    for monto_rapido in DELIVERY_MONTOS_RAPIDOS:
        activo = "activo" if abs(delivery_usd - monto_rapido) <= TOLERANCIA_COBRO else ""
        botones_delivery += (
            f'<button type="button" class="delivery-monto-btn {activo}" '
            f'data-delivery-monto="{monto_rapido:.2f}">${monto_rapido:.2f}</button>'
        )

    delivery_bloqueado = (not puede_modificar_orden) or tiene_delivery_legacy
    delivery_disabled = "disabled" if delivery_bloqueado else ""
    delivery_aviso = ""
    if tiene_delivery_legacy:
        delivery_aviso = (
            "<div class='delivery-alerta'>"
            "Esta orden contiene un delivery agregado con el sistema anterior. "
            "No se puede agregar delivery explícito para evitar doble cargo."
            "</div>"
        )
    elif not puede_modificar_orden:
        delivery_aviso = "<div class='delivery-alerta'>Delivery bloqueado para esta orden.</div>"

    html += f"""
    <div class="panel">
        <h2>🧾 Orden {texto_numero_orden(o[1])}</h2>
        <div class="acciones-superiores">
            {boton_editar_orden}
            {boton_eliminar_orden}
            {boton_emergencia}
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
        if not puede_modificar_orden:
            boton_eliminar = ""
            boton_indicacion = ""
        else:
            boton_eliminar = f"""
            <form method="post" action="/eliminar_item/{i[2]}/{orden_id}" class="form-eliminar-item" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-item" style="background:#c0392b;">❌</button>
            </form>
            """
            boton_indicacion = f"""
            <form method="post" action="/actualizar_indicacion_item/{i[2]}/{orden_id}" class="form-indicacion-item" style="margin:0;" data-indicacion="{html_lib.escape(i[3] or '', quote=True)}">
                <input type="hidden" name="indicacion" value="">
                <button type="submit" class="btn-item" style="background:#2980b9;">✏️</button>
            </form>
            """

        descripcion_combo = (
            texto_descripcion_combo_orden(i[0], i[3])
            or texto_descripcion_promocion_orden(i[0], i[3])
        )
        indicacion_html = ""
        if descripcion_combo:
            descripcion_segura = "<br>".join(
                html_lib.escape(linea) for linea in descripcion_combo.splitlines()
            )
            indicacion_html = f"<div class='item-descripcion'>{descripcion_segura}</div>"
        elif i[3]:
            indicacion_html = f"<div class='item-indicacion'>(Indicación: {html_lib.escape(i[3])})</div>"

        html += f"""
        <div class="item-orden">
            <div class="item-detalle">
                <div>{html_lib.escape(i[0])} - ${i[1]}</div>
                {indicacion_html}
            </div>
            <div class="acciones-item">
                {boton_indicacion}
                {boton_eliminar}
            </div>
        </div>
        """

    html += f"""
        <div class="delivery-panel">
            <h3>Delivery</h3>
            {delivery_aviso}
            <form method="post" action="/orden/{orden_id}/delivery" id="deliveryForm">
                <label>Monto USD</label>
                <div class="delivery-grid">{botones_delivery}</div>
                <input name="delivery_usd" id="delivery_usd" type="number" min="0" max="{DELIVERY_MONTO_MAXIMO:.2f}" step="0.01" value="{delivery_usd:.2f}" {delivery_disabled}>
                <label>Repartidor</label>
                <select name="delivery_repartidor_id" id="delivery_repartidor_id" {delivery_disabled}>
                    {repartidor_options}
                </select>
                <div class="delivery-help">{delivery_estado_repartidor}</div>
                <div class="delivery-help">Puedes guardar el monto y asignar el repartidor mas tarde. Para cobrar, debe estar asignado.</div>
                <div class="delivery-actions">
                    <button class="btn" type="submit" {delivery_disabled}>Guardar delivery</button>
                    <button class="btn" type="button" id="mostrarNuevoRepartidor" {delivery_disabled}>+ Nuevo repartidor</button>
                </div>
            </form>
            <div class="delivery-nuevo" id="nuevoRepartidorPanel">
                <input id="nuevoRepartidorNombre" placeholder="Nombre del repartidor">
                <input id="nuevoRepartidorTelefono" placeholder="Teléfono">
                <button class="btn" type="button" id="guardarNuevoRepartidor">Crear y seleccionar</button>
                <div class="delivery-help" id="nuevoRepartidorMensaje"></div>
                <a href="/repartidores" class="delivery-help">Administrar repartidores</a>
            </div>
        </div>
        <div class="total">Consumo Neko Wok: ${total_usd:.2f}</div>
        <div class="total">Delivery: ${(delivery_usd + delivery_legacy_usd):.2f}</div>
        <div class="total total-cliente">Total cliente: ${total_cliente_usd:.2f}</div>
        <div class="total">USD: ${total_usd:.2f}</div>
        <div class="total">Bs: {total_bs:.2f}</div>
        <p>Descuento: Bs {round(descuento, 2)}</p>
        <div class="total">Total Final Bs: {total_bs_final:.2f}</div>
        <div class="delivery-help">Total cliente Bs visual: {total_cliente_bs:.2f}</div>
        {boton_reimprimir}
    """

    if not bloqueada_por_cierre and estado != "cerrada":
        html += f"""
        <a href="/enviar_cocina/{orden_id}" class="btn-accion cocina">🍳 Enviar a cocina</a>
        <a href="/activar_factura/{orden_id}" class="btn-accion" style="background:#8e44ad;">🧾 Facturar</a>
        <a href="/cobrar/{orden_id}" class="btn-accion cobrar"{advertencia_cobro}>💵 Cobrar</a>
        """
    elif edicion_emergencia_activa:
        html += f"""
        <a href="/cobrar/{orden_id}" class="btn-accion cobrar">💵 Volver a cobrar</a>
        """

    if not bloqueada_por_cierre and items and estado in ("abierta", "en cocina", "listo", "cerrada"):
        html += f"""
        <a href="/reimprimir_factura/{orden_id}" class="btn-accion" style="background:#d35400;">🧾 Reimprimir factura</a>
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
    <div id="modal-configuracion" class="modal-refresco" aria-hidden="true">
        <div class="modal-contenido">
            <div class="modal-top">
                <div>
                    <h2 id="modal-configuracion-titulo">Configurar producto</h2>
                    <p id="modal-configuracion-producto">Producto</p>
                </div>
                <button id="cerrar-modal-configuracion" class="cerrar-modal" type="button">✖</button>
            </div>
            <div id="configuracion-opciones-grid" class="sabores-grid"></div>
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
    const deliveryMonto = document.getElementById("delivery_usd");
    const deliveryRepartidor = document.getElementById("delivery_repartidor_id");
    const nuevoRepartidorPanel = document.getElementById("nuevoRepartidorPanel");
    const mostrarNuevoRepartidor = document.getElementById("mostrarNuevoRepartidor");
    const guardarNuevoRepartidor = document.getElementById("guardarNuevoRepartidor");
    const nuevoRepartidorNombre = document.getElementById("nuevoRepartidorNombre");
    const nuevoRepartidorTelefono = document.getElementById("nuevoRepartidorTelefono");
    const nuevoRepartidorMensaje = document.getElementById("nuevoRepartidorMensaje");

    document.querySelectorAll(".delivery-monto-btn").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            if (!deliveryMonto || deliveryMonto.disabled) {{
                return;
            }}
            deliveryMonto.value = btn.dataset.deliveryMonto;
            document.querySelectorAll(".delivery-monto-btn").forEach(function(opcion) {{
                opcion.classList.toggle("activo", opcion === btn);
            }});
        }});
    }});

    if (mostrarNuevoRepartidor && nuevoRepartidorPanel) {{
        mostrarNuevoRepartidor.addEventListener("click", function() {{
            nuevoRepartidorPanel.classList.toggle("activo");
            if (nuevoRepartidorPanel.classList.contains("activo") && nuevoRepartidorNombre) {{
                nuevoRepartidorNombre.focus();
            }}
        }});
    }}

    if (guardarNuevoRepartidor) {{
        guardarNuevoRepartidor.addEventListener("click", function() {{
            const nombre = (nuevoRepartidorNombre.value || "").trim();
            const telefono = (nuevoRepartidorTelefono.value || "").trim();
            if (!nombre) {{
                nuevoRepartidorMensaje.textContent = "El nombre es obligatorio.";
                nuevoRepartidorNombre.focus();
                return;
            }}
            fetch("/api/repartidores", {{
                method: "POST",
                headers: {{"Content-Type": "application/json"}},
                body: JSON.stringify({{nombre: nombre, telefono: telefono}})
            }})
            .then(function(response) {{ return response.json().then(function(data) {{ return {{status: response.status, data: data}}; }}); }})
            .then(function(result) {{
                if (!result.data.ok) {{
                    nuevoRepartidorMensaje.textContent = result.data.error || "No se pudo crear el repartidor.";
                    return;
                }}
                const rep = result.data.repartidor;
                const option = document.createElement("option");
                option.value = String(rep.id);
                option.textContent = rep.nombre;
                option.selected = true;
                deliveryRepartidor.appendChild(option);
                nuevoRepartidorNombre.value = "";
                nuevoRepartidorTelefono.value = "";
                nuevoRepartidorMensaje.textContent = "Repartidor creado y seleccionado.";
                nuevoRepartidorPanel.classList.remove("activo");
            }})
            .catch(function() {{
                nuevoRepartidorMensaje.textContent = "No se pudo crear el repartidor.";
            }});
        }});
    }}

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

    function claseSaborRefresco(sabor) {{
        const clases = {{
            "Coca Cola": "sabor-coca-cola",
            "Chinotto": "sabor-chinotto",
            "Frescolita": "sabor-frescolita",
            "Naranja": "sabor-naranja",
            "Uva": "sabor-uva"
        }};
        return clases[sabor] || "";
    }}

    function abrirSelectorRefresco(btn) {{
        refrescoSeleccionadoUrl = btn.dataset.url;
        modalRefrescoProducto.textContent = btn.dataset.producto || "Refresco";
        saboresRefrescoGrid.innerHTML = "";

        saboresRefresco.forEach(function(sabor) {{
            const boton = document.createElement("button");
            boton.type = "button";
            const claseColor = claseSaborRefresco(sabor);
            boton.className = "sabor-btn" + (claseColor ? " " + claseColor : "") + (sabor === "Otro" ? " otro" : "");
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

    document.querySelectorAll(".form-indicacion-item").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            event.preventDefault();
            const actual = form.dataset.indicacion || "";
            const indicacion = prompt("Indicación especial para este plato", actual);
            if (indicacion === null) {{
                return;
            }}
            form.querySelector('input[name="indicacion"]').value = indicacion.trim();
            form.submit();
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

    document.querySelectorAll(".form-emergencia").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            const clave = pedirClaveSupervisor();
            if (!clave) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave;
        }});
    }});

    const modalConfiguracion = document.getElementById("modal-configuracion");
    const modalConfiguracionTitulo = document.getElementById("modal-configuracion-titulo");
    const modalConfiguracionProducto = document.getElementById("modal-configuracion-producto");
    const configuracionOpcionesGrid = document.getElementById("configuracion-opciones-grid");
    const cerrarModalConfiguracion = document.getElementById("cerrar-modal-configuracion");
    let configuracionUrl = "";
    let pasosConfiguracion = [];
    let pasoConfiguracionActual = 0;
    let seleccionesConfiguracion = [];

    function cerrarConfiguracion() {{
        configuracionUrl = "";
        pasosConfiguracion = [];
        pasoConfiguracionActual = 0;
        seleccionesConfiguracion = [];
        modalConfiguracion.classList.remove("activo");
        modalConfiguracion.setAttribute("aria-hidden", "true");
    }}

    function terminarConfiguracion() {{
        const destino = new URL(configuracionUrl, window.location.origin);
        seleccionesConfiguracion.forEach(function(seleccion) {{
            destino.searchParams.append(seleccion.parametro, seleccion.valor);
        }});
        window.location.href = destino.pathname + destino.search;
    }}

    function seleccionarOpcionConfiguracion(paso, valor) {{
        let valorFinal = valor;
        if (valor === "Otro") {{
            valorFinal = prompt("Escribe el sabor del refresco");
            if (valorFinal === null || !valorFinal.trim()) {{
                return;
            }}
            valorFinal = valorFinal.trim();
        }}
        if (paso.parametro === "extra_lumpias") {{
            valorFinal = valor.startsWith("Añadir") ? "1" : "0";
        }}
        seleccionesConfiguracion.push({{parametro: paso.parametro, valor: valorFinal}});
        pasoConfiguracionActual += 1;
        if (pasoConfiguracionActual >= pasosConfiguracion.length) {{
            terminarConfiguracion();
            return;
        }}
        mostrarPasoConfiguracion();
    }}

    function mostrarPasoConfiguracion() {{
        const paso = pasosConfiguracion[pasoConfiguracionActual];
        modalConfiguracionTitulo.textContent = paso.titulo;
        configuracionOpcionesGrid.innerHTML = "";
        paso.opciones.forEach(function(opcion) {{
            const boton = document.createElement("button");
            boton.type = "button";
            boton.className = "sabor-btn" + (opcion === "Otro" ? " otro" : "");
            boton.textContent = opcion;
            boton.addEventListener("click", function() {{
                seleccionarOpcionConfiguracion(paso, opcion);
            }});
            configuracionOpcionesGrid.appendChild(boton);
        }});
    }}

    function tituloCombo(producto) {{
        const match = (producto || "").match(/(\\d+)/);
        return match ? "COMBO #" + match[1] : (producto || "COMBO");
    }}

    function crearGrupoRadio(titulo, nombre, opciones) {{
        const seccion = document.createElement("div");
        seccion.className = "combo-config-seccion";
        const etiqueta = document.createElement("label");
        etiqueta.textContent = titulo;
        seccion.appendChild(etiqueta);

        const select = document.createElement("select");
        select.className = "combo-select";
        select.name = nombre;
        select.required = true;

        const opcionVacia = document.createElement("option");
        opcionVacia.value = "";
        opcionVacia.textContent = "Seleccionar...";
        select.appendChild(opcionVacia);

        opciones.forEach(function(opcion) {{
            const option = document.createElement("option");
            option.value = opcion;
            option.textContent = opcion;
            select.appendChild(option);
        }});
        seccion.appendChild(select);
        return seccion;
    }}

    function crearGrupoExtraLumpia() {{
        const seccion = document.createElement("div");
        seccion.className = "combo-config-seccion";

        const etiqueta = document.createElement("label");
        etiqueta.textContent = "Extra de Lumpia";
        seccion.appendChild(etiqueta);

        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "extra_lumpias";
        hidden.value = "0";
        seccion.appendChild(hidden);

        const opciones = document.createElement("div");
        opciones.className = "extra-lumpia-opciones";

        const botonSinExtra = document.createElement("button");
        botonSinExtra.type = "button";
        botonSinExtra.className = "extra-lumpia-btn activo";
        botonSinExtra.textContent = "Sin extra de Lumpia";
        botonSinExtra.dataset.valor = "0";

        const botonExtra = document.createElement("button");
        botonExtra.type = "button";
        botonExtra.className = "extra-lumpia-btn";
        botonExtra.textContent = "Extra de Lumpia";
        botonExtra.dataset.valor = "1";

        [botonSinExtra, botonExtra].forEach(function(boton) {{
            boton.addEventListener("click", function() {{
                hidden.value = boton.dataset.valor;
                botonSinExtra.classList.toggle("activo", boton.dataset.valor === "0");
                botonExtra.classList.toggle("activo", boton.dataset.valor === "1");
            }});
            opciones.appendChild(boton);
        }});

        seccion.appendChild(opciones);
        return seccion;
    }}

    function abrirConfiguracionCombo(btn) {{
        configuracionUrl = btn.dataset.url;
        const producto = btn.dataset.producto || "Combo";
        const acompanantes = (btn.dataset.acompanantes || "").split("|").filter(Boolean);
        const bebidas = (btn.dataset.bebidas || "").split("|").filter(Boolean);
        const cantidadAcompanantes = Number(btn.dataset.cantidadAcompanantes || 1);

        modalConfiguracionTitulo.textContent = tituloCombo(producto);
        modalConfiguracionProducto.textContent = "";
        configuracionOpcionesGrid.innerHTML = "";
        configuracionOpcionesGrid.className = "combo-config";

        if (cantidadAcompanantes === 1) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Acompañante", "acompanante_1", acompanantes));
        }} else {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Primer acompañante", "acompanante_1", acompanantes));
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Segundo acompañante", "acompanante_2", acompanantes));
        }}
        configuracionOpcionesGrid.appendChild(crearGrupoRadio("Bebida", "bebida", bebidas));

        const aceptar = document.createElement("button");
        aceptar.type = "button";
        aceptar.className = "sabor-btn combo-aceptar";
        aceptar.textContent = "Aceptar";
        aceptar.addEventListener("click", function() {{
            const destino = new URL(configuracionUrl, window.location.origin);
            for (let i = 1; i <= cantidadAcompanantes; i += 1) {{
                const elegido = configuracionOpcionesGrid.querySelector('select[name="acompanante_' + i + '"]');
                if (!elegido || !elegido.value) {{
                    alert("Debes seleccionar todos los acompañantes");
                    return;
                }}
                destino.searchParams.append("acompanante", elegido.value);
            }}
            const bebida = configuracionOpcionesGrid.querySelector('select[name="bebida"]');
            if (!bebida || !bebida.value) {{
                alert("Debes seleccionar una bebida");
                return;
            }}
            destino.searchParams.append("bebida", bebida.value);
            window.location.href = destino.pathname + destino.search;
        }});
        configuracionOpcionesGrid.appendChild(aceptar);

        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }}

    function abrirConfiguracion(btn) {{
        configuracionUrl = btn.dataset.url;
        modalConfiguracionProducto.textContent = btn.dataset.producto || "Producto";
        pasosConfiguracion = [];
        seleccionesConfiguracion = [];
        pasoConfiguracionActual = 0;
        configuracionOpcionesGrid.className = "sabores-grid";
        const sabores = saboresRefresco.slice();

        if (btn.dataset.tipo === "combo") {{
            abrirConfiguracionCombo(btn);
            return;
        }} else {{
            const pollos = (btn.dataset.pollos || "").split("|").filter(Boolean);
            const arroces = (btn.dataset.arroces || "").split("|").filter(Boolean);
            const cantidadArroces = Number(btn.dataset.cantidadArroces || 0);
            const cantidadRefrescos = Number(btn.dataset.cantidadRefrescos || 0);
            if (pollos.length) {{
                pasosConfiguracion.push({{
                    titulo: "Tipo de pollo",
                    parametro: "pollo",
                    opciones: pollos
                }});
            }}
            for (let i = 1; i <= cantidadArroces; i += 1) {{
                pasosConfiguracion.push({{
                    titulo: "Elige el arroz " + i + " de " + cantidadArroces,
                    parametro: "arroz",
                    opciones: arroces
                }});
            }}
            for (let i = 1; i <= cantidadRefrescos; i += 1) {{
                pasosConfiguracion.push({{
                    titulo: "Sabor del " + (btn.dataset.refresco || "refresco") + " " + i + " de " + cantidadRefrescos,
                    parametro: "sabor",
                    opciones: sabores
                }});
            }}
            pasosConfiguracion.push({{
                titulo: "¿Añadir Ración de Lumpias por $3.00?",
                parametro: "extra_lumpias",
                opciones: ["Sin extra", "Añadir Ración de Lumpias (+$3.00)"]
            }});
        }}

        if (!pasosConfiguracion.length) {{
            window.location.href = configuracionUrl;
            return;
        }}
        mostrarPasoConfiguracion();
        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }}

    function abrirConfiguracionSelect(btn) {{
        if (btn.dataset.tipo === "combo") {{
            abrirConfiguracionCombo(btn);
            return;
        }}

        configuracionUrl = btn.dataset.url;
        modalConfiguracionTitulo.textContent = "Configurar promocion";
        modalConfiguracionProducto.textContent = btn.dataset.producto || "Producto";
        configuracionOpcionesGrid.innerHTML = "";
        configuracionOpcionesGrid.className = "combo-config";

        const pollos = (btn.dataset.pollos || "").split("|").filter(Boolean);
        const arroces = (btn.dataset.arroces || "").split("|").filter(Boolean);
        const cantidadArroces = Number(btn.dataset.cantidadArroces || 0);
        const cantidadRefrescos = Number(btn.dataset.cantidadRefrescos || 0);
        const sabores = saboresRefresco.slice();

        if (pollos.length) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Tipo de pollo", "pollo", pollos));
        }}
        for (let i = 1; i <= cantidadArroces; i += 1) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio(cantidadArroces === 1 ? "Arroz" : "Arroz " + i, "arroz_" + i, arroces));
        }}
        for (let i = 1; i <= cantidadRefrescos; i += 1) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio(cantidadRefrescos === 1 ? "Refresco" : "Refresco " + i, "sabor_" + i, sabores));
        }}
        configuracionOpcionesGrid.appendChild(crearGrupoExtraLumpia());

        const aceptar = document.createElement("button");
        aceptar.type = "button";
        aceptar.className = "sabor-btn combo-aceptar";
        aceptar.textContent = "Aceptar";
        aceptar.addEventListener("click", function() {{
            const destino = new URL(configuracionUrl, window.location.origin);
            const campoPollo = configuracionOpcionesGrid.querySelector('select[name="pollo"]');
            if (campoPollo) {{
                if (!campoPollo.value) {{
                    alert("Debes seleccionar un tipo de pollo");
                    campoPollo.focus();
                    return;
                }}
                destino.searchParams.append("pollo", campoPollo.value);
            }}

            for (let i = 1; i <= cantidadArroces; i += 1) {{
                const arroz = configuracionOpcionesGrid.querySelector('select[name="arroz_' + i + '"]');
                if (!arroz || !arroz.value) {{
                    alert("Debes seleccionar todos los arroces");
                    if (arroz) {{
                        arroz.focus();
                    }}
                    return;
                }}
                destino.searchParams.append("arroz", arroz.value);
            }}

            for (let i = 1; i <= cantidadRefrescos; i += 1) {{
                const sabor = configuracionOpcionesGrid.querySelector('select[name="sabor_' + i + '"]');
                if (!sabor || !sabor.value) {{
                    alert("Debes seleccionar todos los refrescos");
                    if (sabor) {{
                        sabor.focus();
                    }}
                    return;
                }}
                let saborFinal = sabor.value;
                if (saborFinal === "Otro") {{
                    saborFinal = prompt("Escribe el sabor del refresco");
                    if (saborFinal === null || !saborFinal.trim()) {{
                        return;
                    }}
                    saborFinal = saborFinal.trim();
                }}
                destino.searchParams.append("sabor", saborFinal);
            }}

            const extraLumpias = configuracionOpcionesGrid.querySelector('input[name="extra_lumpias"]');
            destino.searchParams.append("extra_lumpias", extraLumpias ? extraLumpias.value : "0");
            window.location.href = destino.pathname + destino.search;
        }});
        configuracionOpcionesGrid.appendChild(aceptar);

        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }}

    document.querySelectorAll(".btn-configurable").forEach(function(btn) {{
        btn.addEventListener("click", function() {{ abrirConfiguracionSelect(btn); }});
    }});
    cerrarModalConfiguracion.addEventListener("click", cerrarConfiguracion);
    modalConfiguracion.addEventListener("click", function(event) {{
        if (event.target === modalConfiguracion) {{ cerrarConfiguracion(); }}
    }});
    </script>
    </body>
    </html>
    """
    return html


@app.route("/orden/<int:orden_id>/delivery", methods=["POST"])
def actualizar_delivery(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        actualizar_delivery_orden(
            cursor,
            orden_id,
            request.form.get("delivery_usd"),
            request.form.get("delivery_repartidor_id"),
        )
        conn.commit()
        conn.close()
        return redirect(f"/orden/{orden_id}")
    except ValueError as exc:
        conn.rollback()
        conn.close()
        return str(exc), 400


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

    if row[0] == "cerrada" and not emergencia_activa(orden_id):
        conn.close()
        return "No puedes agregar productos a una orden cerrada"

    cursor.execute(
        """
        SELECT p.nombre, p.precio, c.nombre
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE p.id=?
        """,
        (producto_id,),
    )
    p = cursor.fetchone()
    if not p:
        conn.close()
        return "Producto no encontrado"

    producto_nombre = p[0]
    if es_producto_delivery_legacy(producto_nombre, p[2]):
        conn.close()
        return "El delivery ahora se registra desde el campo Delivery de la orden.", 400

    cursor.execute("SELECT COALESCE(delivery_usd, 0) FROM ordenes WHERE id=?", (orden_id,))
    delivery_actual = a_float(cursor.fetchone()[0])
    if delivery_actual > TOLERANCIA_COBRO and es_producto_delivery_legacy(producto_nombre, p[2]):
        conn.close()
        return "Esta orden ya tiene delivery explícito configurado.", 400

    indicacion = ""
    if es_producto_refresco(producto_nombre):
        sabor = normalizar_sabor_refresco(request.args.get("sabor"))
        if not sabor:
            conn.close()
            return "Debes seleccionar un sabor valido para el refresco"
        indicacion = f"Sabor: {sabor}"
    elif producto_nombre in COMBOS_PERSONALES:
        cantidad_acompanantes = COMBOS_CANTIDAD_ACOMPANANTES.get(producto_nombre, 1)
        acompanantes = [(valor or "").strip() for valor in request.args.getlist("acompanante")]
        bebida = (request.args.get("bebida") or "").strip()
        if len(acompanantes) != cantidad_acompanantes or any(
            acompanante not in ACOMPANANTES_COMBO for acompanante in acompanantes
        ):
            conn.close()
            return "Debes seleccionar todos los acompañantes validos para este combo"
        if bebida not in BEBIDAS_COMBO:
            conn.close()
            return "Debes seleccionar una bebida valida para este combo"
        indicacion = serializar_indicacion(
            {
                "version": 1,
                "tipo": "combo",
                "producto": COMBOS_JSON[producto_nombre],
                "acompanantes": acompanantes,
                "bebida": bebida,
            }
        )
    elif producto_nombre in PROMOCIONES_NEKO:
        promo = PROMOCIONES_NEKO[producto_nombre]
        pollo = (request.args.get("pollo") or "").strip()
        arroces = [(valor or "").strip() for valor in request.args.getlist("arroz")]
        sabores = request.args.getlist("sabor")
        extra_lumpias = (request.args.get("extra_lumpias") or "0").strip()
        requiere_pollo = producto_nombre in PROMOCIONES_CON_POLLO
        if requiere_pollo and pollo not in POLLOS_PROMOCION:
            conn.close()
            return "Debes seleccionar un tipo de pollo valido para esta promocion"
        if len(arroces) != promo["cantidad_arroces"] or any(
            arroz not in ARROCES_PROMOCION for arroz in arroces
        ):
            conn.close()
            return "Debes seleccionar todos los arroces validos para esta promocion"
        sabores_normalizados = [normalizar_sabor_refresco(sabor) for sabor in sabores]
        if len(sabores_normalizados) != promo["cantidad_refrescos"] or any(
            not sabor for sabor in sabores_normalizados
        ):
            conn.close()
            return "Debes seleccionar todos los sabores de refresco"
        if extra_lumpias not in {"0", "1"}:
            conn.close()
            return "La selección del extra de lumpias no es valida"
        datos_promocion = {
            "version": 1,
            "tipo": "promocion",
            "producto": PROMOCIONES_JSON[producto_nombre],
            "arroces": arroces,
            "bebidas": sabores_normalizados,
        }
        if requiere_pollo:
            datos_promocion["pollo"] = pollo
        indicacion = serializar_indicacion(datos_promocion)

    indicacion = normalizar_indicacion_item(indicacion)

    cursor.execute(
        """
        INSERT INTO orden_items (orden_id, producto, precio, indicacion)
        VALUES (?, ?, ?, ?)
        """,
        (orden_id, producto_nombre, p[1], indicacion),
    )
    if producto_nombre in PROMOCIONES_NEKO and extra_lumpias == "1":
        cursor.execute(
            """
            INSERT INTO orden_items (orden_id, producto, precio, indicacion)
            VALUES (?, ?, ?, ?)
            """,
            (
                orden_id,
                PROMO_EXTRA_LUMPIAS_NOMBRE,
                PROMO_EXTRA_LUMPIAS_PRECIO,
                normalizar_indicacion_item(f"Agregado con: {producto_nombre}"),
            ),
        )
    if row[0] == "cerrada" and emergencia_activa(orden_id):
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "agregar_producto_emergencia",
            f"Producto agregado: {producto_nombre} - ${p[1]}",
        )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/enviar_cocina/<int:orden_id>")
def enviar_cocina(orden_id):
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

    if orden[1] not in ("en cocina", "listo", "cerrada"):
        conn.close()
        return "Solo se pueden reimprimir ordenes en cocina, listas o cerradas"

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
    if estado == "cerrada" and not emergencia_activa(orden_id):
        conn.close()
        return "Orden cerrada, no se puede modificar"

    cursor.execute(
        """
        SELECT id, producto, precio
        FROM orden_items
        WHERE id=? AND orden_id=?
        """,
        (item_id, orden_id),
    )
    item_row = cursor.fetchone()
    if not item_row:
        conn.close()
        return "Producto no encontrado en esta orden"

    cursor.execute("DELETE FROM orden_items WHERE id=? AND orden_id=?", (item_id, orden_id))
    if estado == "cerrada" and emergencia_activa(orden_id):
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "eliminar_producto_emergencia",
            f"Producto eliminado: {item_row[1]} - ${item_row[2]}",
        )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/actualizar_indicacion_item/<int:item_id>/<int:orden_id>", methods=["POST"])
def actualizar_indicacion_item(item_id, orden_id):
    indicacion = normalizar_indicacion_item(request.form.get("indicacion", ""))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return "Orden no encontrada"

    estado, cierre_id = row
    if cierre_id is not None:
        conn.close()
        return "Orden archivada, no se puede modificar"

    if estado not in ("abierta", "en cocina") and not (
        estado == "cerrada" and emergencia_activa(orden_id)
    ):
        conn.close()
        return "Orden cerrada, no se puede modificar"

    cursor.execute(
        """
        SELECT id, producto
        FROM orden_items
        WHERE id=? AND orden_id=?
        """,
        (item_id, orden_id),
    )
    item_row = cursor.fetchone()
    if not item_row:
        conn.close()
        return "Producto no encontrado en esta orden"

    cursor.execute(
        """
        UPDATE orden_items
        SET indicacion=?
        WHERE id=? AND orden_id=?
        """,
        (indicacion, item_id, orden_id),
    )

    if estado == "cerrada" and emergencia_activa(orden_id):
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "editar_indicacion_emergencia",
            f"Indicacion actualizada para {item_row[1]}: {indicacion}",
        )

    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/editar_orden/<int:orden_id>", methods=["GET", "POST"])
def editar_orden(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    bloqueo = cursor.fetchone()
    if not bloqueo:
        conn.close()
        return "Orden no encontrada"

    estado_orden, cierre_id = bloqueo
    if cierre_id is not None:
        conn.close()
        return "Esta orden ya pertenece a un cierre de jornada. Primero debes revertirla desde reportes."

    if estado_orden == "cerrada" and not emergencia_activa(orden_id):
        conn.close()
        return "Orden cerrada, no se puede modificar"

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
        if estado_orden == "cerrada" and emergencia_activa(orden_id):
            registrar_auditoria_emergencia(
                cursor,
                orden_id,
                "editar_datos_orden_emergencia",
                "Datos de la orden editados en emergencia",
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
    <h2>✏️ Editar orden {texto_numero_orden(o[1])}</h2>
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
        <button type="submit">💾 Guardar</button>
    </form>
    <br>
    <a href="/orden/{orden_id}">🏠 Volver</a>
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


@app.route("/activar_edicion_emergencia/<int:orden_id>", methods=["POST"])
def activar_edicion_emergencia(orden_id):
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
    if cierre_id is not None:
        conn.close()
        return "Esta orden ya pertenece a un cierre de jornada. Primero debes revertirla desde reportes."

    if estado != "cerrada":
        conn.close()
        return "La edicion de emergencia solo aplica a ordenes cobradas"

    registrar_auditoria_emergencia(
        cursor,
        orden_id,
        "activar_edicion_emergencia",
        "Edicion de emergencia activada por supervisor",
    )
    conn.commit()
    conn.close()

    activar_emergencia_sesion(orden_id)
    return redirect(f"/orden/{orden_id}")


@app.route("/api/clientes", methods=["GET", "POST"])
def api_clientes():
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        datos = request.get_json(silent=True) or request.form
        nombre = (datos.get("nombre", "") or "").strip()
        telefono = (datos.get("telefono", "") or "").strip()
        documento = (datos.get("documento", "") or "").strip()
        notas = (datos.get("notas", "") or "").strip()

        if not nombre:
            conn.close()
            return jsonify({"ok": False, "error": "El nombre del cliente es obligatorio"}), 400

        fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO clientes (nombre, telefono, documento, notas, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (nombre, telefono, documento, notas, fecha),
        )
        cliente_id = obtener_ultimo_id(cursor, "clientes")
        conn.commit()

        cursor.execute(
            "SELECT id, nombre, telefono, documento FROM clientes WHERE id=?",
            (cliente_id,),
        )
        cliente = cursor.fetchone()
        conn.close()
        return jsonify({"ok": True, "cliente": cliente_json_desde_fila(cliente)})

    clientes = [
        cliente_json_desde_fila(cliente)
        for cliente in listar_clientes_activos(cursor, request.args.get("q", ""))
    ]
    conn.close()
    return jsonify({"ok": True, "clientes": clientes})


@app.route("/cobrar/<int:orden_id>", methods=["GET", "POST"])
def cobrar(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
               o.estado, o.observacion, o.descuento, u.nombre, o.cierre_id, o.cliente_id,
               o.delivery_usd, o.delivery_repartidor_id
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
    cierre_id = o[10]
    cliente_id_actual = o[11]
    delivery_orden_usd = a_float(o[12])
    delivery_repartidor_id = o[13]

    if cierre_id is not None:
        conn.close()
        return "Esta orden ya pertenece a un cierre de jornada. Primero debes revertirla desde reportes."

    if estado == "cerrada" and not emergencia_activa(orden_id):
        conn.close()
        return "Orden cerrada, no se puede volver a cobrar sin activar edicion de emergencia"

    cursor.execute(
        """
        SELECT oi.producto, oi.precio, c.nombre
        FROM orden_items oi
        LEFT JOIN productos p ON LOWER(p.nombre)=LOWER(oi.producto)
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE oi.orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()

    if len(items) == 0:
        conn.close()
        return "No puedes cobrar una orden vacia"

    descuento_bs = a_float(o[8])
    try:
        tasa = obtener_tasa_cobro(cursor)
        totales_cobro = calcular_totales_financieros_delivery(
            items,
            tasa,
            descuento_bs,
            delivery_orden_usd,
        )
    except ValueError as exc:
        conn.close()
        mensaje = str(exc) if "delivery" in str(exc).lower() else "Tasa de cobro invalida. Corrige la tasa antes de cobrar."
        return mensaje, 400
    total_usd = totales_cobro["subtotal_restaurante_usd"]
    total_bs = round(total_usd * tasa, 2)
    total_bs_final = totales_cobro["total_cliente_bs"]
    total_cliente_usd = totales_cobro["total_cliente_usd"]
    total_cliente_bs = totales_cobro["total_cliente_bs"]

    error = ""
    metodo1_val = ""
    monto1_val = f"{round(total_bs_final, 2)}"
    ref1_val = ""
    metodo2_val = ""
    monto2_val = ""
    ref2_val = ""
    descuento_val = f"{round(descuento_bs, 2)}"
    modo_cobro_val = "pagado"
    cliente_id_val = str(cliente_id_actual or "")

    if request.method == "POST":
        modo_cobro = normalizar_modo_cobro(request.form.get("modo_cobro"))
        modo_cobro_val = modo_cobro or (request.form.get("modo_cobro", "") or "").strip()
        cliente_id_val = (request.form.get("cliente_id", "") or "").strip()
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

        cliente_cxc = None
        if modo_cobro == "":
            conn.close()
            return "Modo de cobro invalido", 400
        elif modo_cobro in ("parcial", "credito"):
            try:
                cliente_cxc = obtener_cliente_para_cxc(cursor, cliente_id_val)
            except ValueError as exc:
                conn.close()
                return str(exc), 400

        if error:
            pass
        elif descuento < 0:
            error = "El descuento no puede ser negativo"
        elif modo_cobro == "credito" and (
            metodo1_val or metodo2_val or monto1 > 0 or monto2 > 0
        ):
            conn.close()
            return "El credito completo no debe registrar pagos", 400
        elif modo_cobro == "parcial" and metodo1_val == "":
            conn.close()
            return "El cobro parcial requiere al menos un pago", 400
        elif modo_cobro != "credito" and metodo1_val == "":
            error = "Debes seleccionar el metodo de pago principal"
        elif modo_cobro != "credito" and metodo1_val not in METODOS_PAGO_VALIDOS:
            error = "Metodo de pago principal invalido"
        elif modo_cobro != "credito" and monto1 <= 0:
            error = "El monto del pago 1 debe ser mayor a 0"
        elif metodo2_val and metodo2_val not in METODOS_PAGO_VALIDOS:
            error = "Metodo de pago 2 invalido"
        elif metodo2_val and monto2 < 0:
            error = "El monto del pago 2 no puede ser negativo"
        elif not metodo2_val and monto2 > 0:
            error = "Si colocas monto en pago 2, debes seleccionar el metodo"
        else:
            try:
                totales_cobro = calcular_totales_financieros_delivery(
                    items,
                    tasa,
                    descuento,
                    delivery_orden_usd,
                )
                repartidor_delivery_cobro = validar_repartidor_delivery_cobro(
                    cursor,
                    totales_cobro["delivery_usd"],
                    delivery_repartidor_id,
                )
            except ValueError as exc:
                conn.close()
                return str(exc), 400
            total_bs_final = totales_cobro["total_cliente_bs"]
            total_usd_final = totales_cobro["total_cliente_usd"]

            insertar_pago_1 = False
            insertar_pago_2 = False
            total_pagado_bs = 0.0
            total_pagado_usd = 0.0

            if modo_cobro != "credito":
                pago1_bs, pago1_usd = convertir_pago_equivalente(metodo1_val, monto1, tasa)
                total_pagado_bs = pago1_bs
                total_pagado_usd = pago1_usd

                insertar_pago_1 = bool(metodo1_val and monto1 > 0)
                insertar_pago_2 = bool(
                    metodo2_val and monto2 > 0 and pago1_usd + TOLERANCIA_COBRO < total_usd_final
                )
                if insertar_pago_2:
                    pago2_bs, pago2_usd = convertir_pago_equivalente(metodo2_val, monto2, tasa)
                    total_pagado_bs += pago2_bs
                    total_pagado_usd += pago2_usd

            saldo_cxc_usd = 0.0
            if modo_cobro == "credito":
                saldo_cxc_usd = total_usd_final
            elif modo_cobro == "parcial":
                saldo_cxc_usd = round(max(total_usd_final - total_pagado_usd, 0.0), 2)

            if modo_cobro != "credito" and not insertar_pago_1:
                if modo_cobro == "parcial":
                    conn.close()
                    return "El cobro parcial requiere al menos un pago", 400
                error = "No hay pagos validos para registrar"
            elif modo_cobro == "pagado" and total_pagado_bs + TOLERANCIA_COBRO < total_bs_final:
                error = "Pago insuficiente"
            elif modo_cobro == "parcial" and total_pagado_usd <= TOLERANCIA_COBRO:
                conn.close()
                return "El cobro parcial requiere al menos un pago", 400
            elif modo_cobro == "parcial" and saldo_cxc_usd <= TOLERANCIA_COBRO:
                conn.close()
                return "El cobro parcial requiere saldo pendiente. Usa modo pagado.", 400
            elif modo_cobro == "credito" and saldo_cxc_usd <= TOLERANCIA_COBRO:
                conn.close()
                return "El credito completo requiere saldo pendiente", 400
            else:
                fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
                fecha_cobro = fecha if modo_cobro != "credito" else None
                cliente_id_orden = cliente_cxc[0] if cliente_cxc else cliente_id_actual
                cliente_nombre_orden = cliente_cxc[1] if cliente_cxc else o[5]

                try:
                    validar_recobro_cxc(cursor, orden_id)
                    validar_recobro_delivery(cursor, orden_id)
                except ValueError as exc:
                    conn.close()
                    return str(exc), 400

                try:
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
                        SET estado='cerrada',
                            descuento=?,
                            fecha_venta=?,
                            fecha_cobro=?,
                            tasa_cobro=?,
                            subtotal_usd=?,
                            descuento_bs_snapshot=?,
                            total_usd=?,
                            total_bs=?,
                            venta_restaurante_usd=?,
                            delivery_usd=?,
                            total_cliente_usd=?,
                            cliente_id=?,
                            cliente=?
                        WHERE id=?
                          AND cierre_id IS NULL
                          AND estado IN ('abierta', 'en cocina', 'listo', 'cerrada')
                        """,
                        (
                            totales_cobro["descuento_bs"],
                            fecha,
                            fecha_cobro,
                            totales_cobro["tasa"],
                            totales_cobro["subtotal_snapshot_usd"],
                            totales_cobro["descuento_bs"],
                            totales_cobro["total_usd"],
                            totales_cobro["total_bs"],
                            totales_cobro["snapshot_venta_restaurante_usd"],
                            totales_cobro["snapshot_delivery_usd"],
                            totales_cobro["snapshot_total_cliente_usd"],
                            cliente_id_orden,
                            cliente_nombre_orden,
                            orden_id,
                        ),
                    )

                    if getattr(cursor, "rowcount", 0) == 0:
                        conn.rollback()
                        conn.close()
                        return "Esta orden ya fue cerrada o pertenece a un cierre de jornada"

                    if saldo_cxc_usd > TOLERANCIA_COBRO:
                        crear_cuenta_por_cobrar_inicial(
                            cursor,
                            orden_id,
                            cliente_cxc[0],
                            cliente_cxc[1],
                            saldo_cxc_usd,
                            fecha,
                            session.get("usuario_id"),
                        )

                    if totales_cobro["delivery_usd"] > TOLERANCIA_COBRO:
                        insertar_cargo_delivery(
                            cursor,
                            orden_id,
                            repartidor_delivery_cobro,
                            totales_cobro["delivery_usd"],
                            fecha,
                            session.get("usuario_id"),
                        )

                    if estado == "cerrada" and emergencia_activa(orden_id):
                        registrar_auditoria_emergencia(
                            cursor,
                            orden_id,
                            "volver_a_cobrar_emergencia",
                            "Pagos reemplazados durante edicion de emergencia",
                        )

                    descontar_inventario_por_orden(cursor, orden_id)

                    conn.commit()
                    conn.close()
                except Exception:
                    conn.rollback()
                    conn.close()
                    raise
                if estado == "cerrada":
                    desactivar_emergencia_sesion(orden_id)
                return redirect("/")

    clientes_cobro = listar_clientes_activos(cursor)
    conn.close()
    clientes_cobro_json = json.dumps(
        [cliente_json_desde_fila(cliente) for cliente in clientes_cobro],
        ensure_ascii=False,
    )
    modo_cobro_seguro = modo_cobro_val if modo_cobro_val in MODOS_COBRO_VALIDOS else "pagado"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--gris-fondo); color: var(--texto); }}
    .contenedor {{ width: 95%; max-width: 720px; margin: 18px auto; background: var(--panel); color: var(--texto); padding: 24px; border-radius: 16px; box-shadow: var(--sombra); border: 1px solid var(--borde); }}
    .titulo {{ text-align: center; font-size: 26px; font-weight: 900; color:var(--verde-neko); text-shadow:0 0 8px rgba(61,220,132,0.10); }}
    .numero {{ text-align: right; font-size: 18px; margin-bottom: 10px; }}
    .sep {{ border-top: 1px dashed var(--borde); margin: 15px 0; }}
    .total {{ font-size: 20px; font-weight: bold; text-align: right; }}
    input, select {{ width: 100%; padding: 12px; margin: 5px 0; border-radius: 8px; border: 1px solid var(--borde); font-size: 16px; box-sizing: border-box; background:var(--panel-secundario); color:var(--texto); }}
    .btn {{ width: 100%; padding: 15px; margin-top: 10px; border: none; border-radius: 8px; font-size: 18px; cursor: pointer; }}
    .confirmar {{ background: var(--verde-neko); color: #0F1115; }}
    .volver {{ background: var(--panel-secundario); color: var(--texto); text-decoration:none; display:block; text-align:center; padding:15px; border-radius:8px; border:1px solid var(--borde); }}
    .error {{ background:#fdecea; color:#c0392b; padding:12px; border-radius:8px; margin-bottom:12px; }}
    .metodos-grid {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; margin:8px 0 10px; }}
    .metodo-btn {{ min-height:60px; padding:12px; border:2px solid var(--borde); border-radius:10px; background:var(--panel-secundario); color:var(--texto); font-size:16px; font-weight:900; cursor:pointer; box-shadow:0 4px 12px rgba(0,0,0,0.20); transition:background 0.16s ease, border-color 0.16s ease, color 0.16s ease, transform 0.16s ease; }}
    .metodo-btn:hover {{ transform:translateY(-1px); border-color:var(--verde-neko); }}
    .metodo-btn.activo {{ border-color:var(--verde-neko); background:var(--verde-neko); color:#0F1115; }}
    .metodo-btn.sin-metodo {{ background:#242424; color:var(--texto-secundario); }}
    .metodo-btn.sin-metodo.activo {{ border-color:var(--texto-secundario); background:#3a3a3a; color:white; }}
    .modo-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin:8px 0 12px; }}
    .modo-btn {{ min-height:66px; padding:12px; border:2px solid var(--borde); border-radius:10px; background:var(--panel-secundario); color:var(--texto); font-size:16px; font-weight:900; cursor:pointer; }}
    .modo-btn.activo {{ border-color:var(--verde-neko); background:var(--verde-neko); color:#0F1115; }}
    .modo-ayuda {{ color:var(--texto-secundario); font-size:14px; margin:4px 0 0; }}
    .saldo-panel {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin:12px 0; }}
    .saldo-box {{ background:var(--panel-secundario); border:1px solid var(--borde); border-radius:8px; padding:12px; }}
    .saldo-label {{ color:var(--texto-secundario); font-size:13px; font-weight:700; }}
    .saldo-valor {{ font-size:20px; font-weight:900; margin-top:4px; }}
    .desglose-cobro {{ background:var(--panel-secundario); border:1px solid var(--borde); border-radius:10px; padding:12px; margin:12px 0; }}
    .desglose-fila {{ display:flex; justify-content:space-between; gap:10px; padding:4px 0; }}
    .desglose-fila b {{ color:var(--verde-neko); }}
    .cliente-panel {{ border:1px solid var(--borde); border-radius:10px; padding:14px; background:var(--panel-secundario); margin:12px 0; }}
    .cliente-panel.oculto, .nuevo-cliente.oculto, .pagos-panel.oculto, .cliente-busqueda.oculto, .cliente-seleccion.oculto {{ display:none; }}
    .cliente-resultados {{ display:grid; gap:8px; margin:10px 0; }}
    .cliente-opcion {{ width:100%; min-height:62px; text-align:left; border:1px solid var(--borde); border-radius:8px; background:#242424; color:var(--texto); padding:11px 12px; box-shadow:none; }}
    .cliente-opcion b {{ display:block; font-size:16px; }}
    .cliente-opcion small {{ display:block; color:var(--texto-secundario); margin-top:4px; }}
    .cliente-seleccion {{ border:1px solid var(--verde-neko); background:#11251a; border-radius:8px; padding:12px; margin:10px 0; }}
    .cliente-seleccion small {{ color:var(--texto-secundario); display:block; margin-top:4px; }}
    .accion-secundaria {{ background:#242424; color:var(--texto); border:1px solid var(--borde); }}
    .nuevo-cliente {{ margin-top:10px; }}
    .mensaje-ui {{ color:var(--texto-secundario); font-size:14px; min-height:18px; }}
    @media (max-width: 520px) {{ .metodos-grid {{ grid-template-columns:1fr; }} }}
    @media (max-width: 520px) {{ .modo-grid, .saldo-panel {{ grid-template-columns:1fr; }} }}
    </style>
    </head>
    <body>
    <div class="contenedor">
    <div class="titulo">💵 Cobrar</div>
    <div class="numero">Orden {texto_numero_orden(o[1])}</div>
    <div>
    <b>👤 Cliente:</b> {o[5] if o[5] else '-'}<br>
    <b>Tipo:</b> {o[3]}<br>
    <b>👩 Mesonera:</b> {o[9] if o[9] else '-'}
    </div>
    <div class="sep"></div>
    <div class="desglose-cobro">
        <div class="desglose-fila"><span>Consumo Neko Wok</span><b>${total_usd:.2f}</b></div>
        <div class="desglose-fila"><span>Delivery</span><b>${totales_cobro["delivery_usd"]:.2f}</b></div>
        <div class="desglose-fila"><span>Total a pagar</span><b>${total_cliente_usd:.2f}</b></div>
    </div>
    <div class="total">USD total cliente: ${total_cliente_usd:.2f}</div>
    <div class="total">Bs total cliente: {total_cliente_bs:.2f}</div>
    <div class="total">Tasa: Bs {round(tasa, 2)}</div>
    <div class="total">Total final Bs: {round(total_bs_final, 2)}</div>
    <div class="sep"></div>
    {"<div class='error'>" + error + "</div>" if error else ""}
    <form method="post" id="formCobro">
    <input type="hidden" name="modo_cobro" id="modo_cobro" value="{modo_cobro_seguro}">
    <h3>Modo de cobro</h3>
    <div class="modo-grid">
        <button type="button" class="modo-btn" data-modo="pagado">Pagado</button>
        <button type="button" class="modo-btn" data-modo="parcial">Parcial</button>
        <button type="button" class="modo-btn" data-modo="credito">Cr&eacute;dito</button>
    </div>
    <div id="modoAyuda" class="modo-ayuda"></div>
    <div id="clientePanel" class="cliente-panel oculto">
        <label>Cliente para cuenta por cobrar</label>
        <input type="hidden" name="cliente_id" id="cliente_id" value="{html_lib.escape(cliente_id_val or '', quote=True)}">
        <div id="clienteSeleccion" class="cliente-seleccion oculto">
            <div><b>Cliente seleccionado</b></div>
            <div id="clienteSeleccionNombre"></div>
            <small id="clienteSeleccionDetalle"></small>
            <button type="button" class="btn accion-secundaria" id="cambiarCliente">Cambiar cliente</button>
        </div>
        <div id="clienteBusqueda" class="cliente-busqueda">
            <input type="search" id="clienteBuscar" placeholder="Buscar por nombre, tel&eacute;fono o documento" autocomplete="off">
            <div id="clienteResultados" class="cliente-resultados"></div>
        </div>
        <button type="button" class="btn accion-secundaria" id="mostrarNuevoCliente">+ Nuevo cliente</button>
        <div id="nuevoClientePanel" class="nuevo-cliente oculto">
            <input id="nuevoClienteNombre" placeholder="Nombre del cliente">
            <input id="nuevoClienteTelefono" placeholder="Tel&eacute;fono">
            <input id="nuevoClienteDocumento" placeholder="Documento">
            <input id="nuevoClienteNotas" placeholder="Notas">
            <button type="button" class="btn accion-secundaria" id="guardarNuevoCliente">Guardar cliente</button>
            <div id="clienteMensaje" class="mensaje-ui"></div>
        </div>
    </div>
    <div class="saldo-panel">
        <div class="saldo-box">
            <div class="saldo-label">Total</div>
            <div class="saldo-valor" id="resumenTotal">$0.00</div>
        </div>
        <div class="saldo-box">
            <div class="saldo-label">Pagado ahora</div>
            <div class="saldo-valor" id="resumenPagado">$0.00</div>
        </div>
        <div class="saldo-box">
            <div class="saldo-label">Saldo estimado</div>
            <div class="saldo-valor" id="resumenSaldo">$0.00</div>
        </div>
    </div>
    <div id="pagosPanel" class="pagos-panel">
    <h3>💳 Pago 1</h3>
    <input type="hidden" name="metodo1" id="metodo1" value="{metodo1_val}">
    <div class="metodos-grid" data-metodo-grupo="metodo1">
        <button type="button" class="metodo-btn" data-metodo-target="metodo1" data-metodo="punto_venta">Punto de venta</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo1" data-metodo="bs_pago_movil">Pago m&oacute;vil</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo1" data-metodo="bs_efectivo">Efectivo Bs</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo1" data-metodo="usd">Efectivo USD</button>
    </div>
    <input name="monto1" id="monto1" type="number" step="0.01" min="0.01" value="{monto1_val}" placeholder="Monto" required>
    <input name="ref1" id="ref1" value="{ref1_val}" placeholder="Referencia">
    <div class="sep"></div>
    <h3>💳 Pago 2 (opcional)</h3>
    <input type="hidden" name="metodo2" id="metodo2" value="{metodo2_val}">
    <div class="metodos-grid" data-metodo-grupo="metodo2">
        <button type="button" class="metodo-btn sin-metodo" data-metodo-target="metodo2" data-metodo="">Sin m&eacute;todo</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo2" data-metodo="punto_venta">Punto de venta</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo2" data-metodo="bs_pago_movil">Pago m&oacute;vil</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo2" data-metodo="bs_efectivo">Efectivo Bs</button>
        <button type="button" class="metodo-btn" data-metodo-target="metodo2" data-metodo="usd">Efectivo USD</button>
    </div>
    <input name="monto2" id="monto2" type="number" step="0.01" min="0" value="{monto2_val}" placeholder="Monto">
    <input name="ref2" id="ref2" value="{ref2_val}" placeholder="Referencia">
    </div>
    <div class="sep"></div>
    <label>Descuento (Bs)</label>
    <input name="descuento" id="descuento" type="number" step="0.01" value="{descuento_val}">
    <button class="btn confirmar">💵 Confirmar pago</button>
    </form>
    <a href="/orden/{orden_id}" class="volver">🏠 Volver</a>
    </div>
    <script>
    const formCobro = document.getElementById("formCobro");
    const modoCobro = document.getElementById("modo_cobro");
    const clientePanel = document.getElementById("clientePanel");
    const clienteId = document.getElementById("cliente_id");
    const clienteBuscar = document.getElementById("clienteBuscar");
    const clienteResultados = document.getElementById("clienteResultados");
    const clienteBusqueda = document.getElementById("clienteBusqueda");
    const clienteSeleccion = document.getElementById("clienteSeleccion");
    const clienteSeleccionNombre = document.getElementById("clienteSeleccionNombre");
    const clienteSeleccionDetalle = document.getElementById("clienteSeleccionDetalle");
    const cambiarCliente = document.getElementById("cambiarCliente");
    const pagosPanel = document.getElementById("pagosPanel");
    const modoAyuda = document.getElementById("modoAyuda");
    const metodo1 = document.getElementById("metodo1");
    const monto1 = document.getElementById("monto1");
    const ref1 = document.getElementById("ref1");
    const metodo2 = document.getElementById("metodo2");
    const monto2 = document.getElementById("monto2");
    const ref2 = document.getElementById("ref2");
    const descuento = document.getElementById("descuento");
    const resumenTotal = document.getElementById("resumenTotal");
    const resumenPagado = document.getElementById("resumenPagado");
    const resumenSaldo = document.getElementById("resumenSaldo");
    const nuevoClientePanel = document.getElementById("nuevoClientePanel");
    const mostrarNuevoCliente = document.getElementById("mostrarNuevoCliente");
    const guardarNuevoCliente = document.getElementById("guardarNuevoCliente");
    const clienteMensaje = document.getElementById("clienteMensaje");
    const nuevoClienteNombre = document.getElementById("nuevoClienteNombre");
    const nuevoClienteTelefono = document.getElementById("nuevoClienteTelefono");
    const nuevoClienteDocumento = document.getElementById("nuevoClienteDocumento");
    const nuevoClienteNotas = document.getElementById("nuevoClienteNotas");
    let clientesActivos = {clientes_cobro_json};
    let clienteSeleccionado = null;
    let clienteBusquedaTimer = null;
    const subtotalRestauranteUSD = {round(totales_cobro["subtotal_restaurante_usd"], 2)};
    const deliveryUSD = {round(totales_cobro["delivery_usd"], 2)};
    const totalUSD = {round(total_cliente_usd, 2)};
    const tasa = {round(tasa, 6)};

    function metodoEsUSD(metodo) {{
        return metodo === "usd";
    }}

    function metodoEsBs(metodo) {{
        return metodo === "punto_venta" || metodo === "bs_pago_movil" || metodo === "bs_efectivo" || metodo === "pago_movil";
    }}

    function numero(valor) {{
        const n = parseFloat(String(valor || "0").replace(",", "."));
        return Number.isFinite(n) ? n : 0;
    }}

    function formatoUSD(valor) {{
        return "$" + Math.max(valor, 0).toFixed(2);
    }}

    function totalFinalUSD() {{
        const descuentoBs = Math.max(numero(descuento.value), 0);
        const restauranteNeto = Math.max(subtotalRestauranteUSD - (tasa ? descuentoBs / tasa : 0), 0);
        return restauranteNeto + deliveryUSD;
    }}

    function totalFinalBs() {{
        return totalFinalUSD() * tasa;
    }}

    function pagoEnUSD(metodo, monto) {{
        const valor = Math.max(numero(monto), 0);
        if (metodoEsUSD(metodo)) {{
            return valor;
        }}
        if (metodoEsBs(metodo)) {{
            return tasa ? valor / tasa : 0;
        }}
        return 0;
    }}

    function pago1EnUSD() {{
        return pagoEnUSD(metodo1.value, monto1.value);
    }}

    function pagoTotalEnUSD() {{
        if (modoCobro.value === "credito") {{
            return 0;
        }}
        return pago1EnUSD() + pagoEnUSD(metodo2.value, monto2.value);
    }}

    function saldoEstimadoUSD() {{
        if (modoCobro.value === "credito") {{
            return totalFinalUSD();
        }}
        return Math.max(totalFinalUSD() - pagoTotalEnUSD(), 0);
    }}

    function recalcularPago2() {{
        if (modoCobro.value === "parcial" || modoCobro.value === "credito") {{
            actualizarResumenCobro();
            return;
        }}
        const restanteUSD = Math.max(totalFinalUSD() - pago1EnUSD(), 0);
        if (restanteUSD <= 0) {{
            monto2.value = "0.00";
            actualizarResumenCobro();
            return;
        }}
        if (!metodo2.value) {{
            actualizarResumenCobro();
            return;
        }}
        if (metodoEsUSD(metodo2.value)) {{
            monto2.value = restanteUSD.toFixed(2);
        }} else if (metodoEsBs(metodo2.value)) {{
            monto2.value = (restanteUSD * tasa).toFixed(2);
        }}
        actualizarResumenCobro();
    }}

    function actualizarResumenCobro() {{
        const total = totalFinalUSD();
        const pagado = pagoTotalEnUSD();
        resumenTotal.textContent = formatoUSD(total);
        resumenPagado.textContent = formatoUSD(pagado);
        resumenSaldo.textContent = formatoUSD(saldoEstimadoUSD());
    }}

    function actualizarBotonesMetodo(targetId) {{
        const input = document.getElementById(targetId);
        document.querySelectorAll('[data-metodo-target="' + targetId + '"]').forEach(function(btn) {{
            btn.classList.toggle("activo", btn.dataset.metodo === input.value);
        }});
    }}

    function actualizarBotonesModo() {{
        document.querySelectorAll(".modo-btn").forEach(function(btn) {{
            btn.classList.toggle("activo", btn.dataset.modo === modoCobro.value);
        }});
    }}

    function limpiarPagosCredito() {{
        metodo1.value = "";
        metodo2.value = "";
        monto1.value = "0.00";
        monto2.value = "0.00";
        ref1.value = "";
        ref2.value = "";
        actualizarBotonesMetodo("metodo1");
        actualizarBotonesMetodo("metodo2");
    }}

    function setPagosDeshabilitados(deshabilitado) {{
        [metodo1, metodo2, monto1, monto2, ref1, ref2].forEach(function(input) {{
            input.disabled = deshabilitado;
        }});
        document.querySelectorAll(".metodo-btn").forEach(function(btn) {{
            btn.disabled = deshabilitado;
        }});
        monto1.required = !deshabilitado;
        pagosPanel.classList.toggle("oculto", deshabilitado);
    }}

    function aplicarModo(modo, limpiarCredito) {{
        modoCobro.value = modo;
        actualizarBotonesModo();
        clientePanel.classList.toggle("oculto", modo === "pagado");
        if (modo === "credito") {{
            if (limpiarCredito) {{
                limpiarPagosCredito();
            }}
            setPagosDeshabilitados(true);
            modoAyuda.textContent = "No se recibe dinero ahora. El total queda pendiente para el cliente.";
        }} else {{
            setPagosDeshabilitados(false);
            modoAyuda.textContent = modo === "parcial"
                ? "Recibe una parte ahora y deja el resto como saldo por cobrar."
                : "Cierra la venta con el pago completo recibido.";
        }}
        recalcularPago2();
        actualizarResumenCobro();
    }}

    function seleccionarMetodo(targetId, valor) {{
        const input = document.getElementById(targetId);
        input.value = valor;
        actualizarBotonesMetodo(targetId);

        if (targetId === "metodo1") {{
            if (metodoEsUSD(valor)) {{
                monto1.value = totalFinalUSD().toFixed(2);
            }} else if (metodoEsBs(valor)) {{
                monto1.value = totalFinalBs().toFixed(2);
            }}
        }}

        recalcularPago2();
    }}

    function detalleCliente(cliente) {{
        return [cliente.telefono, cliente.documento].filter(Boolean).join(" · ");
    }}

    function clienteSeleccionadoTexto() {{
        return clienteSeleccionado ? clienteSeleccionado.nombre : "";
    }}

    function mostrarClienteSeleccionado(cliente) {{
        clienteSeleccionado = cliente;
        clienteId.value = String(cliente.id);
        clienteSeleccionNombre.textContent = cliente.nombre;
        clienteSeleccionDetalle.textContent = detalleCliente(cliente);
        clienteSeleccion.classList.remove("oculto");
        clienteBusqueda.classList.add("oculto");
        clienteBuscar.value = "";
        clienteResultados.innerHTML = "";
    }}

    function limpiarClienteSeleccionado() {{
        clienteSeleccionado = null;
        clienteId.value = "";
        clienteSeleccion.classList.add("oculto");
        clienteBusqueda.classList.remove("oculto");
        clienteBuscar.focus();
        renderClientes(clientesActivos.slice(0, 8));
    }}

    function botonCliente(cliente) {{
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cliente-opcion";
        const detalle = detalleCliente(cliente);
        btn.innerHTML = "<b></b><small></small>";
        btn.querySelector("b").textContent = cliente.nombre;
        btn.querySelector("small").textContent = detalle || "Sin telefono/documento";
        btn.addEventListener("click", function() {{
            mostrarClienteSeleccionado(cliente);
        }});
        return btn;
    }}

    function renderClientes(clientes) {{
        clienteResultados.innerHTML = "";
        if (!clientes.length) {{
            const vacio = document.createElement("div");
            vacio.className = "mensaje-ui";
            vacio.textContent = "No hay clientes activos para esa busqueda.";
            clienteResultados.appendChild(vacio);
            return;
        }}
        clientes.slice(0, 8).forEach(function(cliente) {{
            clienteResultados.appendChild(botonCliente(cliente));
        }});
    }}

    async function buscarClientesApi(q) {{
        const response = await fetch("/api/clientes?q=" + encodeURIComponent(q));
        const data = await response.json();
        if (!response.ok || !data.ok) {{
            throw new Error(data.error || "No se pudo buscar clientes.");
        }}
        clientesActivos = data.clientes || [];
        renderClientes(clientesActivos);
    }}

    function buscarClientesConDebounce() {{
        clearTimeout(clienteBusquedaTimer);
        const q = clienteBuscar.value.trim();
        clienteBusquedaTimer = setTimeout(function() {{
            if (!q) {{
                renderClientes(clientesActivos.slice(0, 8));
                return;
            }}
            buscarClientesApi(q).catch(function() {{
                clienteResultados.innerHTML = '<div class="mensaje-ui">No se pudo buscar clientes.</div>';
            }});
        }}, 250);
    }}

    function agregarClienteLocal(cliente) {{
        clientesActivos = clientesActivos.filter(function(actual) {{
            return String(actual.id) !== String(cliente.id);
        }});
        clientesActivos.unshift(cliente);
        mostrarClienteSeleccionado(cliente);
    }}

    document.querySelectorAll(".modo-btn").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            aplicarModo(btn.dataset.modo, btn.dataset.modo === "credito");
        }});
    }});

    document.querySelectorAll(".metodo-btn").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            seleccionarMetodo(btn.dataset.metodoTarget, btn.dataset.metodo || "");
        }});
    }});

    mostrarNuevoCliente.addEventListener("click", function() {{
        nuevoClientePanel.classList.toggle("oculto");
        clienteMensaje.textContent = "";
        if (!nuevoClientePanel.classList.contains("oculto")) {{
            nuevoClienteNombre.focus();
        }}
    }});

    guardarNuevoCliente.addEventListener("click", async function() {{
        clienteMensaje.textContent = "";
        const nombre = nuevoClienteNombre.value.trim();
        if (!nombre) {{
            clienteMensaje.textContent = "El nombre del cliente es obligatorio.";
            return;
        }}
        guardarNuevoCliente.disabled = true;
        try {{
            const response = await fetch("/api/clientes", {{
                method: "POST",
                headers: {{"Content-Type": "application/json"}},
                body: JSON.stringify({{
                    nombre: nombre,
                    telefono: nuevoClienteTelefono.value.trim(),
                    documento: nuevoClienteDocumento.value.trim(),
                    notas: nuevoClienteNotas.value.trim()
                }})
            }});
            const data = await response.json();
            if (!response.ok || !data.ok) {{
                clienteMensaje.textContent = data.error || "No se pudo guardar el cliente.";
                return;
            }}
            agregarClienteLocal(data.cliente);
            nuevoClienteNombre.value = "";
            nuevoClienteTelefono.value = "";
            nuevoClienteDocumento.value = "";
            nuevoClienteNotas.value = "";
            nuevoClientePanel.classList.add("oculto");
            clienteMensaje.textContent = "Cliente seleccionado.";
        }} catch (err) {{
            clienteMensaje.textContent = "No se pudo guardar el cliente.";
        }} finally {{
            guardarNuevoCliente.disabled = false;
        }}
    }});

    formCobro.addEventListener("submit", function(event) {{
        const modo = modoCobro.value;
        const total = totalFinalUSD();
        const pagado = pagoTotalEnUSD();
        const saldo = saldoEstimadoUSD();
        const cliente = clienteSeleccionadoTexto();

        if ((modo === "parcial" || modo === "credito") && !clienteId.value) {{
            event.preventDefault();
            alert("Selecciona un cliente para registrar el saldo pendiente.");
            return;
        }}
        if (modo === "parcial" && pagado <= 0.0001) {{
            event.preventDefault();
            alert("Ingresa al menos un pago para usar cobro parcial.");
            return;
        }}
        if (modo === "parcial" && saldo <= 0.0001) {{
            event.preventDefault();
            alert("El pago cubre el total. Usa el modo Pagado.");
            return;
        }}
        if (modo === "credito") {{
            if (!confirm("Esta venta por " + formatoUSD(total) + " quedara completamente pendiente para " + cliente + ". Confirmar?")) {{
                event.preventDefault();
            }}
            return;
        }}
        if (modo === "parcial") {{
            if (!confirm("Esta venta dejara un saldo pendiente de " + formatoUSD(saldo) + " para " + cliente + ". Confirmar?")) {{
                event.preventDefault();
            }}
        }}
    }});

    actualizarBotonesMetodo("metodo1");
    actualizarBotonesMetodo("metodo2");
    clienteBuscar.addEventListener("input", buscarClientesConDebounce);
    cambiarCliente.addEventListener("click", limpiarClienteSeleccionado);
    monto1.addEventListener("input", actualizarResumenCobro);
    monto2.addEventListener("input", actualizarResumenCobro);
    descuento.addEventListener("input", recalcularPago2);
    const clienteInicial = clientesActivos.find(function(cliente) {{
        return String(cliente.id) === String(clienteId.value || "");
    }});
    if (clienteInicial) {{
        mostrarClienteSeleccionado(clienteInicial);
    }} else {{
        renderClientes(clientesActivos.slice(0, 8));
    }}
    aplicarModo(modoCobro.value || "pagado", false);
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
    <h2>💲 Cambiar tasa</h2>
    <p>Tasa actual: <b>{tasa_actual}</b></p>
    <form method="post">
        <input name="tasa" placeholder="Nueva tasa" style="padding:12px; width:100%;">
        <button style="padding:12px 20px; background:#15803d; color:white; border:none; border-radius:8px;">💾 Guardar</button>
    </form>
    <a href="/" class="volver" style="background:#1a6b4a; margin-top:15px;">🏠 Volver</a>
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
    if not usuario_puede_reportes():
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
            if orden["cierre_id"] is not None and usuario_es_master():
                volver_url = f"/reportes?{urlencode({'desde': desde, 'hasta': hasta})}"
                accion_revertir = f"""
                <form method="post" action="/revertir_orden_cierre/{orden["orden_id"]}" class="form-revertir-cierre" style="margin:0;">
                    <input type="hidden" name="clave" value="">
                    <input type="hidden" name="volver" value="{volver_url}">
                    <button type="submit" style="background:#DC2626; color:white; border:none; border-radius:8px; padding:9px 11px; cursor:pointer; width:auto; min-height:38px; font-weight:700;">🧨 Revertir orden</button>
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

    dashboard_url = f"/dashboard?{urlencode({'desde': desde, 'hasta': hasta})}"
    boton_exportar = ""
    if usuario_es_master():
        export_url = f"/exportar_reporte?{urlencode({'desde': desde, 'hasta': hasta})}"
        boton_exportar = f'<a class="btn-link btn-excel" href="{export_url}">📤 Exportar Excel</a>'

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ padding:18px; }}
    .filtros, .metricas, .bloque {{ background:var(--tarjeta); color:var(--texto); border:1px solid var(--borde); border-radius:14px; padding:18px; box-shadow:var(--sombra-suave); margin-bottom:16px; }}
    .filtros form {{ display:grid; grid-template-columns: 1fr 1fr auto auto; gap:12px; align-items:end; }}
    .metricas {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }}
    .metrica {{ background:var(--panel-secundario); border:1px solid var(--borde); padding:14px; border-radius:12px; }}
    .metrica small {{ display:block; color:var(--texto-secundario); font-weight:700; margin-bottom:6px; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
    .metrica b {{ font-size:22px; color:var(--carbon); }}
    button, .btn-link {{ border:none; border-radius:10px; padding:13px 16px; color:#0F1115; background:var(--verde-neko); text-decoration:none; font-weight:900; min-height:48px; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; }}
    .btn-excel {{ background:var(--azul); color:white; }}
    .btn-dashboard {{ background:var(--azul); color:white; }}
    table {{ width:100%; border-collapse:collapse; background:var(--tarjeta); border-radius:10px; overflow:hidden; }}
    th, td {{ border-bottom:1px solid var(--borde); padding:11px 14px; text-align:left; }}
    th {{ background:var(--panel-secundario); color:var(--texto-secundario); font-weight:800; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
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
                {boton_exportar}
            </form>
        </div>

        <div class="metricas">
            <div class="metrica"><small>Total vendido USD</small><b>$ {reporte["total_vendido_usd"]}</b></div>
            <div class="metrica"><small>Punto de venta Bs</small><b>Bs {reporte["total_punto_venta_bs"]}</b></div>
            <div class="metrica"><small>Pago m&oacute;vil Bs</small><b>Bs {reporte["total_pago_movil_bs"]}</b></div>
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
        ["Total punto de venta Bs", reporte["total_punto_venta_bs"]],
        ["Total Pago m&oacute;vil Bs", reporte["total_pago_movil_bs"]],
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

    nombre = f"reporte_neko_wok_{desde}_a_{hasta}.xlsx"
    respuesta = Response(
        contenido,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@app.route("/dashboard")
def dashboard():
    if not usuario_puede_reportes():
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
    .filtros, .panel-dashboard {{ background:var(--tarjeta); color:var(--texto); border:1px solid var(--borde); border-radius:14px; padding:18px; box-shadow:var(--sombra-suave); margin-bottom:16px; }}
    .filtros form {{ display:grid; grid-template-columns: 1fr 1fr auto auto; gap:12px; align-items:end; }}
    .grid-dashboard {{ display:grid; grid-template-columns: repeat(2, 1fr); gap:16px; }}
    .resumen-top {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:16px; }}
    .metrica {{ background:var(--panel-secundario); border:1px solid var(--borde); padding:16px; border-radius:12px; box-shadow:var(--sombra-suave); }}
    .metrica small {{ display:block; color:var(--texto-secundario); font-weight:700; margin-bottom:6px; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
    .metrica b {{ font-size:22px; color:var(--carbon); }}
    button, .btn-link {{ border:none; border-radius:10px; padding:13px 16px; color:#0F1115; background:var(--verde-neko); text-decoration:none; font-weight:900; min-height:48px; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; }}
    .btn-reportes {{ background:var(--azul); color:white; }}
    .fila-barra {{ display:grid; grid-template-columns: 240px 1fr; gap:12px; align-items:center; padding:10px 0; border-bottom:1px solid var(--borde); }}
    .fila-barra:last-child {{ border-bottom:none; }}
    .barra {{ height:16px; background:var(--panel-secundario); border-radius:999px; overflow:hidden; }}
    .barra span {{ display:block; height:100%; background:var(--verde-neko); border-radius:999px; }}
    .vacio {{ color:var(--texto-secundario); padding:12px 0; font-size:14px; }}
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
        mensaje = "<h2 style='color:#dc2626;'>No hay ordenes cerradas para esta jornada.</h2>"
    else:
        mensaje = "<h2 style='color:#1a6b4a;'>✅ Jornada lista para cierre</h2>"

    boton = ""
    if ordenes_activas == 0 and cantidad_ordenes_cerradas > 0:
        boton = '<br><br><a href="/cerrar_jornada" class="volver" style="background:#3DDC84; color:#0F1115; padding:14px 20px; border-radius:12px; font-weight:800; text-decoration:none;">🔒 Confirmar cierre de jornada</a>'

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
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f7f5f0; padding: 20px; }}
    .card {{ max-width: 980px; margin: auto; background: white; padding: 25px; border-radius: 16px; box-shadow: var(--sombra); border: 1px solid #e5e0d8; }}
    .bloque {{ background: #f0fdf4; padding: 14px; border-radius: 12px; margin-bottom: 14px; border: 1px solid #bbf7d0; }}
    .titulo-bloque {{ font-size: 17px; font-weight: 800; margin-bottom: 10px; color: #1a6b4a; }}
    .dato {{ margin: 6px 0; font-size: 16px; }}
    .volver {{ display:inline-block; margin-top:20px; padding:12px 18px; background:var(--panel-secundario); color:var(--texto); text-decoration:none; border-radius:10px; font-weight:800; border:1px solid var(--borde); }}
    .tabla-wrap {{ overflow:auto; }}
    table {{ width:100%; border-collapse: collapse; background:white; border-radius:10px; overflow:hidden; }}
    th, td {{ border-bottom:1px solid #e5e7eb; padding:10px 14px; text-align:left; }}
    th {{ background:#f0fdf4; color:#1a6b4a; font-weight:800; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
    .vacio {{ color:#9ca3af; }}
    </style>
    </head>
    <body>
    <div class="card">
        <h1>📦 Cierre del Día</h1>
        {mensaje}

        <div class="dato"><b>Inicio de jornada:</b> {resumen["inicio_jornada"]}</div>
        <div class="dato"><b>Ordenes cerradas:</b> {cantidad_ordenes_cerradas}</div>

        <div class="bloque">
            <div class="titulo-bloque">💵 VENTAS</div>
            <div class="dato"><b>Total vendido en USD:</b> ${round(resumen["total_ventas_usd"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">💳 COBRADO</div>
            <div class="dato"><b>Punto de venta:</b> Bs {round(resumen["total_punto_venta_bs"], 2)}</div>
            <div class="dato"><b>Pago m&oacute;vil en Bs:</b> Bs {round(resumen["total_pago_movil_bs"], 2)}</div>
            <div class="dato"><b>Efectivo en Bs:</b> Bs {round(resumen["total_efectivo_bs"], 2)}</div>
            <div class="dato"><b>Efectivo en USD:</b> $ {round(resumen["total_efectivo_usd"], 2)}</div>
        </div>

        <div class="bloque">
            <div class="titulo-bloque">💲 TASA</div>
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
    .card {{ max-width: 760px; margin: auto; background: white; padding: 28px; border-radius: 16px; box-shadow: 0 8px 24px rgba(13,74,50,0.10); border: 1px solid #e5e0d8; }}
    h1 {{ margin-top: 0; color: #1a6b4a; }}
    .total {{ font-size: 20px; font-weight: 800; color: #1a6b4a; margin-bottom: 8px; }}
    .volver {{ display:inline-block; margin-top:20px; padding:12px 18px; background:var(--panel-secundario); color:var(--texto); text-decoration:none; border-radius:10px; font-weight:800; border:1px solid var(--borde); }}
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
        SELECT o.id, o.numero_orden, o.tipo, o.referencia, o.fecha_hora, u.nombre,
               COALESCE(o.observacion, '')
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
    cocina_links = '<a href="/cocina">🍳 Cocina</a>'
    if usuario_es_master():
        cocina_links = '<a href="/">🏠 Inicio</a>' + cocina_links
    if usuario_puede_ver_inventario():
        cocina_links += '<a href="/inventario">📦 Inventario</a>'
    if usuario_puede_produccion():
        cocina_links += '<a href="/produccion">👨‍🍳 Producción</a>'

    html = """
    <html>
    <head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; background:#0F1115; color:#F4F4F4; font-size:20px; margin:0; }
        .topbar { padding:10px 16px; background:#181B20; display:flex; justify-content:space-between; align-items:center; gap:10px; border-bottom:1px solid #31363F; box-shadow:0 4px 16px rgba(0,0,0,0.28); }
        .topbar-brand { font-weight:900; font-size:18px; display:flex; align-items:center; gap:8px; }
        .topbar-brand span { color:#3DDC84; text-shadow:0 0 8px rgba(61,220,132,0.12); }
        .topbar-user { font-size:14px; opacity:0.8; }
        .topbar a { color:white; text-decoration:none; background:#20242B; border:1px solid #31363F; padding:8px 12px; border-radius:8px; font-size:13px; font-weight:700; transition:background 0.18s ease, border-color 0.18s ease; }
        .topbar a:hover { background:#262B33; border-color:#3C4350; }
        .container { display:flex; }
        .col { width:50%; padding:10px; box-sizing:border-box; }
        .col-title { font-size:14px; font-weight:800; letter-spacing:2px; text-transform:uppercase; color:#B0B6BE; padding:8px 10px 4px; }
        .orden { border:3px solid #31363F; margin:8px; padding:16px; border-radius:14px; background:#20242B; box-shadow:0 10px 22px rgba(0,0,0,0.22); }
        .green { border-color: #3DDC84; background:#1C2A23; }
        .orange { border-color: #f97316; background:#1c0a00; }
        .red { border-color: #ef4444; background:#1c0000; animation: pulse-red 1.5s ease-in-out infinite; }
        @keyframes pulse-red { 0%,100% { border-color:#ef4444; } 50% { border-color:#fca5a5; } }
        .btn { padding:12px 16px; background:#3DDC84; color:#0F1115; border:none; font-size:16px; font-weight:800; border-radius:10px; cursor:pointer; width:100%; margin-top:10px; box-shadow:0 4px 12px rgba(0,0,0,0.20); }
        .btn:active { transform:scale(0.97); }
        .mesonera { color:#3DDC84; font-weight:700; font-size:16px; }
        .cocina-header { text-align:center; padding:10px; font-size:14px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:#B0B6BE; background:#181B20; border-bottom:1px solid #31363F; }
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
        <div class="topbar-brand">🐱 Neko <span>Wok</span> · 🍳 Cocina</div>
        <div style="display:flex; align-items:center; gap:10px;">
            <div class="topbar-user">👤 """ + usuario_activo() + """</div>
            <div style="display:flex; gap:6px;">
            """ + cocina_links + """
            <a href="/logout">🚪 Salir</a>
            </div>
        </div>
    </div>
    <div class="cocina-header">🍳 Estaciones de cocina · Vista en tiempo real</div>
    <div class="container">
        <div class="col">
            <div class="col-title">🍚 Estación Arroz</div>
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

        cursor.execute(
            """
            SELECT producto, COALESCE(indicacion, '')
            FROM orden_items
            WHERE orden_id=?
            """,
            (o[0],),
        )
        items = cursor.fetchall()
        tiene_arroz = any("Arroz chino" in i[0] for i in items)
        tiene_otro = any("Arroz chino" not in i[0] for i in items)
        lineas_comanda = agrupar_items_comanda(items, observacion=o[6])

        bloque = f"""
        <div class="orden {color_class}">
            <h2>Orden {texto_numero_orden(o[1])}</h2>
            <p>{o[2]} - {o[3]}</p>
            <p class="mesonera">👩 Mesonera: {(o[5] or '-').upper()}</p>
            <p>{int(minutos)} min</p>
        """

        for linea in lineas_comanda:
            linea_html = html_lib.escape(quitar_prefijo_cantidad_visual(linea)).replace("\n", "<br>")
            bloque += f"<p>{linea_html}</p>"

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
            <div class="col-title">🔥 Estación Caliente</div>
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


@app.route("/ordenes_listas")
def ordenes_listas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
               u.nombre, COUNT(i.id), COALESCE(SUM(i.precio), 0)
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        LEFT JOIN orden_items i ON i.orden_id = o.id
        WHERE o.estado = 'listo'
          AND o.cierre_id IS NULL
        GROUP BY o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente, u.nombre
        ORDER BY o.id DESC
        """
    )
    ordenes = cursor.fetchall()
    conn.close()

    filas = ""
    for o in ordenes:
        filas += f"""
        <tr>
            <td>{texto_numero_orden(o[1])}</td>
            <td>{html_lib.escape(o[2] or '')}</td>
            <td>{html_lib.escape(o[3] or '')}</td>
            <td>{html_lib.escape(o[4] or '')}</td>
            <td>{html_lib.escape(o[5] or '-')}</td>
            <td>{html_lib.escape(o[6] or '-')}</td>
            <td>{o[7]}</td>
            <td>$ {round(a_float(o[8]), 2)}</td>
            <td class="acciones">
                <a href="/orden/{o[0]}">Ver</a>
                <a class="cobrar" href="/cobrar/{o[0]}">Cobrar</a>
            </td>
        </tr>
        """

    if not filas:
        filas = '<tr><td colspan="9" class="vacio">No hay ordenes listas pendientes por cobrar.</td></tr>'

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ font-family:'Segoe UI', Arial, sans-serif; margin:0; background:var(--gris-fondo); color:var(--texto); }}
    .contenedor {{ width:95%; max-width:1100px; margin:18px auto; background:var(--panel); border:1px solid var(--borde); border-radius:14px; padding:18px; box-shadow:var(--sombra); }}
    h1 {{ margin-top:0; color:var(--verde-neko); }}
    table {{ width:100%; border-collapse:collapse; background:var(--tarjeta); }}
    th, td {{ padding:10px; border-bottom:1px solid var(--borde); text-align:left; font-size:14px; }}
    th {{ color:var(--texto-secundario); text-transform:uppercase; letter-spacing:0.5px; font-size:12px; }}
    .acciones {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .acciones a {{ color:white; background:#1d4ed8; padding:8px 10px; border-radius:8px; text-decoration:none; font-weight:800; }}
    .acciones a.cobrar {{ background:var(--verde-neko); color:#0F1115; }}
    .vacio {{ text-align:center; color:var(--texto-secundario); padding:26px; }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/">Inicio</a><a href="/cierre">Cierre</a>')}
    <div class="contenedor">
        <h1>Ordenes listas pendientes por cobrar</h1>
        <table>
            <thead>
                <tr>
                    <th>Orden</th>
                    <th>Fecha</th>
                    <th>Tipo</th>
                    <th>Referencia</th>
                    <th>Cliente</th>
                    <th>Mesonera</th>
                    <th>Items</th>
                    <th>Total</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>{filas}</tbody>
        </table>
    </div>
    </body>
    </html>
    """


@app.route("/ordenes_cocina")
def ordenes_cocina():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT o.id, o.numero_orden, o.tipo, o.cliente, o.referencia, u.nombre,
                   o.estado, o.reimpresion_token, COALESCE(o.observacion, '')
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
                SELECT producto, COALESCE(indicacion, '')
                FROM orden_items
                WHERE orden_id=?
                """,
                (o[0],),
            )
            items = [
                quitar_prefijo_cantidad_visual(item)
                for item in agrupar_items_comanda(cursor.fetchall(), observacion=o[8])
            ]

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
                    "observacion": o[8],
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
        SELECT o.numero_orden, o.tipo, o.referencia, o.cliente, u.nombre,
               o.venta_restaurante_usd, o.delivery_usd, o.total_cliente_usd
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
        SELECT producto, precio, COALESCE(indicacion, '')
        FROM orden_items
        WHERE orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()
    conn.close()

    items_agrupados, total = preparar_lineas_factura(items, o[5], o[6], o[7])
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
    .item span:first-child {{ white-space: pre-line; }}
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

    for item in items_agrupados:
        html += f"""
        <div class="item">
            <span>{html_lib.escape(quitar_prefijo_cantidad_visual(item["texto"]))}</span>
            <span>${round(item["precio_total"], 2)}</span>
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


@app.route("/api/tasa")
def api_tasa():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        tasa = obtener_tasa_actual(cursor)
        conn.close()
        print(f"/api/tasa responde tasa={tasa}")
        return jsonify({"ok": True, "tasa": tasa})
    except Exception as e:
        print("ERROR EN API_TASA:", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/facturas_pendientes")
def facturas_pendientes():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT o.id, o.numero_orden, o.tipo, o.cliente, o.referencia, u.nombre,
                   o.factura_reimpresion_token,
                   o.venta_restaurante_usd, o.delivery_usd, o.total_cliente_usd
            FROM ordenes o
            LEFT JOIN usuarios u ON o.usuario_id = u.id
            WHERE o.facturar = 1
              AND o.cierre_id IS NULL
            """
        )
        ordenes = cursor.fetchall()
        resultado = []

        if not ordenes:
            conn.close()
            return jsonify(resultado)

        orden_ids = [o[0] for o in ordenes]
        placeholders = ",".join("?" for _ in orden_ids)
        cursor.execute(
            f"""
            SELECT orden_id, producto, precio, COALESCE(indicacion, '')
            FROM orden_items
            WHERE orden_id IN ({placeholders})
            ORDER BY id ASC
            """,
            orden_ids,
        )

        items_por_orden = defaultdict(list)
        for orden_id, producto, precio, indicacion in cursor.fetchall():
            items_por_orden[orden_id].append((producto, precio, indicacion))

        for o in ordenes:
            items = items_por_orden[o[0]]
            items_agrupados, total_factura = preparar_lineas_factura(items, o[7], o[8], o[9])

            resultado.append(
                {
                    "id": o[0],
                    "numero": o[1],
                    "tipo": o[2],
                    "cliente": o[3],
                    "referencia": o[4],
                    "usuario": o[5] if o[5] else "N/A",
                    "evento_impresion": f"{o[0]}-{o[6] if o[6] else 'base'}",
                    "items": [
                        f"{quitar_prefijo_cantidad_visual(item['texto'])} - ${round(item['precio_total'], 2)}"
                        for item in items_agrupados
                    ],
                    "total": total_factura,
                }
            )

        conn.close()
        if resultado:
            print(f"Facturas pendientes devueltas: {len(resultado)}")
        return jsonify(resultado)

    except Exception as e:
        print("ERROR EN FACTURAS:", e)
        return jsonify([])


@app.route("/activar_factura/<int:orden_id>")
def activar_factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ordenes SET facturar=1, factura_reimpresion_token=NULL WHERE id=? AND cierre_id IS NULL",
        (orden_id,),
    )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/reimprimir_factura/<int:orden_id>")
def reimprimir_factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, cierre_id
        FROM ordenes
        WHERE id=?
        """,
        (orden_id,),
    )
    orden = cursor.fetchone()

    if not orden:
        conn.close()
        return "Orden no encontrada"

    if orden[1] is not None:
        conn.close()
        return "No se puede reimprimir una factura archivada en cierre de jornada"

    token = ahora_venezuela().strftime("%Y%m%d%H%M%S%f")
    cursor.execute(
        """
        UPDATE ordenes
        SET facturar=1, factura_reimpresion_token=?
        WHERE id=?
        """,
        (token, orden_id),
    )
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/desactivar_factura/<int:orden_id>")
def desactivar_factura(orden_id):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM ordenes WHERE id=?", (orden_id,))
        factura = cursor.fetchone()

        if not factura:
            conn.close()
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404

        cursor.execute("UPDATE ordenes SET facturar=0 WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()
        print(f"/desactivar_factura desactivo factura {orden_id}")
        return jsonify({"ok": True, "id": orden_id})

    except Exception as e:
        print("ERROR EN DESACTIVAR_FACTURA:", e)
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return jsonify({"ok": False, "error": str(e)}), 500


def _reset_neko_wok_db():
    """Borra datos operativos y recrea el menú Neko Wok desde cero. NO borra usuarios ni tasa."""
    TABLAS_OPERATIVAS = [
        "orden_items",
        "pagos",
        "cierre_detalle",
        "ordenes",
        "cierres",
        "cierres_caja",
        "compras",
        "producciones",
        "movimientos_inventario",
        "inventario",
        "recetas",
        "proveedores",
        "productos_base",
        "auditoria_emergencias",
        "productos",
        "categorias",
    ]

    conn = get_connection()
    cursor = conn.cursor()

    try:
        if es_postgres():
            tablas_str = ", ".join(TABLAS_OPERATIVAS)
            cursor.execute(f"TRUNCATE {tablas_str} RESTART IDENTITY CASCADE")
        else:
            for tabla in TABLAS_OPERATIVAS:
                cursor.execute(f"DELETE FROM {tabla}")
            for tabla in TABLAS_OPERATIVAS:
                cursor.execute(
                    "DELETE FROM sqlite_sequence WHERE name=?", (tabla,)
                )

        # Recrear categorías Neko Wok
        for cat in ORDEN_CATEGORIAS_POS:
            cursor.execute("INSERT INTO categorias (nombre, activo) VALUES (?, 1)", (cat,))

        conn.commit()

        # Obtener IDs de categorías recién creadas
        cursor.execute("SELECT id, nombre FROM categorias")
        cat_dict = {nombre: cat_id for cat_id, nombre in cursor.fetchall()}

        # Recrear productos Neko Wok
        productos_neko = PRODUCTOS_MENU_NEKO

        for nombre, precio, cat in productos_neko:
            cursor.execute(
                "INSERT INTO productos (nombre, precio, categoria_id, activo) VALUES (?, ?, ?, 1)",
                (nombre, precio, cat_dict.get(cat)),
            )

        # Recrear productos_base de inventario
        productos_base = [
            ("Pollo",    "kg"),
            ("Cerdo",    "kg"),
            ("Camaron",  "kg"),
            ("Arroz",    "kg"),
            ("Lumpias",  "unidad"),
            ("Salsa",    "lt"),
            ("Refresco", "unidad"),
        ]
        for nombre, unidad in productos_base:
            cursor.execute(
                "INSERT INTO productos_base (nombre, unidad) VALUES (?, ?)",
                (nombre, unidad),
            )

        conn.commit()
        conn.close()

    except Exception:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        raise


@app.route("/reset_neko", methods=["GET", "POST"])
def reset_neko():
    if not usuario_es_master():
        return "Acceso denegado", 403

    if request.method == "POST":
        confirmacion = (request.form.get("confirmacion") or "").strip()
        if confirmacion != "RESET NEKO WOK":
            return f"""
            <html><head><meta charset="UTF-8"><style>{estilos_base()}</style></head>
            <body>
            {barra_superior('<a href="/usuarios">👥 Usuarios</a>')}
            <div style="max-width:600px;margin:40px auto;padding:0 18px;">
                <div style="background:#fef2f2;border:2px solid #ef4444;border-radius:10px;padding:24px;">
                    <h2 style="color:#dc2626;margin-top:0;">✖ Confirmación incorrecta</h2>
                    <p>Debes escribir exactamente: <code>RESET NEKO WOK</code></p>
                    <a href="/reset_neko" style="color:#1d4ed8;">← Volver</a>
                </div>
            </div>
            </body></html>
            """, 400

        try:
            _reset_neko_wok_db()
        except Exception as exc:
            return f"""
            <html><head><meta charset="UTF-8"><style>{estilos_base()}</style></head>
            <body>
            {barra_superior('<a href="/usuarios">👥 Usuarios</a>')}
            <div style="max-width:600px;margin:40px auto;padding:0 18px;">
                <div style="background:#fef2f2;border:2px solid #ef4444;border-radius:10px;padding:24px;">
                    <h2 style="color:#dc2626;margin-top:0;">⚠️ Error durante el reset</h2>
                    <p>Los datos NO fueron modificados (se hizo rollback).</p>
                    <pre style="background:#fff;padding:12px;border-radius:6px;overflow:auto;font-size:12px;">{html_lib.escape(str(exc))}</pre>
                    <a href="/reset_neko" style="color:#1d4ed8;">← Volver</a>
                </div>
            </div>
            </body></html>
            """, 500

        return f"""
        <html><head><meta charset="UTF-8"><style>{estilos_base()}</style></head>
        <body>
        {barra_superior('<a href="/">🏠 Inicio</a>')}
        <div style="max-width:600px;margin:40px auto;padding:0 18px;">
            <div style="background:#f0fdf4;border:2px solid #22c55e;border-radius:10px;padding:24px;">
                <h2 style="color:#15803d;margin-top:0;">✅ Reset completado</h2>
                <p>El sistema fue reiniciado exitosamente con el menú Neko Wok.</p>
                <ul>
                    <li>Órdenes, pagos y cierres anteriores: <b>eliminados</b></li>
                    <li>Inventario y compras: <b>eliminados</b></li>
                    <li>Menú Neko Wok: <b>recreado</b></li>
                    <li>Productos base (inventario): <b>recreados</b></li>
                    <li>Usuarios y tasa: <b>conservados</b></li>
                </ul>
                <a href="/" style="display:inline-block;margin-top:8px;background:#1a6b4a;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;">🏠 Ir al inicio</a>
            </div>
        </div>
        </body></html>
        """

    # GET — pantalla de advertencia
    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ margin:0; }}
    .contenido {{ max-width:660px; margin:40px auto; padding:0 18px; }}
    .advertencia {{ background:#fff7ed; border:2px solid #f97316; border-radius:12px; padding:28px; }}
    .advertencia h1 {{ color:#c2410c; margin-top:0; font-size:22px; }}
    .lista-borrar {{ background:#fef2f2; border-radius:8px; padding:14px 18px; margin:16px 0; }}
    .lista-borrar li {{ color:#991b1b; margin:4px 0; }}
    .lista-conservar {{ background:#f0fdf4; border-radius:8px; padding:14px 18px; margin:16px 0; }}
    .lista-conservar li {{ color:#166534; margin:4px 0; }}
    input[name="confirmacion"] {{ width:100%; padding:12px; font-size:16px; border:2px solid #f97316; border-radius:8px; margin:10px 0; box-sizing:border-box; font-family:monospace; }}
    .btn-reset {{ background:#dc2626; color:white; border:none; padding:14px 28px; border-radius:8px; font-size:16px; font-weight:bold; cursor:pointer; width:100%; margin-top:8px; }}
    .btn-reset:hover {{ background:#b91c1c; }}
    .btn-cancel {{ display:block; text-align:center; margin-top:14px; color:#6b7280; text-decoration:none; }}
    </style>
    </head>
    <body>
    {barra_superior('<a href="/usuarios">👥 Usuarios</a>')}
    <div class="contenido">
        <div class="advertencia">
            <h1>⚠️ Reset Neko Wok — Advertencia</h1>
            <p><b>Esta acción borrará permanentemente los datos operativos del sistema</b> y dejará la base de datos limpia con solo el menú Neko Wok.</p>

            <p><b>Se borrarán:</b></p>
            <ul class="lista-borrar">
                <li>Órdenes (ordenes, orden_items)</li>
                <li>Pagos (pagos)</li>
                <li>Cierres de jornada (cierres, cierres_caja, cierre_detalle)</li>
                <li>Inventario (inventario, movimientos_inventario)</li>
                <li>Compras y producciones</li>
                <li>Recetas</li>
                <li>Proveedores</li>
                <li>Productos base</li>
                <li>Auditoría de emergencias</li>
                <li>Todos los productos y categorías anteriores</li>
            </ul>

            <p><b>Se conservarán:</b></p>
            <ul class="lista-conservar">
                <li>Usuarios y PINs</li>
                <li>Tasa de cambio actual</li>
            </ul>

            <p><b>Se recrearán automáticamente:</b></p>
            <ul class="lista-conservar">
                <li>Categorías Neko Wok (7 categorías)</li>
                <li>Productos Neko Wok completos</li>
                <li>Productos base de inventario</li>
            </ul>

            <form method="post">
                <label><b>Escribe exactamente para confirmar:</b><br>
                <code style="background:#fff;padding:3px 8px;border-radius:4px;font-size:14px;">RESET NEKO WOK</code></label>
                <input name="confirmacion" type="text" autocomplete="off" placeholder="RESET NEKO WOK">
                <button class="btn-reset" type="submit">⚠️ Confirmar reset definitivo</button>
            </form>
            <a href="/usuarios" class="btn-cancel">← Cancelar y volver</a>
        </div>
    </div>
    </body>
    </html>
    """


with app.app_context():
    init_db()
    cargar_productos()
    asegurar_menu_neko_wok()
    desactivar_menu_china_house()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
