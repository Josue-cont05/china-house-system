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
    
    try:
        cursor.execute("ALTER TABLE productos ADD COLUMN categoria_id INTEGER")
    except:
    pass

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
    CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT
    )
    """)
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        categorias = [
            ("Arroces",),
            ("Especiales",),
            ("Bebidas",)
        ]

    cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", categorias)


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
    cursor.execute("""
    
    CREATE TABLE IF NOT EXISTS orden_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orden_id INTEGER,
        producto TEXT,
        precio REAL
    )
    """)

    # 🔥 NUEVA TABLA TASA
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        valor REAL
    )
    """)

    # 🔥 ASEGURAR QUE EXISTA UNA TASA
    cursor.execute("SELECT COUNT(*) FROM tasa")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO tasa (valor) VALUES (36)")

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

    cursor.execute("""
    ALTER TABLE productos ADD COLUMN categoria_id INTEGER
    """)
    
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
    nombre = request.form["nombre"]
    precio = float(request.form["precio"])
    categoria_id = int(request.form["categoria_id"])

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

    if request.method == "POST":
        nombre = request.form["nombre"]
        precio = float(request.form["precio"])

        cursor.execute("""
        UPDATE productos SET nombre=?, precio=?
        WHERE id=?
        """, (nombre, precio, id))

        conn.commit()
        conn.close()

        return redirect("/menu")

    cursor.execute("SELECT nombre, precio FROM productos WHERE id=?", (id,))
    p = cursor.fetchone()

    conn.close()

    return f"""
    <h1>Editar producto</h1>

    <form method="post">
        Nombre: <input name="nombre" value="{p[0]}"><br><br>
        Precio: <input name="precio" value="{p[1]}"><br><br>
        <button>Guardar</button>
    </form>

    <a href="/menu">Volver</a>
    """

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
    VALUES (?, ?, ?, ?, ?, ?)
    """, (numero, fecha_hora, tipo, referencia, cliente, "abierta"))

    conn.commit()
    orden_id = cursor.lastrowid
    conn.close()

    return redirect(f"/orden/{orden_id}")

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

    # 🔹 HTML
    html = f"""
    <html>
    <head>
    <style>
        body {{ font-family: Arial; display:flex; }}
        .productos {{ width:60%; }}
        .panel {{ width:40%; padding:20px; border-left:2px solid #ccc; }}
        .btn {{ width:100%; padding:20px; margin:5px; font-size:18px; background:#27ae60; color:white; border:none; }}
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
            html += f"<h3>🍽 {categoria}</h3>"

        html += f"""
        <a href="/agregar/{orden_id}/{p[0]}">
            <button class="btn">{p[1]} - ${p[2]}</button>
        </a>
        """

    html += "</div>"

    # 🔹 Panel derecho
    html += f"""
    <div class="panel">
        <h2>Orden #{o[0]}</h2>
        <p>{o[1]} - {o[2]}</p>
        <p>Cliente: {o[3] if o[3] else '-'}</p>
        <p>Hora: {o[5]}</p>
        <p>Estado: {o[4]}</p>

        <hr>

        <h3>Productos</h3>
    """

    for i in items:
        html += f"{i[0]} - ${i[1]}<br>"

    html += f"""
    <h2>Total USD: ${total_usd}</h2>
    <h2>Total Bs: Bs {total_bs}</h2>

    <a href="/enviar_cocina/{orden_id}">🔥 Enviar a cocina</a><br>
    <a href="/cobrar/{orden_id}">💰 Cobrar</a><br>
    <a href="/">⬅ Volver</a>
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

    if request.method == "POST":
        metodo = request.form["metodo"]
        monto = float(request.form["monto"])
        referencia = request.form.get("referencia", "")

        # VALIDACIONES
        if metodo == "usd":
            if monto < total_usd:
                return "Pago insuficiente en USD"

        elif metodo == "bs_efectivo":
            if monto < total_bs:
                return "Pago insuficiente en Bs"

        elif metodo == "bs_pago_movil":
            if monto < total_bs:
                return "Pago móvil insuficiente"
            if referencia.strip() == "":
                return "Debes colocar la referencia del pago móvil"
                
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO pagos (orden_id, metodo, monto, referencia, fecha)
        VALUES (?, ?, ?, ?, ?)
        """, (orden_id, metodo, monto, referencia, fecha))
        
        # Cerrar orden
        cursor.execute("UPDATE ordenes SET estado='cerrada' WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()

        return redirect("/")

    conn.close()

    return f"""
    <h1>💰 Cobro Orden #{orden_id}</h1>

    <h2>Total USD: ${total_usd}</h2>
    <h2>Total Bs: Bs {total_bs}</h2>

    <form method="post">
        <label>Método de pago:</label><br>
        <select name="metodo">
            <option value="usd">$ Efectivo</option>
            <option value="bs_efectivo">Bs Efectivo</option>
            <option value="bs_pago_movil">Pago Móvil</option>
        </select><br><br>

        <label>Monto recibido:</label><br>
        <input name="monto"><br><br>

        <label>Referencia (solo pago móvil):</label><br>
        <input name="referencia"><br><br>

        <button type="submit">Confirmar pago</button>
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

    <h1>🍳 COCINA</h1>

    <div class="container">
        <div class="col">
            <h2>🟡 ESTACIÓN ARROZ</h2>
    """

    arroz_html = ""
    caliente_html = ""

    total_ordenes = len(ordenes)

    for o in ordenes:
        fecha_orden = datetime.datetime.strptime(o[4], "%Y-%m-%d %H:%M:%S")
        minutos = (ahora - fecha_orden).seconds / 60

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
                <button class="btn">✅ LISTO</button>
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
            <h2>🔵 ESTACIÓN CALIENTE</h2>
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
# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    cargar_productos()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
