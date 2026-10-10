"""
modifiers.py (infraestructura)

Repositorio SQL puro para el sistema general de grupos de
modificadores/opciones (caso inicial: Jugo Natural -> "Sabor" +
"Azucar"; tambien sirve para refrescos u otro producto nuevo sin tocar
codigo). Tres tablas:

- `grupos_modificadores`: un grupo (ej. "Sabor") con sus reglas de
  seleccion (obligatorio, seleccion_multiple, minimo, maximo).
- `opciones_modificador`: las opciones de un grupo (ej. "Fresa"),
  cada una con su propio activa/disponible/precio_adicional.
- `producto_grupos_modificadores`: asociacion muchos-a-muchos entre
  productos y grupos (un grupo puede reutilizarse en varios
  productos, ej. el mismo grupo "Sabor de refresco" en varias bebidas).

Nunca se borra fisicamente un grupo/opcion ya usado en una orden
historica (la seleccion queda serializada como snapshot JSON dentro de
`orden_items.indicacion` via app.domain.sales.item_descriptions --
desactivar un grupo/opcion despues no altera ninguna orden pasada).
Las operaciones de "eliminar" expuestas aqui son solo toggles de
activo/disponible o, para la asociacion producto<->grupo (que no tiene
historial propio, es pura configuracion), un DELETE real de la fila de
asociacion.

`get_connection`/`pk_autoincrement_sql`/`obtener_ultimo_id` se reciben
inyectados en el bootstrap (mismo patron que cxc.py/delivery.py) para
no crear un import circular con web_app.py.
"""

from app.domain.sales.modifiers import GrupoModificador, OpcionModificador


def crear_tablas_modificadores(get_connection, pk_autoincrement_sql):
    """Idempotente, no destructiva. Se llama desde web_app.init_db()."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS grupos_modificadores (
            id {pk_autoincrement_sql()},
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            obligatorio INTEGER DEFAULT 1,
            seleccion_multiple INTEGER DEFAULT 0,
            minimo INTEGER DEFAULT 1,
            maximo INTEGER DEFAULT 1,
            orden INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS opciones_modificador (
            id {pk_autoincrement_sql()},
            grupo_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            activa INTEGER DEFAULT 1,
            disponible INTEGER DEFAULT 1,
            precio_adicional REAL DEFAULT 0,
            orden INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS producto_grupos_modificadores (
            id {pk_autoincrement_sql()},
            producto_id INTEGER NOT NULL,
            grupo_id INTEGER NOT NULL,
            orden INTEGER DEFAULT 0,
            UNIQUE (producto_id, grupo_id)
        )
        """
    )

    conn.commit()
    conn.close()


# ---- administracion (Menu) --------------------------------------------


