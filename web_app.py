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
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL,
        tipo TEXT,
        descripcion TEXT,
        activo INTEGER DEFAULT 1
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
    CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tasa REAL
    )
    """)

    conn.commit()
    conn.close()

# ---------------- TASA ----------------

def obtener_tasa():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tasa FROM config ORDER BY id DESC LIMIT 1")
    data = cursor.fetchone()
    conn.close()
    return data[0] if data else None

@app.route("/config", methods=["GET", "POST"])
def config():
    if request.method == "POST":
        try:
            tasa = float(request.form["tasa"])
        except:
            return "Error: tasa inválida"

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO config (tasa) VALUES (?)", (tasa,))
        conn.commit()
        conn.close()

        return redirect("/")

    return """
    <h1>Configurar tasa Bs</h1>
    <form method="post">
        <input name="tasa" required>
        <button>Guardar</button>
    </form>
    """

# ---------------- PRODUCTOS ----------------

@app.route("/productos")
def productos():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM productos WHERE activo=1")
    productos = cursor.fetchall()

    conn.close()

    html = "<h1>Menú</h1>"

    for p in productos:
        html += f"""
        {p[1]} - ${p[2]} ({p[3]})
        <a href="/eliminar_producto/{p[0]}">❌</a><br>
        """

    html += """
    <hr>
    <h3>Nuevo producto / combo</h3>
    <form action="/crear_producto" method="post">
        Nombre:<input name="nombre" required><br>
        Precio:<input name="precio" required><br>
        Tipo:
        <select name="tipo">
            <option>producto</option>
            <option>combo</option>
        </select><br>
        Descripción:<input name="descripcion"><br>
        <button>Crear</button>
    </form>

    <br><a href="/">Volver</a>
    """

    return html

@app.route("/crear_producto", methods=["POST"])
def crear_producto():
    try:
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "").strip()
        tipo = request.form.get("tipo", "producto")
        descripcion = request.form.get("descripcion", "")

        if not nombre or not precio:
            return "Error: datos incompletos"

        precio = float(precio)

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO productos (nombre, precio, tipo, descripcion)
        VALUES (?, ?, ?, ?)
        """, (nombre, precio, tipo, descripcion))

        conn.commit()
        conn.close()

        return redirect("/productos")

    except Exception as e:
        return f"Error: {e}"

@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE productos SET activo=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/productos")

# ---------------- CONSECUTIVO ----------------

def siguiente_numero():
    hoy = datetime.date.today().isoformat()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT MAX(numero_orden)
    FROM ordenes
    WHERE date(fecha_hora)=?
    """, (hoy,))

    ultimo = cursor.fetchone()[0]
    conn.close()

    return 1 if ultimo is None else ultimo + 1

# ---------------- HOME ----------------

@app.route("/")
def home():
    tasa = obtener_tasa()

    if not tasa:
        return redirect("/config")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes WHERE estado!='cerrada'")
    ordenes = cursor.fetchall()

    conn.close()

    html = f"""
    <h1>🍜 China House POS</h1>

    <b>Tasa Bs:</b> {tasa}
    <a href="/config">✏️</a>
    <br>
    <a href="/productos">Gestionar menú</a>

    <hr>

    <h3>Nueva orden</h3>
    <form action="/crear_orden" method="post">
        Tipo:
        <select name="tipo">
            <option>Mesa</option>
            <option>Delivery</option>
            <option>Pickup</option>
        </select><br>

        Referencia:<input name="referencia"><br>
        Cliente:<input name="cliente"><br>

        <button>Crear orden</button>
    </form>

    <hr>

    <h3>Órdenes activas</h3>
    """

    for o in ordenes:
        html += f"""
        #{o[1]} - {o[3]} {o[4]}
        <a href="/orden/{o[0]}">Abrir</a><br>
        """

    return html

# ---------------- CREAR ORDEN ----------------

@app.route("/crear_orden", methods=["POST"])
def crear_orden():
    tipo = request.form.get("tipo", "")
    referencia = request.form.get("referencia", "")
    cliente = request.form.get("cliente", "")

    numero = siguiente_numero()
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha_hora, tipo, referencia, cliente, estado)
    VALUES (?, ?, ?, ?, ?, 'abierta')
    """, (numero, fecha, tipo, referencia, cliente))

    conn.commit()
    orden_id = cursor.lastrowid
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- ORDEN ----------------

@app.route("/orden/<int:orden_id>")
def orden(orden_id):
    tasa = obtener_tasa()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT id,nombre,precio FROM productos WHERE activo=1")
    productos = cursor.fetchall()

    conn.close()

    total = sum(i[3] for i in items)
    total_bs = round(total * tasa, 2)

    html = f"<h2>Total: ${total} | Bs {total_bs}</h2><hr>"

    for i in items:
        html += f"{i[2]} - ${i[3]}<br>"

    html += "<hr><h3>Agregar</h3>"

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
    p = cursor.fetchone()

    if not p:
        return "Producto no encontrado"

    cursor.execute("""
    INSERT INTO orden_items (orden_id, producto, precio)
    VALUES (?, ?, ?)
    """, (orden_id, p[0], p[1]))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
