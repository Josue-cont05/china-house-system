from flask import Flask, request, redirect
import sqlite3
import datetime
import pytz
import os

app = Flask(__name__)

# ---------------- DB ----------------

def init_db():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # ---------------- PRODUCTOS ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        precio REAL
    )
    """)

    # 🔥 agregar columna categoria_id (seguro)
    try:
        cursor.execute("ALTER TABLE productos ADD COLUMN categoria_id INTEGER")
    except:
        pass


# ------------------ CATEGORIAS ------------------

# Crear tabla categorias
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT
    )
    """)

    # Insertar categorias iniciales (solo si está vacía)
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        categorias = [
            ("Arroces",),
            ("Bebida",),
            ("Delivery",),
            ("Extras",)
        ]

        cursor.executemany(
            "INSERT INTO categorias (nombre) VALUES (?)",
            categorias
        )
    # ---------------- ORDENES ----------------
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
    # 🔥 columna descuento
    cursor.execute("PRAGMA table_info(ordenes)")
    columnas = [col[1] for col in cursor.fetchall()]

    if "descuento" not in columnas:
        cursor.execute("ALTER TABLE ordenes ADD COLUMN descuento REAL DEFAULT 0")
        conn.commit()
    
    # 🔥 Verificar si existe la columna "observacion"
    cursor.execute("PRAGMA table_info(ordenes)")
    columnas = [col[1] for col in cursor.fetchall()]

    if "observacion" not in columnas:
        cursor.execute("ALTER TABLE ordenes ADD COLUMN observacion TEXT")
        conn.commit()


    
    # ---------------- ITEMS ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orden_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orden_id INTEGER,
        producto TEXT,
        precio REAL
    )
    """)

    # ---------------- PAGOS ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orden_id INTEGER,
        metodo TEXT,
        monto REAL,
        referencia TEXT,
        fecha TEXT
    )
    """)

    # ---------------- TASA ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        valor REAL
    )
    """)

    # 🔥 asegurar tasa inicial
    cursor.execute("SELECT COUNT(*) FROM tasa")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO tasa (valor) VALUES (36)")

    # ---------------- INGREDIENTES (BASE FUTURA) ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ingredientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        unidad TEXT,
        stock REAL
    )
    """)

    conn.commit()
    conn.close()

# ---------------- PRODUCTOS ----------------