def crear_grupo_modificador(
    cursor,
    obtener_ultimo_id,
    *,
    nombre,
    obligatorio=True,
    seleccion_multiple=False,
    minimo=1,
    maximo=1,
    orden=0,
):
    cursor.execute(
        """
        INSERT INTO grupos_modificadores
            (nombre, activo, obligatorio, seleccion_multiple, minimo, maximo, orden)
        VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (nombre, int(bool(obligatorio)), int(bool(seleccion_multiple)), minimo, maximo, orden),
    )
    return obtener_ultimo_id(cursor, "grupos_modificadores")


def actualizar_grupo_modificador(
    cursor, grupo_id, *, nombre, obligatorio, seleccion_multiple, minimo, maximo, orden
):
    cursor.execute(
        """
        UPDATE grupos_modificadores
        SET nombre=?, obligatorio=?, seleccion_multiple=?, minimo=?, maximo=?, orden=?
        WHERE id=?
        """,
        (
            nombre,
            int(bool(obligatorio)),
            int(bool(seleccion_multiple)),
            minimo,
            maximo,
            orden,
            grupo_id,
        ),
    )


def alternar_activo_grupo_modificador(cursor, grupo_id, activo):
    cursor.execute(
        "UPDATE grupos_modificadores SET activo=? WHERE id=?", (int(bool(activo)), grupo_id)
    )


def crear_opcion_modificador(
    cursor, obtener_ultimo_id, *, grupo_id, nombre, precio_adicional=0.0, orden=0
):
    cursor.execute(
        """
        INSERT INTO opciones_modificador (grupo_id, nombre, activa, disponible, precio_adicional, orden)
        VALUES (?, ?, 1, 1, ?, ?)
        """,
        (grupo_id, nombre, precio_adicional, orden),
    )
    return obtener_ultimo_id(cursor, "opciones_modificador")


def actualizar_opcion_modificador(cursor, opcion_id, *, nombre, precio_adicional, orden):
    cursor.execute(
        "UPDATE opciones_modificador SET nombre=?, precio_adicional=?, orden=? WHERE id=?",
        (nombre, precio_adicional, orden, opcion_id),
    )


def alternar_activa_opcion_modificador(cursor, opcion_id, activa):
    cursor.execute(
        "UPDATE opciones_modificador SET activa=? WHERE id=?", (int(bool(activa)), opcion_id)
    )


def alternar_disponible_opcion_modificador(cursor, opcion_id, disponible):
    cursor.execute(
        "UPDATE opciones_modificador SET disponible=? WHERE id=?",
        (int(bool(disponible)), opcion_id),
    )


def asociar_grupo_a_producto(cursor, producto_id, grupo_id, orden=0):
    cursor.execute(
        "SELECT id FROM producto_grupos_modificadores WHERE producto_id=? AND grupo_id=?",
        (producto_id, grupo_id),
    )
    if cursor.fetchone():
        return
    cursor.execute(
        "INSERT INTO producto_grupos_modificadores (producto_id, grupo_id, orden) VALUES (?, ?, ?)",
        (producto_id, grupo_id, orden),
    )


def desasociar_grupo_de_producto(cursor, producto_id, grupo_id):
    cursor.execute(
        "DELETE FROM producto_grupos_modificadores WHERE producto_id=? AND grupo_id=?",
        (producto_id, grupo_id),
    )


def listar_grupos_modificadores_admin(cursor):
    """Todos los grupos (activos e inactivos), para la pantalla de
    administracion -- a diferencia de listar_grupos_de_producto, que
    solo trae los activos para la toma de ordenes."""
    cursor.execute(
        """
        SELECT id, nombre, activo, obligatorio, seleccion_multiple, minimo, maximo, orden
        FROM grupos_modificadores
        ORDER BY orden, id
        """
    )
    return cursor.fetchall()


def listar_opciones_de_grupo_admin(cursor, grupo_id):
    cursor.execute(
        """
        SELECT id, nombre, activa, disponible, precio_adicional, orden
        FROM opciones_modificador
        WHERE grupo_id=?
        ORDER BY orden, id
        """,
        (grupo_id,),
    )
    return cursor.fetchall()


def listar_grupos_de_producto_admin(cursor, producto_id):
    """Grupos ya asociados a un producto (cualquier estado activo),
    para la pantalla de asociacion producto<->grupo."""
    cursor.execute(
        """
        SELECT g.id, g.nombre, g.activo
        FROM producto_grupos_modificadores pg
        JOIN grupos_modificadores g ON g.id = pg.grupo_id
        WHERE pg.producto_id=?
        ORDER BY pg.orden, g.id
        """,
        (producto_id,),
    )
    return cursor.fetchall()


# ---- toma de ordenes (dominio) -----------------------------------------


def _armar_grupos_dominio(filas_grupo, filas_opcion_por_grupo):
    grupos = []
    for grupo_id, nombre, activo, obligatorio, seleccion_multiple, minimo, maximo, orden in filas_grupo:
        opciones = tuple(
            OpcionModificador(
                id=o_id,
                nombre=o_nombre,
                activa=bool(o_activa),
                disponible=bool(o_disponible),
                precio_adicional=o_precio or 0.0,
                orden=o_orden,
            )
            for o_id, o_nombre, o_activa, o_disponible, o_precio, o_orden in filas_opcion_por_grupo.get(
                grupo_id, []
            )
        )
        grupos.append(
            GrupoModificador(
                id=grupo_id,
                nombre=nombre,
                activo=bool(activo),
                obligatorio=bool(obligatorio),
                seleccion_multiple=bool(seleccion_multiple),
                minimo=minimo,
                maximo=maximo,
                orden=orden,
                opciones=opciones,
            )
        )
    return grupos


def listar_grupos_de_producto(cursor, producto_id):
    """Grupos ACTIVOS asociados a un producto, con sus opciones ACTIVAS
    (independientemente de si estan disponibles/agotadas -- eso lo
    decide validar_seleccion_modificadores, no esta funcion), listos
    para construir GrupoModificador de dominio. Usado tanto para
    renderizar el selector al tomar la orden como para validar la
    seleccion recibida."""
    cursor.execute(
        """
        SELECT g.id, g.nombre, g.activo, g.obligatorio, g.seleccion_multiple, g.minimo, g.maximo, pg.orden
        FROM producto_grupos_modificadores pg
        JOIN grupos_modificadores g ON g.id = pg.grupo_id
        WHERE pg.producto_id=? AND g.activo=1
        ORDER BY pg.orden, g.id
        """,
        (producto_id,),
    )
    filas_grupo = cursor.fetchall()
    if not filas_grupo:
        return []

    grupo_ids = [fila[0] for fila in filas_grupo]
    placeholders = ",".join("?" * len(grupo_ids))
    cursor.execute(
        f"""
        SELECT grupo_id, id, nombre, activa, disponible, precio_adicional, orden
        FROM opciones_modificador
        WHERE grupo_id IN ({placeholders}) AND activa=1
        ORDER BY orden, id
        """,
        grupo_ids,
    )
    opciones_por_grupo = {}
    for grupo_id, o_id, o_nombre, o_activa, o_disponible, o_precio, o_orden in cursor.fetchall():
        opciones_por_grupo.setdefault(grupo_id, []).append(
            (o_id, o_nombre, o_activa, o_disponible, o_precio, o_orden)
        )

    return _armar_grupos_dominio(filas_grupo, opciones_por_grupo)


def listar_grupos_por_producto_ids(cursor, producto_ids):
    """Igual que listar_grupos_de_producto pero para varios productos
    a la vez (2 queries en total, sin N+1) -- usado al renderizar el
    catalogo completo de /orden/<id>. Devuelve {producto_id: [GrupoModificador, ...]},
    omitiendo productos sin ningun grupo activo asociado."""
    producto_ids = list(producto_ids)
    if not producto_ids:
        return {}

    placeholders = ",".join("?" * len(producto_ids))
    cursor.execute(
        f"""
        SELECT pg.producto_id, g.id, g.nombre, g.activo, g.obligatorio, g.seleccion_multiple, g.minimo, g.maximo, pg.orden
        FROM producto_grupos_modificadores pg
        JOIN grupos_modificadores g ON g.id = pg.grupo_id
        WHERE pg.producto_id IN ({placeholders}) AND g.activo=1
        ORDER BY pg.orden, g.id
        """,
        producto_ids,
    )
    filas = cursor.fetchall()
    if not filas:
        return {}

    grupo_ids = sorted({fila[1] for fila in filas})
    placeholders_grupos = ",".join("?" * len(grupo_ids))
    cursor.execute(
        f"""
        SELECT grupo_id, id, nombre, activa, disponible, precio_adicional, orden
        FROM opciones_modificador
        WHERE grupo_id IN ({placeholders_grupos}) AND activa=1
        ORDER BY orden, id
        """,
        grupo_ids,
    )
    opciones_por_grupo = {}
    for grupo_id, o_id, o_nombre, o_activa, o_disponible, o_precio, o_orden in cursor.fetchall():
        opciones_por_grupo.setdefault(grupo_id, []).append(
            (o_id, o_nombre, o_activa, o_disponible, o_precio, o_orden)
        )

    filas_por_producto = {}
    for producto_id, *resto_grupo in filas:
        filas_por_producto.setdefault(producto_id, []).append(tuple(resto_grupo))

    return {
        producto_id: _armar_grupos_dominio(filas_grupo, opciones_por_grupo)
        for producto_id, filas_grupo in filas_por_producto.items()
    }
