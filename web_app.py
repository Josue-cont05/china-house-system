from flask import Flask, request, redirect
import sqlite3
import datetime
import os

app = Flask(__name__)

# ---------------- DB ----------------

def get_db():
    return sqlite3.connect("china_house.db")

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_orden INTEGER,
        fecha TEXT,
        tipo TEXT,  -- mesa / delivery / pickup
        referencia TEXT, -- Mesa 1 o dirección
        estado TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orden_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orden_id INTEGER,
        producto TEXT,
        precio REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- MENU ----------------

menu = [
    {"id": 1, "nombre": "Arroz chino", "precio": 5},
    {"id": 2, "nombre": "Pollo agridulce", "precio": 6},
    {"id": 3, "nombre": "Pasta china", "precio": 5},
]

# ---------------- UTIL ----------------

def obtener_numero_orden(fecha):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(numero_orden) FROM ordenes WHERE fecha = ?", (fecha,))
    resultado = cursor.fetchone()[0]

    conn.close()

    return 1 if resultado is None else resultado + 1

# ---------------- INTERFAZ PRINCIPAL ----------------

@app.route("/")
def venta():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, numero_orden, tipo, referencia, estado FROM ordenes WHERE estado != 'pagada'")
    ordenes = cursor.fetchall()

    conn.close()

    html = "<h1>💻 China House - Ventas</h1>"

    # CREAR ORDEN
    html += """
    <h2>Nueva Orden</h2>
    <form action="/crear_orden" method="post">
        Tipo:
        <select name="tipo">
            <option value="mesa">Mesa</option>
            <option value="delivery">Delivery</option>
            <option value="pickup">Pick Up</option>
        </select><br><br>

        Referencia (Mesa o dirección):
        <input type="text" name="referencia"><br><br>

        <button type="submit">Crear Orden</button>
    </form>
    """

    # ORDENES ACTIVAS
    html += "<h2>Órdenes activas</h2>"

    for o in ordenes:
        html += f"""
        <div style="border:1px solid black; padding:10px; margin:5px;">
            Orden #{o[1]} - {o[2]} - {o[3]} - {o[4]}
            <br>
            <a href="/orden/{o[0]}">Abrir</a>
        </div>
        """

    return html

# ---------------- CREAR ORDEN ----------------

@app.route("/crear_orden", methods=["POST"])
def crear_orden():
    tipo = request.form["tipo"]
    referencia = request.form["referencia"]

    fecha = datetime.date.today().isoformat()
    numero = obtener_numero_orden(fecha)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha, tipo, referencia, estado)
    VALUES (?, ?, ?, ?, ?)
    """, (numero, fecha, tipo, referencia, "abierta"))

    conn.commit()
    conn.close()

    return redirect("/")

# ---------------- VER ORDEN ----------------

@app.route("/orden/<int:orden_id>")
def ver_orden(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT numero_orden, tipo, referencia, estado FROM ordenes WHERE id = ?", (orden_id,))
    orden = cursor.fetchone()

    cursor.execute("SELECT producto, precio FROM orden_detalle WHERE orden_id = ?", (orden_id,))
    productos = cursor.fetchall()

    conn.close()

    html = f"<h1>Orden #{orden[0]}</h1>"
    html += f"<p>{orden[1]} - {orden[2]}</p>"
    html += f"<p>Estado: {orden[3]}</p>"

    total = 0
    html += "<h3>Productos</h3>"

    for p in productos:
        html += f"{p[0]} - ${p[1]}<br>"
        total += p[1]

    html += f"<h2>Total: ${total}</h2>"

    # AGREGAR PRODUCTOS
    html += "<h3>Agregar</h3>"
    for m in menu:
        html += f"""
        <a href="/agregar/{orden_id}/{m['id']}">
        {m['nombre']} - ${m['precio']}
        </a><br>
        """

    html += "<hr>"

    html += f'<a href="/cocina/{orden_id}">🔥 Enviar a cocina</a><br>'
    html += f'<a href="/pagar/{orden_id}">💰 Cobrar</a><br>'
    html += '<a href="/">⬅ Volver</a>'

    return html

# ---------------- AGREGAR PRODUCTO ----------------

@app.route("/agregar/<int:orden_id>/<int:producto_id>")
def agregar(orden_id, producto_id):
    producto = next((p for p in menu if p["id"] == producto_id), None)

    if not producto:
        return "Producto no encontrado"

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO orden_detalle (orden_id, producto, precio)
    VALUES (?, ?, ?)
    """, (orden_id, producto["nombre"], producto["precio"]))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- COCINA ----------------

@app.route("/cocina/<int:orden_id>")
def cocina(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado='cocina' WHERE id = ?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- PAGAR ----------------

@app.route("/pagar/<int:orden_id>")
def pagar(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado='pagada' WHERE id = ?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/")

# ---------------- RUN ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