def cargar_productos():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # 🔍 Verificar si ya hay productos
    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # 🔥 CREAR CATEGORÍAS
    categorias = [
        ("Arroces",),
        ("Bebida",),
        ("Delivery",),
        ("Extras",)
    ]

    cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", categorias)

    # 🔍 Obtener IDs de categorías
    cursor.execute("SELECT id, nombre FROM categorias")
    cat_dict = {nombre: id for id, nombre in cursor.fetchall()}

    # 🔥 PRODUCTOS
    productos = [
        # Arroces
        ("Cerdo-Jamon Personal", 5.5, "Arroces"),
        ("Cerdo-Jamon Mediano", 8.5, "Arroces"),
        ("Cerdo-Jamon Familiar", 11.5, "Arroces"),
        ("Pollo-Jamon Personal", 5.5, "Arroces"),
        ("Pollo-Jamon Mediano", 8.5, "Arroces"),
        ("Pollo-Jamon Familiar", 11.5, "Arroces"),
        ("Pollo-Cerdo Personal", 6.5, "Arroces"),
        ("Pollo-Cerdo Mediano", 9.5, "Arroces"),
        ("Pollo-Cerdo Familiar", 12.5, "Arroces"),
        ("Pollo-Camaron Personal", 6.5, "Arroces"),
        ("Pollo-Camaron Mediano", 9.5, "Arroces"),
        ("Pollo-Camaron Familiar", 12.5, "Arroces"),
        ("Especial Personal", 7.5, "Arroces"),
        ("Especial Mediano", 10.5, "Arroces"),
        ("Especial Familiar", 15.5, "Arroces"),

        # Bebidas
        ("Refresco 1 Lt", 1.1, "Bebida"),
        ("Refresco 1.5 Lt", 0, "Bebida"),
        ("Refresco 2 Lt", 0, "Bebida"),

        # Delivery
        ("Delivery 1", 1, "Delivery"),
        ("Delivery 1.5", 1.5, "Delivery"),
        ("Delivery 2", 2, "Delivery"),
        ("Delivery 2.5", 2.5, "Delivery"),
        ("Delivery 3", 3, "Delivery"),

        # Extras
        ("Salsa extra", 0.25, "Extras"),
    ]

    # 🔥 Insertar productos con categoría
    for nombre, precio, categoria in productos:
        categoria_id = cat_dict.get(categoria)
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id) VALUES (?, ?, ?)",
            (nombre, precio, categoria_id)
        )

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
    WHERE fecha_hora LIKE ?
    """, (hoy + "%",))

    ultimo = cursor.fetchone()[0]

    conn.close()

    return 1 if ultimo is None else ultimo + 1

# ---------------- POS PRINCIPAL ----------------

@app.route("/")
def index():
    import sqlite3

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, numero_orden, fecha_hora, tipo, referencia, cliente, estado, observacion, descuento FROM ordenes ORDER BY id DESC")
    ordenes = cursor.fetchall()

    conn.close()

    html = """
    <html>
    <head>
    <style>
    body {
        font-family: Arial;
        margin: 0;
        background: #f5f6fa;
    }

    .header {
        background: #2c3e50;
        color: white;
        padding: 15px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .titulo {
        font-size: 22px;
        font-weight: bold;
    }

    .menu-top a {
        margin-left: 10px;
        color: white;
        text-decoration: none;
        background: #34495e;
        padding: 8px 10px;
        border-radius: 5px;
        font-size: 13px;
    }

    .contenedor {
        display: flex;
        padding: 20px;
        gap: 20px;
    }

    .panel-izq {
        width: 35%;
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }

    .panel-der {
        width: 65%;
    }

    input, select {
        width: 100%;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
        border: 1px solid #ccc;
    }

    button {
        width: 100%;
        padding: 12px;
        background: #27ae60;
        color: white;
        border: none;
        border-radius: 5px;
        margin-top: 10px;
        font-size: 16px;
    }

    .card {
        background: white;
        padding: 15px;
        margin-bottom: 10px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .estado {
        padding: 5px 10px;
        border-radius: 5px;
        color: white;
        font-size: 12px;
    }

    .btn-ver {
        background: #3498db;
        color: white;
        padding: 6px 10px;
        border-radius: 5px;
        text-decoration: none;
    }

    .btn-cobrar {
        background: #27ae60;
        color: white;
        padding: 6px 10px;
        border-radius: 5px;
        text-decoration: none;
    }
    </style>
    </head>

    <body>

    <div class="header">
        <div class="titulo">🍜 China House POS</div>

        <div class="menu-top">
            <a href="/cambiar_tasa">💱 Tasa</a>
            <a href="/exportar">📦 Exportar</a>
            <a href="/cierre">📊 Cierre</a>
            <a href="/menu">📋 Menú</a>
            <a href="/cocina">🍳 Cocina</a>
        </div>
    </div>

    <div class="contenedor">

        <!-- 🔹 PANEL IZQUIERDO -->
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

                <label>Cliente</label>
                <input name="cliente">

                <button type="submit">Crear Orden</button>

            </form>

        </div>

        <!-- 🔹 PANEL DERECHO -->
        <div class="panel-der">

            <h3>Órdenes activas</h3>
    """

    for o in ordenes:
        if o[6] not in ["abierta", "en cocina"]:
            continue

        html += f"""
        <div class="card">

            <div>
                <b>Orden #{o[1]}</b><br>
                {o[3]} - {o[4]}<br>
                👤 {o[5] if o[5] else '-'}
            </div>

            <div style="text-align:right;">
                <span class="estado" style="background:#f39c12;">
                    {o[6]}
                </span><br><br>

                <a href="/orden/{o[0]}" class="btn-ver">Ver</a>
                <a href="/cobrar/{o[0]}" class="btn-cobrar">Cobrar</a>
            </div>

        </div>
        """

    html += "<h3>Historial</h3>"

    for o in ordenes:
        if o[6] != "cerrada":
            continue

        html += f"""
        <div style="background:#ecf0f1; padding:10px; margin-bottom:5px; border-radius:5px;">
            ✔ Orden #{o[1]} - {o[5] if o[5] else '-'}
        </div>
        """

    html += """
        </div>

    </div>

    </body>
    </html>
    """

    return html
# ---------------- MENU ----------------
@app.route("/menu")
def menu():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # Productos
    cursor.execute("SELECT id, nombre, precio FROM productos")
    productos = cursor.fetchall()

    # Categorías
    cursor.execute("SELECT id, nombre FROM categorias")
    categorias = cursor.fetchall()

    conn.close()

    html = """
    <h1>📋 Menú</h1>

    <a href="/">⬅ Volver</a><br><br>

    <h2>Agregar producto</h2>
    """

    # 🔥 FORMULARIO
    html += """
    <form action="/agregar_producto" method="post">
        Nombre: <input name="nombre"><br><br>
        Precio: <input name="precio"><br><br>

        Categoría:
        <select name="categoria_id">
    """

    # 🔥 OPCIONES DINÁMICAS
    for c in categorias:
        html += f"<option value='{c[0]}'>{c[1]}</option>"

    # 🔥 CIERRE FORM
    html += """
        </select><br><br>

        <button>Agregar</button>
    </form>

    <hr>

    <h2>Productos actuales</h2>
    """

    # 🔥 LISTADO
    for p in productos:
        html += f"""
        <div>
            {p[1]} - ${p[2]}

            <a href="/editar_producto/{p[0]}">✏️ Editar</a>
            <a href="/eliminar_producto/{p[0]}">❌ Eliminar</a>
        </div>
        """

    return html

# ---------------- Agregar producto ----------------
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    nombre = request.form.get("nombre", "").strip()

    try:
        precio = float(request.form["precio"])
        categoria_id = int(request.form["categoria_id"])
    except:
        return "Datos inválidos"

    if nombre == "":
        return "Nombre requerido"

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO productos (nombre, precio, categoria_id)
    VALUES (?, ?, ?)
    """, (nombre, precio, categoria_id))

    conn.commit()
    conn.close()

    return redirect("/menu")
# ---------------- ELIMINAR PRODUCTO ----------------
@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM productos WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return redirect("/menu")
    
# ---------------- EDITAR PRODUCTO ----------------

@app.route("/editar_producto/<int:id>", methods=["GET", "POST"])
def editar_producto(id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # 🔹 traer categorías
    cursor.execute("SELECT id, nombre FROM categorias")
    categorias = cursor.fetchall()

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()

        try:
            precio = float(request.form["precio"])
            categoria_id = int(request.form["categoria_id"])
        except:
            return "Datos inválidos"

        cursor.execute("""
        UPDATE productos 
        SET nombre=?, precio=?, categoria_id=?
        WHERE id=?
        """, (nombre, precio, categoria_id, id))

        conn.commit()
        conn.close()

        return redirect("/menu")

    # 🔹 traer producto actual
    cursor.execute("""
    SELECT nombre, precio, categoria_id 
    FROM productos WHERE id=?
    """, (id,))
    p = cursor.fetchone()

    if not p:
        conn.close()
        return "Producto no encontrado"

    html = f"""
    <h1>Editar producto</h1>

    <form method="post">
        Nombre: <input name="nombre" value="{p[0]}"><br><br>
        Precio: <input name="precio" value="{p[1]}"><br><br>

        Categoría:
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
    """

    conn.close()
    return html


# ---------------- NUEVA ORDEN ----------------

@app.route("/nueva_orden")
def nueva_orden():
    return """
    <html>
    <head>
    <style>
    body {
        font-family: Arial;
        padding: 20px;
        background: #f5f6fa;
    }

    h2 {
        margin-bottom: 20px;
    }

    input, select {
        padding: 10px;
        margin: 5px 0;
        width: 250px;
        border-radius: 5px;
        border: 1px solid #ccc;
    }

    button {
        padding: 12px 20px;
        background: #27ae60;
        color: white;
        border: none;
        border-radius: 5px;
        margin-top: 10px;
        cursor: pointer;
    }

    button:hover {
        background: #219150;
    }

    .volver {
        display: inline-block;
        margin-top: 20px;
        color: #3498db;
        text-decoration: none;
    }
    </style>
    </head>

    <body>

    <h2>🆕 Nueva Orden</h2>

    <form action="/crear_orden" method="post">

        <label>Tipo:</label><br>
        <select name="tipo">
            <option value="Mesa">Mesa</option>
            <option value="Delivery">Delivery</option>
            <option value="Para llevar">Para llevar</option>
        </select><br><br>

        <label>Referencia:</label><br>
        <input name="referencia" required><br><br>

        <label>Cliente:</label><br>
        <input name="cliente"><br><br>

        <button type="submit">Crear Orden</button>

    </form>

    <a href="/" class="volver">⬅ Volver</a>

    </body>
    </html>
    """
    
# ---------------- CREAR ORDEN ----------------

@app.route("/crear_orden", methods=["POST"])
def crear_orden():
    tipo = request.form.get("tipo")
    referencia = request.form.get("referencia", "")
    cliente = request.form.get("cliente", "")

    numero = siguiente_numero()
    
    venezuela = pytz.timezone("America/Caracas")
    fecha = datetime.datetime.now(venezuela).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha_hora, tipo, referencia, cliente, estado)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (numero, fecha, tipo, referencia, cliente, "abierta"))

    cursor.execute("SELECT last_insert_rowid()")
    orden_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- ORDEN ----------------

