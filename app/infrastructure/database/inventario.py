"""
inventario.py (infraestructura)

Schema de inventario/compras/produccion/recetas/proveedores, mas el
repositorio SQL de esas tablas (recetas, movimientos_inventario,
productos_base, proveedores, compras, producciones y el stock de
inventario). Las rutas de presentacion (`/recetas`, `/compras`,
`/proveedores`, `/productos_base`, `/produccion`) en web_app.py llaman
estas funciones en vez de tener SQL inline.

Las escrituras operativas (descontar_inventario_por_orden,
registrar_movimiento_inventario) siguen en web_app.py por ahora:
dependen de `usuario_activo()`/`session` (quien esta operando) ademas de
`ahora_venezuela` -- moverlas requeriria enhebrar esos dos valores a
traves de app/application/payments/checkout.py::ejecutar_cobro (que ya
las recibe inyectadas desde la ruta) sin beneficio real todavia; queda
como deuda documentada NO bloqueante (mision: helper cross-cutting sin
centralizar) hasta que exista un modulo central para
usuario_activo/ahora_venezuela.

`get_connection`/`pk_autoincrement_sql` se reciben inyectados (siguen
en web_app.py hoy) para no crear un import circular. El resto de
funciones reciben un `cursor` ya abierto -- el llamador (web_app.py)
sigue siendo dueno del ciclo de vida de la conexion (commit/close).
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


def listar_recetas(cursor):
    cursor.execute(
        """
        SELECT id, producto_menu, insumo, cantidad, unidad
        FROM recetas
        ORDER BY producto_menu ASC, insumo ASC, id ASC
        """
    )
    return cursor.fetchall()


def crear_receta(cursor, producto_menu, insumo, cantidad, unidad):
    cursor.execute(
        """
        INSERT INTO recetas (producto_menu, insumo, cantidad, unidad)
        VALUES (?, ?, ?, ?)
        """,
        (producto_menu, insumo, cantidad, unidad),
    )


def eliminar_receta_por_id(cursor, receta_id):
    cursor.execute("DELETE FROM recetas WHERE id=?", (receta_id,))


def listar_insumos_inventario(cursor):
    cursor.execute(
        """
        SELECT nombre, unidad
        FROM inventario
        ORDER BY nombre ASC
        """
    )
    return cursor.fetchall()


def listar_movimientos_inventario_recientes(cursor, limite=300):
    cursor.execute(
        """
        SELECT fecha, producto, tipo, cantidad, stock_anterior, stock_nuevo,
               referencia, usuario, observacion
        FROM movimientos_inventario
        ORDER BY id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return cursor.fetchall()


def listar_productos_base(cursor):
    cursor.execute(
        """
        SELECT id, nombre, unidad
        FROM productos_base
        ORDER BY nombre ASC
        """
    )
    return cursor.fetchall()


def obtener_producto_base_por_id(cursor, producto_base_id):
    cursor.execute(
        """
        SELECT nombre, unidad
        FROM productos_base
        WHERE id=?
        """,
        (producto_base_id,),
    )
    return cursor.fetchone()


def producto_base_existe_por_nombre(cursor, nombre):
    cursor.execute(
        "SELECT id FROM productos_base WHERE lower(nombre)=lower(?)",
        (nombre,),
    )
    return cursor.fetchone() is not None


def crear_producto_base(cursor, nombre, unidad):
    cursor.execute(
        """
        INSERT INTO productos_base (nombre, unidad)
        VALUES (?, ?)
        """,
        (nombre, unidad),
    )


def listar_proveedores(cursor):
    cursor.execute(
        """
        SELECT id, nombre
        FROM proveedores
        ORDER BY nombre ASC
        """
    )
    return cursor.fetchall()


def obtener_proveedor_por_id(cursor, proveedor_id):
    cursor.execute(
        """
        SELECT nombre
        FROM proveedores
        WHERE id=?
        """,
        (proveedor_id,),
    )
    return cursor.fetchone()


def proveedor_existe_por_nombre(cursor, nombre):
    cursor.execute(
        "SELECT id FROM proveedores WHERE lower(nombre)=lower(?)",
        (nombre,),
    )
    return cursor.fetchone() is not None


def crear_proveedor(cursor, nombre):
    cursor.execute(
        """
        INSERT INTO proveedores (nombre)
        VALUES (?)
        """,
        (nombre,),
    )


def crear_compra(cursor, producto, cantidad, precio_total, proveedor, fecha, usuario_id):
    cursor.execute(
        """
        INSERT INTO compras (producto, cantidad, precio_total, proveedor, fecha, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (producto, cantidad, precio_total, proveedor, fecha, usuario_id),
    )


def listar_compras_recientes(cursor, limite=20):
    cursor.execute(
        """
        SELECT producto, cantidad, precio_total, proveedor, fecha
        FROM compras
        ORDER BY id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return cursor.fetchall()


def listar_inventario_para_produccion(cursor):
    cursor.execute(
        """
        SELECT id, nombre, unidad, stock_actual, costo_promedio
        FROM inventario
        ORDER BY nombre ASC
        """
    )
    return cursor.fetchall()


def obtener_item_inventario_por_id(cursor, inventario_id):
    cursor.execute(
        """
        SELECT id, nombre, stock_actual, unidad, costo_promedio
        FROM inventario
        WHERE id=?
        LIMIT 1
        """,
        (inventario_id,),
    )
    return cursor.fetchone()


def actualizar_stock_inventario(cursor, inventario_id, nuevo_stock):
    cursor.execute(
        """
        UPDATE inventario
        SET stock_actual=?
        WHERE id=?
        """,
        (nuevo_stock, inventario_id),
    )


def crear_produccion(
    cursor,
    producto_origen,
    cantidad_origen,
    producto_resultado,
    cantidad_resultado,
    costo_total,
    fecha,
    usuario_id,
    merma,
    porcentaje_merma,
    costo_unitario_resultado,
    insumos_extra,
    costo_insumos_extra,
    porciones_detalle,
):
    cursor.execute(
        """
        INSERT INTO producciones (
            producto_origen, cantidad_origen, producto_resultado,
            cantidad_resultado, costo_total, fecha, usuario_id,
            merma, porcentaje_merma, costo_unitario_resultado,
            insumos_extra, costo_insumos_extra, porciones_detalle
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            producto_origen,
            cantidad_origen,
            producto_resultado,
            cantidad_resultado,
            costo_total,
            fecha,
            usuario_id,
            merma,
            porcentaje_merma,
            costo_unitario_resultado,
            insumos_extra,
            costo_insumos_extra,
            porciones_detalle,
        ),
    )


def listar_producciones_recientes(cursor, limite=20):
    cursor.execute(
        """
        SELECT producto_origen, cantidad_origen, producto_resultado, cantidad_resultado,
               costo_total, fecha, COALESCE(merma, 0), COALESCE(porcentaje_merma, 0),
               COALESCE(costo_unitario_resultado, 0), COALESCE(insumos_extra, ''),
               COALESCE(costo_insumos_extra, 0), COALESCE(porciones_detalle, '')
        FROM producciones
        ORDER BY id DESC
        LIMIT ?
        """,
        (limite,),
    )
    return cursor.fetchall()


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
