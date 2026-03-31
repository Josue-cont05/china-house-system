from flask import Flask, request, redirect
import sqlite3
import datetime
import os

app = Flask(__name__)

# -------------------- DB --------------------

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

# -------------------- DATA INICIAL --------------------

def cargar_productos():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO productos (nombre, precio) VALUES ('Arroz chino', 5)")
        cursor.execute("INSERT INTO productos (nombre, precio) VALUES ('Pollo agridulce', 6)")
        cursor.execute("INSERT INTO productos (nombre, precio) VALUES ('Pasta china', 5)")

    conn.commit()
    conn.close()

# -------------------- CONSECUTIVO --------------------

def siguiente_numero():
    hoy = datetime.date.today().isoformat()

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(numero_orden) FROM ordenes WHERE fecha = ?", (hoy,))
    ultimo = cursor.fetchone()[0]

    conn.close()

    return 1 if ultimo is None else ultimo + 1

# -------------------- HOME --------------------

@app.route("/")
def home():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes WHERE estado != 'cerrada'")
    ordenes = cursor.fetchall()

    conn.close()

    html = """
    <h1>🍜 China House - Sistema</h1>

    <h2>Nueva Orden</h2>
    <form action="/crear_orden" method="post">
        Tipo:
        <select name="tipo">
            <option value="Mesa">Mesa</option>
            <option value="Delivery">Delivery</option>
            <option value="Pickup">Pickup</option>
        </select><br><br>

        Referencia (Mesa o dirección):
        <input type="text" name="referencia"><br><br>

        Nombre del cliente (opcional):
        <input type="text" name="cliente"><br><br>

        <button type="submit">Crear Orden</button>
    </form>

    <hr>

    <h2>Órdenes abiertas</h2>
    """

    for o in ordenes:
        html += f"""
        <div style="border:1px solid #ccc; padding:10px; margin:10px;">
            <b>Orden #{o[1]}</b><br>
            {o[3]} - {o[4]}<br>
            Cliente: {o[5] if o[5] else '-'}<br>
            Estado: {o[6]}<br>
            <a href="/orden/{o[0]}">Abrir</a>
        </div>
        """

    return html

# -------------------- CREAR ORDEN --------------------

@app.route("/crear_orden", methods=["POST"])
def crear_orden():
    tipo = request.form["tipo"]
    referencia = request.form["referencia"]
    cliente = request.form.get("cliente", "")

    numero = siguiente_numero()
    fecha = datetime.date.today().isoformat()

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha, tipo, referencia, cliente, estado)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (numero, fecha, tipo, referencia, cliente, "abierta"))

    conn.commit()

    orden_id = cursor.lastrowid
    conn.close()

    return redirect(f"/orden/{orden_id}")

# -------------------- VER ORDEN --------------------

@app.route("/orden/<int:orden_id>")
def ver_orden(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT numero_orden, tipo, referencia, cliente, estado FROM ordenes WHERE id = ?", (orden_id,))
    orden = cursor.fetchone()

    cursor.execute("SELECT producto, precio FROM orden_items WHERE orden_id = ?", (orden_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT id, nombre, precio FROM productos")
    productos = cursor.fetchall()

    conn.close()

    total = sum(i[1] for i in items)

    html = f"""
    <h1>Orden #{orden[0]}</h1>
    <p>{orden[1]} - {orden[2]}</p>
    <p>Cliente: {orden[3] if orden[3] else '-'}</p>
    <p>Estado: {orden[4]}</p>

    <h3>Productos</h3>
    """

    for i in items:
        html += f"{i[0]} - ${i[1]}<br>"

    html += f"<h3>Total: ${total}</h3><hr>"

    html += "<h3>Agregar producto</h3>"

    for p in productos:
        html += f"""
        <a href="/agregar/{orden_id}/{p[0]}">
            {p[1]} - ${p[2]}
        </a><br>
        """

    html += f"""
    <br><br>
    🔥 <a href="/enviar_cocina/{orden_id}">Enviar a cocina</a><br>
    💰 <a href="/cobrar/{orden_id}">Cobrar</a><br><br>

    <a href="/">Volver</a>
    """

    return html

# -------------------- AGREGAR PRODUCTO --------------------

@app.route("/agregar/<int:orden_id>/<int:producto_id>")
def agregar_producto(orden_id, producto_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT nombre, precio FROM productos WHERE id = ?", (producto_id,))
    producto = cursor.fetchone()

    cursor.execute("""
    INSERT INTO orden_items (orden_id, producto, precio)
    VALUES (?, ?, ?)
    """, (orden_id, producto[0], producto[1]))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# -------------------- ENVIAR A COCINA --------------------

@app.route("/enviar_cocina/<int:orden_id>")
def enviar_cocina(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado = 'en cocina' WHERE id = ?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# -------------------- COBRAR --------------------

@app.route("/cobrar/<int:orden_id>")
def cobrar(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado = 'cerrada' WHERE id = ?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/")

# -------------------- MAIN --------------------

if __name__ == "__main__":
    init_db()
    cargar_productos()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
