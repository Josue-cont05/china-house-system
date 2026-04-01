from flask import Flask, request, redirect
import sqlite3
import datetime
import os

app = Flask(__name__)

# ---------------- DB ----------------

def init_db():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_orden INTEGER,
        fecha_hora TEXT,
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orden_id INTEGER,
        metodo TEXT,
        monto REAL,
        referencia TEXT
    )
    """)

    conn.commit()
    conn.close()

# ---------------- PRODUCTOS ----------------

def cargar_productos():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] == 0:
        productos = [
            ("Arroz chino", 5),
            ("Pollo agridulce", 6),
            ("Pasta china", 5)
        ]
        cursor.executemany("INSERT INTO productos (nombre, precio) VALUES (?, ?)", productos)

    conn.commit()
    conn.close()

# ---------------- CONSECUTIVO ----------------

def siguiente_numero():
    hoy = datetime.date.today().isoformat()

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT MAX(numero_orden)
    FROM ordenes
    WHERE date(fecha_hora) = ?
    """, (hoy,))

    ultimo = cursor.fetchone()[0]

    conn.close()

    return 1 if ultimo is None else ultimo + 1

# ---------------- HOME ----------------

@app.route("/")
def pos():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes WHERE estado != 'cerrada'")
    ordenes = cursor.fetchall()

    conn.close()

    html = """
    <h1>🍜 China House POS</h1>

    <form action="/crear_orden" method="post">
        Tipo:
        <select name="tipo">
            <option>Mesa</option>
            <option>Delivery</option>
            <option>Pickup</option>
        </select>

        Referencia:
        <input name="referencia">

        Cliente:
        <input name="cliente">

        <button type="submit">Crear Orden</button>
    </form>

    <hr>
    <h2>Órdenes</h2>
    """

    for o in ordenes:
        html += f"""
        <div>
            #{o[1]} | {o[3]} - {o[4]} | {o[6]}
            <a href="/orden/{o[0]}">Abrir</a>
        </div>
        """

    return html

# ---------------- CREAR ORDEN ----------------

@app.route("/crear_orden", methods=["POST"])
def crear_orden():
    tipo = request.form["tipo"]
    referencia = request.form["referencia"]
    cliente = request.form.get("cliente", "")

    numero = siguiente_numero()
    fecha_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha_hora, tipo, referencia, cliente, estado)
    VALUES (?, ?, ?, ?, ?, 'abierta')
    """, (numero, fecha_hora, tipo, referencia, cliente))

    conn.commit()
    orden_id = cursor.lastrowid
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- ORDEN ----------------

@app.route("/orden/<int:orden_id>")
def orden(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT id, nombre, precio FROM productos")
    productos = cursor.fetchall()

    conn.close()

    total = sum(i[3] for i in items)

    html = "<h2>Orden</h2>"

    for i in items:
        html += f"{i[2]} - ${i[3]}<br>"

    html += f"<h3>Total: ${total}</h3><hr>"

    for p in productos:
        html += f"<a href='/agregar/{orden_id}/{p[0]}'>{p[1]}</a><br>"

    html += f"<br><a href='/cobrar/{orden_id}'>💰 Cobrar</a>"
    html += "<br><a href='/'>Volver</a>"

    return html

# ---------------- AGREGAR ----------------

@app.route("/agregar/<int:orden_id>/<int:producto_id>")
def agregar(orden_id, producto_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT nombre, precio FROM productos WHERE id=?", (producto_id,))
    p = cursor.fetchone()

    cursor.execute("INSERT INTO orden_items (orden_id, producto, precio) VALUES (?, ?, ?)",
                   (orden_id, p[0], p[1]))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- COBRAR (PRO) ----------------

@app.route("/cobrar/<int:orden_id>")
def cobrar(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT producto, precio FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT metodo, monto FROM pagos WHERE orden_id=?", (orden_id,))
    pagos = cursor.fetchall()

    conn.close()

    subtotal = sum(i[1] for i in items)

    html = f"""
    <h1>Cobro</h1>

    <h3>Factura</h3>
    """

    for i in items:
        html += f"{i[0]} - ${i[1]}<br>"

    html += f"<hr>Subtotal: ${subtotal}<br>"

    html += f"""
    <form action="/calcular/{orden_id}" method="post">

        Descuento:
        <input name="descuento" value="0"><br>

        Impuesto (%):
        <input name="impuesto" value="0"><br>

        Tasa Bs:
        <input name="tasa" value="40"><br>

        <button type="submit">Calcular</button>
    </form>

    <hr>

    <h3>Pagos realizados</h3>
    """

    total_pagado = 0
    for p in pagos:
        html += f"{p[0]} - ${p[1]}<br>"
        total_pagado += p[1]

    html += f"<br>Total pagado: ${total_pagado}<br>"

    html += f"""
    <form action="/agregar_pago/{orden_id}" method="post">
        Metodo:
        <select name="metodo">
            <option>Efectivo $</option>
            <option>Efectivo Bs</option>
            <option>Pago móvil</option>
        </select>

        Monto:
        <input name="monto">

        Referencia:
        <input name="ref">

        <button>Agregar pago</button>
    </form>

    <br><a href="/cerrar/{orden_id}">Cerrar orden</a>
    <br><a href="/orden/{orden_id}">Volver</a>
    """

    return html

# ---------------- PAGOS ----------------

@app.route("/agregar_pago/<int:orden_id>", methods=["POST"])
def agregar_pago(orden_id):
    metodo = request.form["metodo"]
    monto = float(request.form["monto"])
    ref = request.form.get("ref", "")

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("INSERT INTO pagos (orden_id, metodo, monto, referencia) VALUES (?, ?, ?, ?)",
                   (orden_id, metodo, monto, ref))

    conn.commit()
    conn.close()

    return redirect(f"/cobrar/{orden_id}")

# ---------------- CERRAR ----------------

@app.route("/cerrar/<int:orden_id>")
def cerrar(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado='cerrada' WHERE id=?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/")

# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    cargar_productos()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
