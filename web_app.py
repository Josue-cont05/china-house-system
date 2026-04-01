from flask import Flask, request, redirect
import sqlite3
from datetime import datetime

app = Flask(__name__)

# =========================
# DB
# =========================
def get_db():
    return sqlite3.connect("china_house.db")


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL,
        activo INTEGER DEFAULT 1
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero INTEGER,
        fecha TEXT,
        tipo TEXT,
        referencia TEXT,
        cliente TEXT,
        estado TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orden_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orden_id INTEGER,
        producto TEXT,
        precio REAL
    )
    """)

    conn.commit()
    conn.close()


def obtener_tasa():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM configuracion WHERE clave='tasa'")
    row = cursor.fetchone()
    conn.close()
    return float(row[0]) if row else 35


init_db()

# =========================
# HOME
# =========================
@app.route("/")
def home():
    tasa = obtener_tasa()

    return f"""
    <h1>Sistema China House</h1>

    <h3>Tasa actual: Bs {tasa}</h3>
    <form method="POST" action="/tasa">
        Nueva tasa: <input name="tasa">
        <button>Guardar</button>
    </form>

    <hr>

    <a href="/crear_orden">➕ Nueva Orden</a><br>
    <a href="/productos">📦 Productos</a>
    """


@app.route("/tasa", methods=["POST"])
def tasa():
    nueva = request.form["tasa"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO configuracion (clave, valor)
    VALUES ('tasa', ?)
    """, (nueva,))

    conn.commit()
    conn.close()

    return redirect("/")

# =========================
# PRODUCTOS
# =========================
@app.route("/productos")
def productos():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM productos WHERE activo=1")
    productos = cursor.fetchall()

    conn.close()

    html = "<h1>Productos</h1>"

    for p in productos:
        html += f"{p[1]} - ${p[2]}<br>"

    html += """
    <hr>
    <form method="POST" action="/crear_producto">
        Nombre: <input name="nombre"><br>
        Precio: <input name="precio"><br>
        <button>Crear</button>
    </form>

    <br><a href="/">Volver</a>
    """

    return html


@app.route("/crear_producto", methods=["POST"])
def crear_producto():
    nombre = request.form["nombre"]
    precio = request.form["precio"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO productos (nombre,precio) VALUES (?,?)", (nombre, precio))

    conn.commit()
    conn.close()

    return redirect("/productos")

# =========================
# ORDENES
# =========================
@app.route("/crear_orden", methods=["GET", "POST"])
def crear_orden():
    if request.method == "POST":
        tipo = request.form["tipo"]
        referencia = request.form["referencia"]
        cliente = request.form["cliente"]

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        cursor = conn.cursor()

        # consecutivo diario
        hoy = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM ordenes WHERE fecha LIKE ?", (f"{hoy}%",))
        numero = cursor.fetchone()[0] + 1

        cursor.execute("""
        INSERT INTO ordenes (numero,fecha,tipo,referencia,cliente,estado)
        VALUES (?,?,?,?,?,'abierta')
        """, (numero, fecha, tipo, referencia, cliente))

        conn.commit()

        orden_id = cursor.lastrowid
        conn.close()

        return redirect(f"/orden/{orden_id}")

    return """
    <h1>Nueva Orden</h1>

    <form method="POST">
        Tipo:
        <select name="tipo">
            <option>mesa</option>
            <option>delivery</option>
            <option>pickup</option>
        </select><br>

        Referencia (ej: Mesa 1): <input name="referencia"><br>

        Cliente (opcional): <input name="cliente"><br>

        <button>Crear</button>
    </form>
    """

# =========================
# VER ORDEN
# =========================
@app.route("/orden/<int:orden_id>")
def orden(orden_id):
    tasa = obtener_tasa()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes WHERE id=?", (orden_id,))
    orden = cursor.fetchone()

    cursor.execute("SELECT * FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT * FROM productos WHERE activo=1")
    productos = cursor.fetchall()

    conn.close()

    total = sum(i[3] for i in items)
    total_bs = round(total * tasa, 2)

    html = f"""
    <h1>Orden #{orden[1]}</h1>

    Tipo: {orden[3]}<br>
    Referencia: {orden[4]}<br>
    Cliente: {orden[5] if orden[5] else "No especificado"}<br>
    Fecha: {orden[2]}<br>

    <hr>

    <h2>Total: ${total} | Bs {total_bs}</h2>
    """

    for i in items:
        html += f"{i[2]} - ${i[3]}<br>"

    html += "<hr><h3>Agregar producto</h3>"

    for p in productos:
        html += f"""
        <a href="/agregar/{orden_id}/{p[0]}">
        {p[1]} - ${p[2]}
        </a><br>
        """

    html += f"""
    <hr>

    🔥 <a href="/cocina/{orden_id}">Enviar a cocina</a><br>
    💵 <a href="/cobrar/{orden_id}">Cobrar</a><br>

    <br><a href="/">Volver</a>
    """

    return html


@app.route("/agregar/<int:orden_id>/<int:producto_id>")
def agregar(orden_id, producto_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nombre,precio FROM productos WHERE id=?", (producto_id,))
    p = cursor.fetchone()

    cursor.execute("""
    INSERT INTO orden_items (orden_id,producto,precio)
    VALUES (?,?,?)
    """, (orden_id, p[0], p[1]))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# =========================
# COBRAR
# =========================
@app.route("/cobrar/<int:orden_id>", methods=["GET", "POST"])
def cobrar(orden_id):
    tasa = obtener_tasa()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    total = sum(i[3] for i in items)

    if request.method == "POST":
        pago_usd = float(request.form.get("usd") or 0)
        pago_bs = float(request.form.get("bs") or 0)
        descuento = float(request.form.get("descuento") or 0)

        total_final = total - descuento
        total_bs = total_final * tasa

        total_pagado = pago_usd + (pago_bs / tasa)

        vuelto = round(total_pagado - total_final, 2)

        cursor.execute("UPDATE ordenes SET estado='cerrada' WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()

        return f"""
        <h1>Pago completado</h1>

        Total: ${total_final}<br>
        Pagado: ${total_pagado}<br>
        Vuelto: ${vuelto}

        <br><br>
        <a href="/">Volver</a>
        """

    total_bs = round(total * tasa, 2)

    html = f"""
    <h1>Cobrar Orden #{orden_id}</h1>

    <h2>Total: ${total} | Bs {total_bs}</h2>

    <form method="POST">
        Descuento: <input name="descuento"><br><br>

        Pago USD: <input name="usd"><br>
        Pago Bs: <input name="bs"><br><br>

        <button>Confirmar pago</button>
    </form>

    <br><a href="/orden/{orden_id}">Volver</a>
    """

    return html

# =========================
# COCINA
# =========================
@app.route("/cocina/<int:orden_id>")
def cocina(orden_id):
    return f"<h1>Orden {orden_id} enviada a cocina 🔥</h1><a href='/orden/{orden_id}'>Volver</a>"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
