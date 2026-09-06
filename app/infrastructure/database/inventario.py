"""
inventario.py (infraestructura)

Schema de inventario/compras/produccion/recetas. Las escrituras
operativas (descontar_inventario_por_orden, registrar_movimiento_inventario)
siguen en web_app.py por ahora: dependen de `usuario_activo()`/`session`
(quien esta operando) ademas de `ahora_venezuela` -- moverlas requeriria
enhebrar esos dos valores a traves de
app/application/payments/checkout.py::ejecutar_cobro (que ya las recibe
inyectadas desde la ruta) sin beneficio real todavia; queda como deuda
documentada NO bloqueante (mision: helper cross-cutting sin
centralizar) hasta que exista un modulo central para
usuario_activo/ahora_venezuela.

`get_connection`/`pk_autoincrement_sql` se reciben inyectados (siguen
en web_app.py hoy) para no crear un import circular.
"""


def crear_tablas_inventario(get_connection, pk_autoincrement_sql):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS inventario (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            stock_actual REAL,
            unidad TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS compras (
            id {pk_autoincrement_sql()},
            producto TEXT,
            cantidad REAL,
            precio_total REAL,
            proveedor TEXT,
            fecha TEXT,
            usuario_id INTEGER
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS producciones (
            id {pk_autoincrement_sql()},
            producto_origen TEXT,
            cantidad_origen REAL,
            producto_resultado TEXT,
            cantidad_resultado REAL,
            costo_total REAL,
            fecha TEXT,
            usuario_id INTEGER
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS proveedores (
            id {pk_autoincrement_sql()},
            nombre TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS productos_base (
            id {pk_autoincrement_sql()},
            nombre TEXT,
            unidad TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS recetas (
            id {pk_autoincrement_sql()},
            producto_menu TEXT,
            insumo TEXT,
            cantidad REAL,
            unidad TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS movimientos_inventario (
            id {pk_autoincrement_sql()},
            producto TEXT,
            tipo TEXT,
            cantidad REAL,
            stock_anterior REAL,
            stock_nuevo REAL,
            costo_promedio REAL,
            referencia TEXT,
            usuario TEXT,
            fecha TEXT,
            observacion TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def obtener_costo_promedio_producto(cursor, producto):
    cursor.execute(
        """
        SELECT costo_promedio
        FROM inventario
        WHERE lower(nombre) = lower(?)
        LIMIT 1
        """,
        (producto,),
    )
    row = cursor.fetchone()
    if row and row[0]:
        return float(row[0])

    cursor.execute(
        """
        SELECT COALESCE(SUM(precio_total), 0), COALESCE(SUM(cantidad), 0)
        FROM compras
        WHERE lower(producto) = lower(?)
        """,
        (producto,),
    )
    total, cantidad = cursor.fetchone()
    if cantidad and cantidad > 0:
        return float(total or 0) / float(cantidad)

    cursor.execute(
        """
        SELECT COALESCE(SUM(costo_total), 0), COALESCE(SUM(cantidad_resultado), 0)
        FROM producciones
        WHERE lower(producto_resultado) = lower(?)
        """,
        (producto,),
    )
    total, cantidad = cursor.fetchone()
    if cantidad and cantidad > 0:
        return float(total or 0) / float(cantidad)

    return 0.0


def crear_datos_base_inventario(get_connection):
    conn = get_connection()
    cursor = conn.cursor()

    productos_base = [
        ("Pollo", "kg"),
        ("Cerdo", "kg"),
        ("Camaron", "kg"),
        ("Arroz", "kg"),
        ("Lumpias", "unidad"),
        ("Salsa", "lt"),
        ("Refresco", "unidad"),
    ]

    for nombre, unidad in productos_base:
        cursor.execute(
            "SELECT id FROM productos_base WHERE lower(nombre)=lower(?)",
            (nombre,),
        )
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO productos_base (nombre, unidad)
                VALUES (?, ?)
                """,
                (nombre, unidad),
            )

    conn.commit()
    conn.close()
