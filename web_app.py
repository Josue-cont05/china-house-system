from flask import Flask, request, redirect
import sqlite3
from datetime import datetime

app = Flask(__name__)

# ---------------- DB ----------------

def get_db():
    return sqlite3.connect("china_house.db")

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # configuración (tasa)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)

    # 🔥 IMPORTANTE
    conn.commit()
    conn.close()


def obtener_tasa():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT valor FROM configuracion WHERE clave='tasa'")
    row = cursor.fetchone()

    conn.close()

    return float(row[0]) if row else 35
    
    # productos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL
    )
    """)

    # ordenes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero INTEGER,
        fecha TEXT,
        tipo TEXT,
        referencia TEXT,
        cliente TEXT
    )
    """)

    # items
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


init_db()

# ---------------- PRODUCTOS ----------------

@app.route("/productos")
def productos():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM productos")
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

    cursor.execute("INSERT INTO productos (nombre, precio) VALUES (?,?)", (nombre, precio))

    conn.commit()
    conn.close()

    return redirect("/productos")

# ---------------- HOME ----------------

@app.route("/")
def home():
    return """
    <h1>China House</h1>

    <a href="/crear_orden">Nueva Orden</a><br>
    <a href="/productos">Gestionar Productos</a>
    """

# ---------------- CREAR ORDEN ----------------

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
        INSERT INTO ordenes (numero, fecha, tipo, referencia, cliente)
        VALUES (?,?,?,?,?)
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

@app.route("/tasa", methods=["GET", "POST"])
def tasa():
    if request.method == "POST":
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

    return """
    <h1>Configurar tasa</h1>
    <form method="POST">
        Nueva tasa: <input name="tasa">
        <button>Guardar</button>
    </form>
    """

# ---------------- VER ORDEN ----------------

@app.route("/orden/<int:orden_id>")
def ver_orden(orden_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes WHERE id=?", (orden_id,))
    orden = cursor.fetchone()

    cursor.execute("SELECT * FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT * FROM productos")
    productos = cursor.fetchall()

    conn.close()

    tasa = obtener_tasa()

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
    <br><a href="/">Volver</a>
    """

    return html

# ---------------- AGREGAR ----------------

@app.route("/agregar/<int:orden_id>/<int:producto_id>")
def agregar(orden_id, producto_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nombre, precio FROM productos WHERE id=?", (producto_id,))
    producto = cursor.fetchone()

    cursor.execute("""
    INSERT INTO orden_items (orden_id, producto, precio)
    VALUES (?,?,?)
    """, (orden_id, producto[0], producto[1]))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