@app.route("/orden/<int:orden_id>")
def orden(orden_id):
    import sqlite3
    from collections import defaultdict

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # 🔹 Obtener orden
    cursor.execute("SELECT id, numero_orden, fecha_hora, tipo, referencia, cliente, estado, observacion, descuento FROM ordenes WHERE id=?", (orden_id,))
    o = cursor.fetchone()

    if not o:
        return "Orden no encontrada"

    # 🔹 Obtener productos con categoría
    cursor.execute("""
    SELECT p.id, p.nombre, p.precio, c.nombre
    FROM productos p
    LEFT JOIN categorias c ON p.categoria_id = c.id
    """)
    productos = cursor.fetchall()

    # 🔹 Obtener items
    cursor.execute("""
    SELECT producto, precio, id
    FROM orden_items
    WHERE orden_id=?
    """, (orden_id,))
    items = cursor.fetchall()

    conn.close()

    # 🔹 Totales
    total_usd = sum(float(i[1]) for i in items)
    
   # 🔹 Obtener tasa desde DB
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()
    
    tasa = row[0] if row else 1

    conn.close()

    total_bs = total_usd * tasa

    descuento = o[8] if len(o) > 8 and o[8] else 0
    total_bs_final = max(total_bs - descuento, 0)

    # 🔹 HTML BASE
    html = f"""
    <html>
    <head>
    <style>
    body {{
        font-family: Arial;
        display: flex;
    }}

    .productos {{
        width: 60%;
        padding: 20px;
    }}

    .panel {{
        width: 40%;
        padding: 20px;
        background: #f4f4f4;
    }}

    .btn {{
        width: 100%;
        padding: 15px;
        margin: 5px 0;
        background: #27ae60;
        color: white;
        border: none;
        border-radius: 5px;
    }}

    .categoria {{
        font-weight: bold;
        margin-top: 15px;
        background: #333;
        color: white;
        padding: 5px;
        border-radius: 5px;
    }}

    .grid-productos {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
    }}

    .btn-accion {{
        display: block;
        padding: 12px;
        margin: 5px 0;
        text-align: center;
        color: white;
        text-decoration: none;
        border-radius: 5px;
    }}

    .cocina {{ background: #e67e22; }}
    .cobrar {{ background: #27ae60; }}
    .volver {{ background: #7f8c8d; }}

    .total {{
        font-size: 20px;
        margin-top: 10px;
    }}
    </style>
    </head>

    <body>

    <div class="productos">
    <h2>Agregar productos</h2>
    """

    # 🔥 Agrupar por categoría
    categorias = defaultdict(list)

    for p in productos:
        categoria = p[3] if p[3] else "Sin categoría"
        categorias[categoria].append(p)

    # 🔥 Render productos con orden vertical
    for categoria, lista in categorias.items():

        html += f"<div class='categoria'>🍽 {categoria}</div>"
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
            html += f"""
            <a href="/agregar/{orden_id}/{p[0]}">
                <button class="btn">{p[1]} - ${p[2]}</button>
            </a>
            """

        html += "</div>"

    html += "</div>"

    # 🔥 PANEL DERECHO
    html += f"""
    <div class="panel">

        <div style="display:flex; justify-content:flex-end; gap:10px;">
            <a href="/editar_orden/{orden_id}" style="background:#2980b9; color:white; padding:8px 12px; border-radius:5px;">✏️</a>
            <a href="/eliminar_orden/{orden_id}" style="background:#e74c3c; color:white; padding:8px 12px; border-radius:5px;">🗑</a>
        </div>

        <h2>Orden #{o[1]}</h2>
        <p>Tipo: {o[3]}</p>
        <p>Referencia: {o[4]}</p>
        <p>Cliente: {o[5] if o[5] else '-'}</p>
        <p>Hora: {o[2]}</p>
        <p>Estado: {o[6]}</p>

        <p><b>Observación:</b> {o[7] if len(o) > 7 and o[7] else '-'}</p>

        <h3>Productos</h3>
    """

    for i in items:
        html += f"""
        <div style='display:flex; justify-content:space-between; margin:5px 0;'>
            <span>{i[0]} - ${i[1]}</span>
            <a href="/eliminar_item/{i[2]}/{orden_id}" style="color:red;">❌</a>
        </div>
        """

    html += f"""
        <div class="total">USD: ${total_usd}</div>
        <div class="total">Bs: {total_bs}</div>

        <p>Descuento: Bs {descuento}</p>

        <div class="total">Total Final Bs: {total_bs_final}</div>

        <a href="/enviar_cocina/{orden_id}" class="btn-accion cocina">
            Enviar a cocina
        </a>

        <a href="/cobrar/{orden_id}" class="btn-accion cobrar">
            Cobrar
        </a>

        <a href="/" class="btn-accion volver">
            Volver
        </a>

    </div>

    </body>
    </html>
    """

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

