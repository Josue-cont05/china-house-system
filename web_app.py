from flask import Flask, request, redirect
import sqlite3
import datetime
import os

app = Flask(__name__)

# -------------------- DB --------------------

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
        mesa TEXT,
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comandas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_comanda INTEGER,
        orden_id INTEGER,
        fecha TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# -------------------- MENU --------------------

menu = [
    {"nombre": "Arroz chino", "precio": 5},
    {"nombre": "Pollo agridulce", "precio": 6},
    {"nombre": "Pasta china", "precio": 5},
]

# -------------------- CREAR ORDEN --------------------

def obtener_numero_orden(fecha):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(numero_orden) FROM ordenes WHERE fecha = ?", (fecha,))
    resultado = cursor.fetchone()[0]

    conn.close()

    if resultado is None:
        return 1
    return resultado + 1

@app.route("/nueva_orden")
def nueva_orden():
    fecha = datetime.date.today().isoformat()
    numero = obtener_numero_orden(fecha)

    mesa = request.args.get("mesa")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha, mesa, estado)
    VALUES (?, ?, ?, ?)
    """, (numero, fecha, mesa, "abierta"))

    conn.commit()
    conn.close()

    return redirect("/ordenes")

# -------------------- LISTA DE ORDENES --------------------

@app.route("/ordenes")
def ordenes():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, numero_orden, mesa, estado FROM ordenes WHERE estado != 'pagada'")
    ordenes = cursor.fetchall()

    conn.close()

    html = "<h1>Órdenes</h1>"

    # Crear orden
    html += "<h3>Crear nueva orden</h3>"
    for i in range(1, 11):
        html += f'<a href="/nueva_orden?mesa=Mesa {i}">Mesa {i}</a><br>'

    html += "<hr><h3>Órdenes abiertas</h3>"

    for o in ordenes:
        html += f"""
        <div>
            Orden #{o[1]} - {o[2]} - {o[3]}
            <a href="/orden/{o[0]}">Entrar</a>
        </div>
        """

    return html

# -------------------- VER ORDEN --------------------

@app.route("/orden/<int:orden_id>")
def ver_orden(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT numero_orden, mesa, estado FROM ordenes WHERE id = ?", (orden_id,))
    orden = cursor.fetchone()

    cursor.execute("SELECT producto, precio FROM orden_detalle WHERE orden_id = ?", (orden_id,))
    productos = cursor.fetchall()

    conn.close()

    html = f"<h1>Orden #{orden[0]} - {orden[1]}</h1>"
    html += f"<p>Estado: {orden[2]}</p>"

    html += "<h3>Productos</h3>"
    total = 0

    for p in productos:
        html += f"{p[0]} - ${p[1]}<br>"
        total += p[1]

    html += f"<h3>Total: ${total}</h3>"

    html += "<hr><h3>Agregar producto</h3>"

    for m in menu:
        html += f"""
        <a href="/agregar/{orden_id}/{m['nombre']}/{m['precio']}">
            {m['nombre']} - ${m['precio']}
        </a><br>
        """

    html += "<hr>"

    html += f'<a href="/comanda/{orden_id}">🔥 Enviar a cocina</a><br>'
    html += f'<a href="/pagar/{orden_id}">💰 Cobrar</a><br>'
    html += '<a href="/ordenes">⬅ Volver</a>'

    return html

# -------------------- AGREGAR PRODUCTO --------------------

@app.route("/agregar/<int:orden_id>/<producto>/<float:precio>")
def agregar_producto(orden_id, producto, precio):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO orden_detalle (orden_id, producto, precio)
    VALUES (?, ?, ?)
    """, (orden_id, producto, precio))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# -------------------- COMANDA --------------------

def obtener_numero_comanda(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(numero_comanda) FROM comandas WHERE orden_id = ?", (orden_id,))
    resultado = cursor.fetchone()[0]

    conn.close()

    if resultado is None:
        return 1
    return resultado + 1

@app.route("/comanda/<int:orden_id>")
def generar_comanda(orden_id):
    fecha = datetime.datetime.now().isoformat()
    numero = obtener_numero_comanda(orden_id)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO comandas (numero_comanda, orden_id, fecha)
    VALUES (?, ?, ?)
    """, (numero, orden_id, fecha))

    cursor.execute("UPDATE ordenes SET estado = 'cocina' WHERE id = ?", (orden_id,))

    conn.commit()
    conn.close()

    return f"Comanda #{numero} enviada a cocina <br><a href='/orden/{orden_id}'>Volver</a>"

# -------------------- PAGAR --------------------

@app.route("/pagar/<int:orden_id>")
def pagar(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado = 'pagada' WHERE id = ?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/ordenes")

# -------------------- HOME --------------------

@app.route("/")
def home():
    return '<h1>China House</h1><a href="/ordenes">Ir al sistema</a>'

# -------------------- RUN --------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
