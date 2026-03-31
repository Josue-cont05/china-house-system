from flask import Flask, request, redirect
import sqlite3
import datetime

app = Flask(__name__)

# ---------- DB ----------
def conectar():
    return sqlite3.connect("china_house.db")

def crear_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto TEXT,
        cantidad INTEGER,
        tipo TEXT,
        mesa TEXT,
        metodo_pago TEXT,
        usuario TEXT,
        fecha TEXT
    )
    """)

    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] == 0:
        productos = [
            ("Arroz chino", 5),
            ("Pollo agridulce", 6),
            ("Pasta china", 5),
            ("Shopsuey", 6),
            ("Refresco", 1)
        ]
        cursor.executemany(
            "INSERT INTO productos (nombre, precio) VALUES (?, ?)",
            productos
        )

    conn.commit()
    conn.close()

crear_db()

# ---------- MENU ----------
def cargar_menu():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT nombre, precio FROM productos")
    datos = cursor.fetchall()

    conn.close()

    return [{"nombre": n, "precio": p} for n, p in datos]

# ---------- INICIO ----------
@app.route("/")
def inicio():
    return """
    <h1>China House Manager</h1>
    <a href="/venta">Ir a ventas</a>
    """

# ---------- VENTAS ----------
@app.route("/venta")
def venta():
    menu = cargar_menu()

    html = "<h2>Selecciona un producto</h2>"

    for producto in menu:
        html += f"""
        <div style="margin:20px;padding:20px;border:1px solid #ccc;">
            <h3>{producto['nombre']}</h3>
            <p>${producto['precio']}</p>

            <form method="POST" action="/vender">
                <input type="hidden" name="producto" value="{producto['nombre']}">
                <button type="submit">Vender</button>
            </form>
        </div>
        """

    html += "<br><a href='/'>Volver</a>"
    return html

# ---------- REGISTRAR ----------
@app.route("/vender", methods=["POST"])
def vender():
    producto = request.form["producto"]

    conn = conectar()
    cursor = conn.cursor()

    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO ventas (producto, cantidad, tipo, mesa, metodo_pago, usuario, fecha)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (producto, 1, "local", "1", "efectivo", "mesonero", fecha))

    conn.commit()
    conn.close()

    return redirect("/venta")

# ---------- HISTORIAL ----------
@app.route("/historial")
def historial():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT producto, fecha FROM ventas ORDER BY id DESC")
    datos = cursor.fetchall()

    conn.close()

    html = "<h2>Historial</h2>"

    for producto, fecha in datos:
        html += f"<p>{producto} - {fecha}</p>"

    html += "<br><a href='/'>Volver</a>"
    return html

if __name__ == "__main__":

import os
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