# ---------------- COCINA ----------------

@app.route("/enviar_cocina/<int:orden_id>")
def cocina(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado='en cocina' WHERE id=?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")

# ---------------- COBRAR ----------------

@app.route("/cobrar/<int:orden_id>", methods=["GET", "POST"])
def cobrar(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()
    
    # 🔥 AGREGAR ESTO
    cursor.execute("SELECT id, numero_orden, fecha_hora, tipo, referencia, cliente, estado, observacion, descuento FROM ordenes WHERE id=?", (orden_id,))
    o = cursor.fetchone()

    # Obtener items
    cursor.execute("SELECT precio FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    if len(items) == 0:
        conn.close()
        return "No puedes cobrar una orden vacía"

    total_usd = sum(i[0] for i in items)

    # Obtener tasa
    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()
    tasa = row[0] if row else 1

    total_bs = total_usd * tasa
    descuento_bs = o[8] if len(o) > 8 and o[8] else 0
    total_bs_final = total_bs - descuento_bs

    if total_bs_final < 0:
        total_bs_final = 0
    
    
    if request.method == "POST":
        metodo1 = request.form["metodo1"]
        monto1 = float(request.form["monto1"] or 0)
        ref1 = request.form.get("ref1", "")
        descuento = float(request.form.get("descuento", 0))
        descuento_usd = descuento / tasa
        
        metodo2 = request.form.get("metodo2")
        monto2 = float(request.form.get("monto2") or 0)
        ref2 = request.form.get("ref2", "")

        venezuela = pytz.timezone("America/Caracas")
        fecha = datetime.datetime.now(venezuela).strftime("%Y-%m-%d %H:%M:%S")
        
        def convertir(metodo, monto):
            if metodo == "usd":
                return monto, monto * tasa
            elif metodo in ["bs_efectivo", "bs_pago_movil"]:
                return monto / tasa, monto
            else:
                return 0, 0


        usd1, bs1 = convertir(metodo1, monto1)
        usd2, bs2 = convertir(metodo2, monto2) if metodo2 else (0, 0)

        total_pagado_usd = usd1 + usd2

        # VALIDACIÓN
        total_con_descuento = total_usd - descuento_usd
        if total_con_descuento < 0:
            total_con_descuento = 0

        if total_pagado_usd < total_con_descuento:
            return "Pago insuficiente"

        # GUARDAR PAGOS
        cursor.execute(
            "INSERT INTO pagos VALUES (NULL, ?, ?, ?, ?, ?)",
            (orden_id, metodo1, monto1, ref1, fecha)
        )

        if metodo2:
            cursor.execute(
                "INSERT INTO pagos VALUES (NULL, ?, ?, ?, ?, ?)",
                (orden_id, metodo2, monto2, ref2, fecha)
            )

        # 🔥 SIEMPRE cerrar orden
        cursor.execute("""
        UPDATE ordenes 
        SET estado='cerrada', descuento=?
        WHERE id=?
        """, (descuento, orden_id))
        conn.commit()
        conn.close()

        return redirect("/")


    return f"""
    <h1> Cobro Orden #{orden_id}</h1>

    <h2>Total USD: ${total_usd}</h2>
    <h2>Total Bs: Bs {total_bs}</h2>

    <form method="post">
    
    <h3>Pago 1</h3>
       <select name="metodo1">
            <option value="bs_pago_movil" selected>Pago móvil</option>
            <option value="usd">$</option>
            <option value="bs_efectivo">Bs efectivo</option>
        </select>

    <input name="monto1" value="{total_bs}"><br>
    <input name="ref1" placeholder="Referencia"><br><br>

    <h3>Pago 2 (opcional)</h3>
    <select name="metodo2">
        <option value="">-- ninguno --</option>
        <option value="usd">$</option>
        <option value="bs_efectivo">Bs efectivo</option>
        <option value="bs_pago_movil">Pago móvil</option>
    </select>

    <input name="monto2" placeholder="Monto"><br>
    <input name="ref2" placeholder="Referencia"><br><br>

    <label>Descuento (Bs):</label><br>
    <input name="descuento" type="number" step="0.01" value="0"><br><br>

    <button>Confirmar pago</button>

    </form>

    <a href="/orden/{orden_id}">⬅ Volver</a>
    """

# ---------------- CIERRE ----------------
@app.route("/cierre")
def cierre():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    hoy = datetime.date.today().isoformat()

    # Total órdenes
    cursor.execute("""
    SELECT COUNT(*) FROM ordenes
    WHERE date(fecha_hora) = ? AND estado = 'cerrada'
    """, (hoy,))
    total_ordenes = cursor.fetchone()[0]

    # Total USD
    cursor.execute("""
    SELECT SUM(monto) FROM pagos
    WHERE metodo = 'usd' AND date(fecha) = ?
    """, (hoy,))
    total_usd = cursor.fetchone()[0] or 0

    # Total Bs efectivo
    cursor.execute("""
    SELECT SUM(monto) FROM pagos
    WHERE metodo = 'bs_efectivo' AND date(fecha) = ?
    """, (hoy,))
    total_bs_efectivo = cursor.fetchone()[0] or 0

    # Total Pago Móvil
    cursor.execute("""
    SELECT SUM(monto) FROM pagos
    WHERE metodo = 'bs_pago_movil' AND date(fecha) = ?
    """, (hoy,))
    total_pago_movil = cursor.fetchone()[0] or 0

    # Total general en USD (referencial)
    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    tasa = cursor.fetchone()[0]

    total_bs = total_bs_efectivo + total_pago_movil
    total_general_usd = total_usd + (total_bs / tasa)

    conn.close()

    return f"""
    <h1>📊 Cierre del día</h1>

    <h2>Órdenes cerradas: {total_ordenes}</h2>

    <h3>💵 USD: ${total_usd}</h3>
    <h3>💰 Bs efectivo: Bs {total_bs_efectivo}</h3>
    <h3>📱 Pago móvil: Bs {total_pago_movil}</h3>

    <hr>

    <h2>Total Bs: Bs {total_bs}</h2>
    <h2>Total general (USD ref): ${round(total_general_usd, 2)}</h2>

    <a href="/">⬅ Volver</a>
    """
# ---------------- COCINA ----------------
@app.route("/cocina")
def pantalla_cocina():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, numero_orden, tipo, referencia, fecha_hora
    FROM ordenes
    WHERE estado = 'en cocina'
    ORDER BY fecha_hora ASC
    """)

    ordenes = cursor.fetchall()

    ahora = datetime.datetime.now()

    html = """
    <html>
    <head>

    <meta http-equiv="refresh" content="5">

    <style>
        body { 
            font-family: Arial; 
            background:black; 
            color:white; 
            font-size:22px;
        }

        .container {
            display:flex;
        }

        .col {
            width:50%;
            padding:10px;
        }

        .orden {
            border:4px solid white;
            margin:10px;
            padding:15px;
            border-radius:10px;
        }

        .green { border-color: green; }
        .orange { border-color: orange; }
        .red { border-color: red; }

        .btn {
            padding:10px;
            background:green;
            color:white;
            border:none;
            font-size:18px;
        }

        h1 { text-align:center; }
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

    <h1> COCINA</h1>

    <div class="container">
        <div class="col">
            <h2> ESTACIÓN ARROZ</h2>
    """

    arroz_html = ""
    caliente_html = ""

    total_ordenes = len(ordenes)

    for o in ordenes:
        fecha_orden = datetime.datetime.strptime(o[4], "%Y-%m-%d %H:%M:%S")
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
            <h2>Orden #{o[1]}</h2>
            <p>{o[2]} - {o[3]}</p>
            <p>⏱ {int(minutos)} min</p>
        """

        for i in items:
            bloque += f"<p>• {i[0]}</p>"

        bloque += f"""
            <a href="/listo/{o[0]}">
                <button class="btn"> LISTO</button>
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
            <h2> ESTACIÓN CALIENTE</h2>
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
# ---------------- LISTO ---------------- 

@app.route("/listo/<int:orden_id>")
def marcar_listo(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE ordenes SET estado='listo' WHERE id=?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/cocina")

# ---------------- EXPORTAR ----------------    
@app.route("/exportar")
def exportar():
    import sqlite3
    import csv
    from flask import Response

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # 🔹 Traer órdenes
    cursor.execute("SELECT id, numero_orden, fecha_hora, tipo, referencia, cliente, estado, observacion, descuento FROM ordenes")
    ordenes = cursor.fetchall()

    filas = []

    for o in ordenes:
        orden_id = o[0]

        # 🔹 Items
        cursor.execute("""
        SELECT producto, precio 
        FROM orden_items 
        WHERE orden_id=?
        """, (orden_id,))
        items = cursor.fetchall()

        # 🔹 Pagos
        cursor.execute("""
        SELECT metodo, monto, referencia 
        FROM pagos 
        WHERE orden_id=?
        """, (orden_id,))
        pagos = cursor.fetchall()

        # 🔹 Totales
        total_usd = sum(i[1] for i in items)
        tasa = 36
        total_bs = total_usd * tasa
        descuento = o[8] if len(o) > 8 and o[8] else 0
        total_final = max(total_bs - descuento, 0)

        # 🔥 LÓGICA INTELIGENTE
        for idx, item in enumerate(items):

            producto = item[0]
            precio = item[1]

            # SOLO PRIMER PRODUCTO lleva total
            total_usd_col = total_usd if idx == 0 else 0
            total_bs_col = total_final if idx == 0 else 0

            # ASIGNAR PAGOS POR FILA
            metodo = ""
            monto = 0
            referencia = ""

            if idx < len(pagos):
                metodo = pagos[idx][0]
                monto = pagos[idx][1]
                referencia = pagos[idx][2]

            filas.append([
                orden_id,
                o[2],  # fecha
                o[3],  # tipo
                o[4],  # referencia orden
                o[5],  # cliente
                producto,
                precio,
                metodo,
                monto,
                referencia,
                total_usd_col,
                total_bs_col
            ])

    conn.close()

    # 🔹 CSV
    def generate():
        yield "Orden,Fecha,Tipo,Ref Orden,Cliente,Producto,Precio USD,Metodo,Monto,Referencia Pago,Total USD,Total Bs\n"
        for f in filas:
            yield ",".join(str(x) for x in f) + "\n"

    return Response(generate(), mimetype="text/csv")

# ---------------- ELIMINAR PRODUCTOR DE LA ORDEN ----------------
@app.route("/eliminar_item/<int:item_id>/<int:orden_id>")
def eliminar_item(item_id, orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM orden_items WHERE id=?", (item_id,))

    conn.commit()
    conn.close()

    return redirect(f"/orden/{orden_id}")


# ---------------- EDITAR ORDEN ----------------
@app.route("/editar_orden/<int:orden_id>", methods=["GET", "POST"])
def editar_orden(orden_id):
    import sqlite3
    from flask import request, redirect

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # 🔥 SI ES POST → GUARDAR
    if request.method == "POST":
        tipo = request.form.get("tipo")
        referencia = request.form.get("referencia")
        cliente = request.form.get("cliente")
        observacion = request.form.get("observacion")

        cursor.execute("""
        UPDATE ordenes
        SET tipo=?, referencia=?, cliente=?, observacion=?
        WHERE id=?
        """, (tipo, referencia, cliente, observacion, orden_id))

        conn.commit()
        conn.close()

        return redirect(f"/orden/{orden_id}")

    # 🔥 SI ES GET → MOSTRAR FORMULARIO
    cursor.execute("SELECT * FROM ordenes WHERE id=?", (orden_id,))
    o = cursor.fetchone()

    conn.close()

    return f"""
    <h2>Editar Orden #{o[1]}</h2>

    <form method="POST">

        <label>Tipo:</label><br>
        <input name="tipo" value="{o[3]}"><br><br>

        <label>Referencia:</label><br>
        <input name="referencia" value="{o[4]}"><br><br>

        <label>Cliente:</label><br>
        <input name="cliente" value="{o[5] if o[5] else ''}"><br><br>

        <label>Observación:</label><br>
        <textarea name="observacion" 
        style="width:100%; height:80px;">
{o[7] if len(o) > 7 and o[7] else ''}
        </textarea><br><br>

        <button type="submit">Guardar</button>

    </form>

    <br>
    <a href="/orden/{orden_id}">Volver</a>
    """
# ---------------- ELIMINAR ORDEN ----------------
@app.route("/eliminar_orden/<int:orden_id>")
def eliminar_orden(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM orden_items WHERE orden_id=?", (orden_id,))
    cursor.execute("DELETE FROM pagos WHERE orden_id=?", (orden_id,))
    cursor.execute("DELETE FROM ordenes WHERE id=?", (orden_id,))

    conn.commit()
    conn.close()

    return redirect("/")


# ---------------- CAMBIAR TASA ----------------

@app.route("/cambiar_tasa", methods=["GET", "POST"])
def cambiar_tasa():
    import sqlite3

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    if request.method == "POST":
        nueva_tasa = float(request.form["tasa"])

        cursor.execute("UPDATE tasa SET valor=?", (nueva_tasa,))
        conn.commit()

    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()

    tasa_actual = row[0] if row else 1

    conn.close()

    return f"""
    <html>
    <body style="font-family:Arial; padding:40px;">

    <h2>💱 Cambiar tasa</h2>

    <p>Tasa actual: <b>{tasa_actual}</b></p>

    <form method="post">
        <input name="tasa" placeholder="Nueva tasa" style="padding:10px; width:200px;">
        <br><br>
        <button style="padding:10px 20px; background:#27ae60; color:white; border:none;">
            Guardar
        </button>
    </form>

    <br><br>

    <a href="/">⬅ Volver</a>

    </body>
    </html>
    """

# ---------------- ORDEN - COCINA ----------------
from flask import jsonify

@app.route("/ordenes_cocina")
def ordenes_cocina():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, numero_orden, tipo, cliente
    FROM ordenes
    WHERE estado = 'en cocina'
    """)

    ordenes = []

    for o in cursor.fetchall():
        cursor.execute("""
        SELECT producto FROM orden_items WHERE orden_id=?
        """, (o[0],))

        items = [i[0] for i in cursor.fetchall()]

        ordenes.append({
            "id": o[0],
            "numero": o[1],
            "tipo": o[2],
            "cliente": o[3],
            "items": items
        })

    conn.close()
    return jsonify(ordenes)

# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    cargar_productos()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

