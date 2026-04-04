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
    WHERE date(fecha_hora) = ?
    """, (hoy,))

    ultimo = cursor.fetchone()[0]

    conn.close()

    return 1 if ultimo is None else ultimo + 1

# ---------------- POS PRINCIPAL ----------------

@app.route("/")
def pos():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes WHERE estado != 'cerrada'")
    ordenes = cursor.fetchall()

    conn.close()

    html = """
    <html>
    <head>
    <style>
        body { font-family: Arial; margin:20px; }
        .orden { border:1px solid #ccc; padding:10px; margin:10px; }
        input, select { padding:8px; margin:5px; }
        button { padding:10px; }
    </style>
    </head>
    <body>

    <h1>🍜 China House POS</h1>

    <a href="/cierre">📊 Ver cierre del día</a><br><br>

    <a href="/tasa">💱 Cambiar tasa</a>

    <a href="/cocina">🍳 Pantalla cocina</a><br><br>

    <a href="/menu">📋 Administrar menú</a><br><br>

    <a href="/exportar">📥 Exportar ventas</a><br><br>

    <h2>Nueva Orden</h2>
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

        <button type="submit">Crear</button>
    </form>

    <hr>

    <h2>Órdenes activas</h2>
    """

    for o in ordenes:
        html += f"""
        <div class="orden">
            <b>#{o[1]}</b> | {o[3]} - {o[4]}<br>
            Cliente: {o[5] if o[5] else '-'}<br>
            Hora: {o[2]}<br>
            Estado: {o[6]}<br>
            <a href="/orden/{o[0]}">Abrir</a>
        </div>
        """

    html += "</body></html>"
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
    cursor.execute("SELECT * FROM ordenes WHERE id=?", (orden_id,))
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

    # 🔹 Obtener items (SIN JOIN ❗)
    cursor.execute("""
    SELECT producto, precio, id
    FROM orden_items
    WHERE orden_id=?
    """, (orden_id,))
    items = cursor.fetchall()

    conn.close()

    # 🔹 Totales
    total_usd = sum(i[1] for i in items)
    tasa = 36
    total_bs = total_usd * tasa

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

    # 🔥 AGRUPAR POR CATEGORÍA
    categorias = defaultdict(list)

    for p in productos:
        categoria = p[3] if p[3] else "Sin categoría"
        categorias[categoria].append(p)

    # 🔥 RENDER POR CATEGORÍA + ORDEN VERTICAL
    for categoria, lista in categorias.items():

        html += f"<div class='categoria'>🍽 {categoria}</div>"
        html += "<div class='grid-productos'>"

        # 🔥 ORDEN TIPO COLUMNA VERTICAL
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
            <a href="/editar_orden/{orden_id}" 
               style="background:#2980b9; color:white; padding:8px 12px; border-radius:5px;">
                ✏️
            </a>

            <a href="/eliminar_orden/{orden_id}" 
               style="background:#e74c3c; color:white; padding:8px 12px; border-radius:5px;">
                🗑
            </a>
        </div>

        <h2>Orden #{o[1]}</h2>
        <p>Tipo: {o[3]}</p>
        <p>Referencia: {o[4]}</p>
        <p>Cliente: {o[5] if o[5] else '-'}</p>
        <p>Hora: {o[2]}</p>
        <p>Estado: {o[6]}</p>

        <div class="lista-items">

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
    </div>

    <div class="total">USD: ${total_usd}</div>
    <div class="total">Bs: {total_bs}</div>

    <p>Descuento: Bs {o[8] if len(o) > 8 and o[8] else 0}</p>

    <div class="total">Total Final Bs: {total_bs_final}</div>

    <a href="/enviar_cocina/{orden_id}" class="btn-accion cocina">
        Enviar a cocina
    </a>

    <a href="/cobrar/{orden_id}" class="btn-accion cobrar">
        Cobrar
    </a>
    
    html += f"""
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

        # CERRAR ORDEN
            cursor.execute("""
            UPDATE ordenes 
            SET estado='cerrada', descuento=?
            WHERE id=?
            """, (descuento, orden_id))
        conn.commit()
        conn.close()

        return redirect("/")

    conn.close()

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
 
# ---------------- TASA ----------------

@app.route("/tasa", methods=["GET", "POST"])
def cambiar_tasa():
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    if request.method == "POST":
        nueva = float(request.form["tasa"])
        cursor.execute("UPDATE tasa SET valor=?", (nueva,))
        conn.commit()

    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    tasa = cursor.fetchone()[0]

    conn.close()

    return f"""
    <h1>💱 Tasa actual: {tasa}</h1>
    <form method="post">
        Nueva tasa: <input name="tasa">
        <button>Guardar</button>
    </form>
    <a href="/">Volver</a>
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
    import pandas as pd
    from datetime import datetime

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    hoy = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT id, numero_orden, fecha_hora, tipo, cliente, descuento
        FROM ordenes
        WHERE fecha_hora LIKE ?
    """, (f"{hoy}%",))

    ordenes = cursor.fetchall()

    data = []

    for o in ordenes:
        orden_id = o[0]

        # 🔹 PRODUCTOS
        cursor.execute("""
            SELECT p.nombre, p.precio
            FROM orden_items oi
            JOIN productos p ON oi.producto_id = p.id
            WHERE oi.orden_id = ?
        """, (orden_id,))
        productos = cursor.fetchall()

        # 🔹 PAGOS
        cursor.execute("""
            SELECT metodo, monto_bs, monto_usd, referencia
            FROM pagos
            WHERE orden_id = ?
        """, (orden_id,))
        pagos = cursor.fetchall()

        # 🔹 TOTALES
        total_usd = sum([p[1] for p in productos])

        cursor.execute("SELECT valor FROM tasa LIMIT 1")
        tasa_row = cursor.fetchone()
        tasa = tasa_row[0] if tasa_row else 1

        total_bs = total_usd * tasa
        descuento = o[5] if o[5] else 0
        total_bs_final = max(total_bs - descuento, 0)

        # 🔥 LÓGICA PRINCIPAL
        max_filas = max(len(productos), len(pagos))

        for i in range(max_filas):

            producto_nombre = ""
            producto_precio = ""

            if i < len(productos):
                producto_nombre = productos[i][0]
                producto_precio = productos[i][1]

            metodo = ""
            monto_bs = 0
            monto_usd = 0
            referencia = ""

            if i < len(pagos):
                metodo = pagos[i][0]
                monto_bs = pagos[i][1] or 0
                monto_usd = pagos[i][2] or 0
                referencia = pagos[i][3] or ""

            data.append({
                "Orden": o[1],
                "Fecha": o[2],
                "Tipo": o[3],
                "Cliente": o[4],

                "Producto": producto_nombre,
                "Precio $": producto_precio,

                "Método": metodo,
                "Monto Bs": monto_bs,
                "Monto $": monto_usd,
                "Referencia": referencia,

                "Total Orden $": total_usd if i == 0 else "",
                "Total Orden Bs": total_bs if i == 0 else "",
                "Descuento Bs": descuento if i == 0 else "",
                "Total Final Bs": total_bs_final if i == 0 else ""
            })

    conn.close()

    df = pd.DataFrame(data)

    archivo = f"ventas_{hoy}.xlsx"
    df.to_excel(archivo, index=False)

    return f"Exportación lista: {archivo}"

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

# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    cargar_productos()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
