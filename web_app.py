from flask import Flask, request, redirect
import sqlite3
import datetime
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

    # ---------------- CATEGORIAS ----------------
 # 🔥 insertar categorias iniciales
cursor.execute("SELECT COUNT(*) FROM categorias")
if cursor.fetchone()[0] == 0:
    categorias = [
        ("Arroces",),
        ("Bebida",),
        ("Delivery",),
        ("Extras",)
    ]

    cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", categorias)
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
        ("Cerdo-Pollo Personal", 6.5, "Arroces"),
        ("Cerdo-Pollo Mediano", 9.5, "Arroces"),
        ("Cerdo-Pollo Familiar", 12.5, "Arroces"),
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
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ordenes (numero_orden, fecha_hora, tipo, referencia, cliente, estado)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (numero, fecha, tipo, referencia, cliente, "abierta"))

    conn.commit()
    conn.close()

    return redirect("/")

# ---------------- ORDEN ----------------

@app.route("/orden/<int:orden_id>")
def orden(orden_id):
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    # 🔹 Datos de la orden
    cursor.execute("""
    SELECT numero_orden, tipo, referencia, cliente, estado, fecha_hora 
    FROM ordenes WHERE id=?
    """, (orden_id,))
    o = cursor.fetchone()
    if not o:
        conn.close()
        return "Orden no encontrada"

    # 🔹 Items de la orden
    cursor.execute("SELECT producto, precio FROM orden_items WHERE orden_id=?", (orden_id,))
    items = cursor.fetchall()

    # 🔹 Productos con categoría
    cursor.execute("""
    SELECT p.id, p.nombre, p.precio, c.nombre
    FROM productos p
    LEFT JOIN categorias c ON p.categoria_id = c.id
    ORDER BY c.nombre
    """)
    productos = cursor.fetchall()

    # 🔥 Obtener tasa (seguro)
    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    row = cursor.fetchone()
    tasa = row[0] if row else 1

    conn.close()

    # 🔹 Totales
    total_usd = sum(i[1] for i in items)
    total_bs = total_usd * tasa

    html = f"""
    <html>
    <head>
    <style>
        body {{
            font-family: Arial;
            display:flex;
            margin:0;
        }}

        .productos {{
            width:65%;
            padding:10px;
            background:#f5f5f5;
        }}

        .panel {{
            width:35%;
            padding:20px;
            background:white;
            border-left:3px solid #ccc;
        }}

        .btn {{
            width:48%;
            padding:20px;
            margin:5px 1%;
            font-size:18px;
            background:#27ae60;
            color:white;
            border:none;
            border-radius:10px;
        }}

        .categoria {{
            background:#333;
            color:white;
            padding:8px;
            margin-top:10px;
            border-radius:5px;
        }}

        .acciones a {{
            display:block;
            margin:10px 0;
            padding:10px;
            background:#3498db;
            color:white;
            text-align:center;
            text-decoration:none;
            border-radius:5px;
        }}

        /* 🔥 PANEL DERECHO */
        .panel h2 {{
            margin-top:0;
        }}

        .total {{
            font-size:24px;
            font-weight:bold;
            margin:10px 0;
        }}

        .btn-accion {{
            display:block;
            width:100%;
            padding:15px;
            margin:10px 0;
            text-align:center;
            text-decoration:none;
            color:white;
            border-radius:8px;
            font-size:18px;
        }}

        .cocina {{ background:#e67e22; }}
        .cobrar {{ background:#27ae60; }}
        .volver {{ background:#7f8c8d; }}

        .lista-items {{
            background:#f9f9f9;
            padding:10px;
            border-radius:8px;
            margin:10px 0;
        }}
    </style>
    </head>

    <body>

    <div class="productos">
        <h2>Agregar productos</h2>
    """

    # 🔥 Agrupar por categorías
    categoria_actual = None

    for p in productos:
        categoria = p[3] if p[3] else "Sin categoría"

        if categoria != categoria_actual:
            categoria_actual = categoria
            html += f"<div class='categoria'>🍽 {categoria}</div>"

        html += f"""
        <a href="/agregar/{orden_id}/{p[0]}">
            <button class="btn">{p[1]} - ${p[2]}</button>
        </a>
        """

    html += "</div>"

    # 🔹 Panel derecho
    html += f"""
    <div class="panel">

        <h2> Orden #{o[0]}</h2>
        <p><b>{o[1]}</b> - {o[2]}</p>
        <p>Cliente: {o[3] if o[3] else '-'}</p>
        <p>Hora: {o[5]}</p>
        <p>Estado: {o[4]}</p>

        <div class="lista-items">
            <h3> Productos</h3>
"""

    for i in items:
        html += f"<p>• {i[0]} - ${i[1]}</p>"

    html += f"""
        </div>

        <div class="total"> USD: ${total_usd}</div>
        <div class="total"> Bs: {total_bs}</div>

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

    if request.method == "POST":
        metodo1 = request.form["metodo1"]
        monto1 = float(request.form["monto1"] or 0)
        ref1 = request.form.get("ref1", "")

        metodo2 = request.form.get("metodo2")
        monto2 = float(request.form.get("monto2") or 0)
        ref2 = request.form.get("ref2", "")

        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
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
        if total_pagado_usd < total_usd:
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
        cursor.execute("UPDATE ordenes SET estado='cerrada' WHERE id=?", (orden_id,))
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
        <option value="usd">$</option>
        <option value="bs_efectivo">Bs efectivo</option>
        <option value="bs_pago_movil">Pago móvil</option>
    </select>

    <input name="monto1" placeholder="Monto"><br>
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
    conn = sqlite3.connect("china_house.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        o.fecha_hora,
        o.numero_orden,
        i.producto,
        i.precio,
        p.metodo,
        p.monto,
        p.referencia
    FROM ordenes o
    LEFT JOIN orden_items i ON o.id = i.orden_id
    LEFT JOIN pagos p ON o.id = p.orden_id
    ORDER BY o.fecha_hora DESC
    """)

    datos = cursor.fetchall()
    conn.close()

    # encabezados
    csv = "fecha;orden;producto;precio;metodo;monto;referencia\n"

    for d in datos:
        fecha = d[0] or ""
        orden = d[1] or ""
        producto = d[2] or ""
        precio = d[3] or ""
        metodo = d[4] or ""
        monto = d[5] or ""
        referencia = d[6] or ""

        csv += f"{fecha};{orden};{producto};{precio};{metodo};{monto};{referencia}\n"

    return csv, 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=ventas_detalladas.csv"
    }

# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    cargar_productos()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
