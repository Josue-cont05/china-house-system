"""
delivery.py (infraestructura)

Repositorio SQL puro de Delivery/repartidores (`repartidores`,
`delivery_movimientos`, y las columnas de delivery en `ordenes`).
Deliberadamente NO valida reglas de negocio de mas alto nivel que las
inherentes al propio dato (ver `app/domain/delivery/rules.py` para las
reglas puras, y `app/application/delivery/*` para los casos de uso que
coordinan esto con notifications).

`get_connection`/`pk_autoincrement_sql`/`asegurar_columna` y
`obtener_ultimo_id`/`ahora_venezuela` se reciben inyectados donde hacen
falta (mismo patron que cxc.py/payments.py) para no crear un import
circular con web_app.py, que es quien los define hoy.
"""

from app.domain.delivery.rules import normalizar_nombre_repartidor
from app.domain.sales.calculations import (
    _a_float as a_float,
    TOLERANCIA_COBRO,
    es_producto_delivery_legacy,
    normalizar_monto_delivery,
)
from app.infrastructure.database.cxc import orden_tiene_cxc


def crear_tablas_delivery(get_connection, pk_autoincrement_sql, asegurar_columna):
    """Idempotente, no destructiva. Se llama desde web_app.init_db()."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS repartidores (
            id {pk_autoincrement_sql()},
            nombre TEXT NOT NULL,
            telefono TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS delivery_movimientos (
            id {pk_autoincrement_sql()},
            orden_id INTEGER,
            repartidor_id INTEGER NOT NULL,
            tipo TEXT NOT NULL
                CHECK (tipo IN ('cargo', 'pago', 'ajuste', 'anulacion')),
            monto_usd REAL NOT NULL,
            fecha TEXT,
            usuario_id INTEGER,
            referencia TEXT,
            observacion TEXT,
            movimiento_revertido_id INTEGER
        )
        """
    )

    conn.commit()
    conn.close()

    asegurar_columna("ordenes", "venta_restaurante_usd", "REAL")
    asegurar_columna("ordenes", "delivery_usd", "REAL")
    asegurar_columna("ordenes", "total_cliente_usd", "REAL")
    asegurar_columna("ordenes", "total_cliente_bs", "REAL")
    asegurar_columna("ordenes", "delivery_repartidor_id", "INTEGER")


def listar_repartidores(cursor, solo_activos=False):
    where = "WHERE COALESCE(activo, 1)=1" if solo_activos else ""
    cursor.execute(
        f"""
        SELECT id, nombre, COALESCE(telefono, ''), COALESCE(notas, ''),
               COALESCE(activo, 1), fecha_creacion
        FROM repartidores
        {where}
        ORDER BY COALESCE(activo, 1) DESC, LOWER(nombre), id
        """
    )
    return cursor.fetchall()


def obtener_repartidor(cursor, repartidor_id):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(telefono, ''), COALESCE(notas, ''),
               COALESCE(activo, 1), fecha_creacion
        FROM repartidores
        WHERE id=?
        """,
        (repartidor_id,),
    )
    return cursor.fetchone()


def crear_repartidor(cursor, nombre, telefono, notas, activo, ahora_venezuela, obtener_ultimo_id):
    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO repartidores (nombre, telefono, notas, activo, fecha_creacion)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            normalizar_nombre_repartidor(nombre),
            (telefono or "").strip()[:80],
            (notas or "").strip()[:500],
            1 if int(a_float(activo, 1)) == 1 else 0,
            fecha,
        ),
    )
    return obtener_ultimo_id(cursor, "repartidores")


def orden_tiene_delivery_legacy(cursor, orden_id):
    cursor.execute(
        """
        SELECT oi.producto,
               (
                   SELECT c.nombre
                   FROM productos p
                   LEFT JOIN categorias c ON p.categoria_id = c.id
                   WHERE LOWER(p.nombre)=LOWER(oi.producto)
                   ORDER BY COALESCE(p.activo, 1) DESC, p.id
                   LIMIT 1
               ) AS categoria
        FROM orden_items oi
        WHERE oi.orden_id=?
        """,
        (orden_id,),
    )
    return any(es_producto_delivery_legacy(producto, categoria) for producto, categoria in cursor.fetchall())


def validar_orden_delivery_modificable(cursor, orden_id):
    cursor.execute(
        """
        SELECT estado, cierre_id
        FROM ordenes
        WHERE id=?
        """,
        (orden_id,),
    )
    orden_row = cursor.fetchone()
    if not orden_row:
        raise ValueError("Orden no encontrada")
    estado, cierre_id = orden_row
    if cierre_id is not None:
        raise ValueError("No puedes modificar delivery en una orden archivada en cierre de jornada.")
    if estado == "cerrada":
        raise ValueError("No puedes modificar delivery en una orden cerrada.")
    if orden_tiene_cxc(cursor, orden_id):
        raise ValueError("No puedes modificar delivery en una orden con cuenta por cobrar asociada.")
    return estado


def actualizar_delivery_orden(cursor, orden_id, monto_delivery, repartidor_id):
    validar_orden_delivery_modificable(cursor, orden_id)
    monto = normalizar_monto_delivery(monto_delivery)

    repartidor_id_final = None
    if monto > 0:
        if orden_tiene_delivery_legacy(cursor, orden_id):
            raise ValueError("Esta orden contiene un delivery agregado con el sistema anterior. No se puede agregar delivery explicito.")
        repartidor_id_texto = (str(repartidor_id or "")).strip()
        if repartidor_id_texto:
            repartidor_id_final = int(a_float(repartidor_id_texto))
            repartidor = obtener_repartidor(cursor, repartidor_id_final)
            if not repartidor or int(repartidor[4] or 0) != 1:
                raise ValueError("Debes seleccionar un repartidor activo para guardar delivery.")

    cursor.execute(
        """
        UPDATE ordenes
        SET delivery_usd=?, delivery_repartidor_id=?
        WHERE id=?
        """,
        (monto, repartidor_id_final, orden_id),
    )
    return {"delivery_usd": monto, "delivery_repartidor_id": repartidor_id_final}


def orden_tiene_movimientos_delivery(cursor, orden_id):
    cursor.execute("SELECT 1 FROM delivery_movimientos WHERE orden_id=? LIMIT 1", (orden_id,))
    return cursor.fetchone() is not None


def validar_recobro_delivery(cursor, orden_id):
    if orden_tiene_movimientos_delivery(cursor, orden_id):
        raise ValueError(
            "Esta orden tiene movimientos de delivery asociados y no puede recobrarse directamente. "
            "Debe utilizarse un proceso administrativo de reversion."
        )


def validar_repartidor_delivery_cobro(cursor, delivery_usd, repartidor_id):
    if a_float(delivery_usd) <= TOLERANCIA_COBRO:
        return None
    try:
        repartidor_id_int = int(a_float(repartidor_id))
    except Exception:
        repartidor_id_int = 0
    if repartidor_id_int <= 0:
        raise ValueError("Debes asignar un repartidor antes de cobrar esta orden.")
    repartidor = obtener_repartidor(cursor, repartidor_id_int)
    if not repartidor or int(repartidor[4] or 0) != 1:
        raise ValueError("Selecciona un repartidor activo para el delivery.")
    return repartidor_id_int


def insertar_cargo_delivery(cursor, orden_id, repartidor_id, monto_usd, fecha, usuario_id, obtener_ultimo_id):
    monto_usd = round(a_float(monto_usd), 2)
    if monto_usd <= TOLERANCIA_COBRO:
        return None
    if orden_tiene_movimientos_delivery(cursor, orden_id):
        raise ValueError("Esta orden ya tiene movimientos de delivery asociados.")
    cursor.execute(
        """
        INSERT INTO delivery_movimientos (
            orden_id, repartidor_id, tipo, monto_usd, fecha,
            usuario_id, referencia, observacion, movimiento_revertido_id
        )
        VALUES (?, ?, 'cargo', ?, ?, ?, ?, ?, NULL)
        """,
        (
            orden_id,
            repartidor_id,
            monto_usd,
            fecha,
            usuario_id,
            f"orden:{orden_id}",
            "Cargo delivery generado al cerrar la orden",
        ),
    )
    return obtener_ultimo_id(cursor, "delivery_movimientos")


def resumen_delivery_admin(cursor):
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo='cargo' THEN monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo='pago' THEN ABS(monto_usd) ELSE 0 END), 0),
            COALESCE(SUM(monto_usd), 0),
            COALESCE(SUM(CASE WHEN tipo='cargo' AND orden_id IS NOT NULL THEN 1 ELSE 0 END), 0)
        FROM delivery_movimientos
        """
    )
    generado, pagado, pendiente, servicios = cursor.fetchone()
    return {
        "generado": a_float(generado),
        "pagado": a_float(pagado),
        "pendiente": a_float(pendiente),
        "servicios": int(servicios or 0),
    }


def resumen_delivery_por_repartidor(cursor):
    cursor.execute(
        """
        SELECT
            r.id,
            r.nombre,
            COALESCE(r.activo, 1),
            COALESCE(SUM(CASE WHEN dm.tipo='cargo' AND dm.orden_id IS NOT NULL THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dm.tipo='cargo' THEN dm.monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dm.tipo='pago' THEN ABS(dm.monto_usd) ELSE 0 END), 0),
            COALESCE(SUM(dm.monto_usd), 0)
        FROM repartidores r
        LEFT JOIN delivery_movimientos dm ON dm.repartidor_id = r.id
        GROUP BY r.id, r.nombre, r.activo
        ORDER BY COALESCE(SUM(dm.monto_usd), 0) DESC, LOWER(r.nombre), r.id
        """
    )
    return cursor.fetchall()


def resumen_delivery_movimientos(cursor, inicio=None, fin=None, solo_ordenes_sin_cierre=False):
    where_periodo = []
    params_periodo = []
    if inicio:
        where_periodo.append("dm.fecha >= ?")
        params_periodo.append(inicio)
    if fin:
        where_periodo.append("dm.fecha <= ?")
        params_periodo.append(fin)
    where_sql = "WHERE " + " AND ".join(where_periodo) if where_periodo else ""
    condicion_cargo = "dm.tipo='cargo'"
    if solo_ordenes_sin_cierre:
        condicion_cargo += " AND dm.orden_id IS NOT NULL AND o.cierre_id IS NULL"

    cursor.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN {condicion_cargo} THEN dm.monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dm.tipo='pago' THEN ABS(dm.monto_usd) ELSE 0 END), 0)
        FROM delivery_movimientos dm
        LEFT JOIN ordenes o ON o.id = dm.orden_id
        {where_sql}
        """,
        params_periodo,
    )
    generado, pagado = cursor.fetchone()
    cursor.execute("SELECT COALESCE(SUM(monto_usd), 0) FROM delivery_movimientos")
    pendiente_actual = cursor.fetchone()[0]
    return {
        "generado": round(a_float(generado), 2),
        "pagado": round(a_float(pagado), 2),
        "pendiente_actual": round(a_float(pendiente_actual), 2),
    }


def detalle_delivery_repartidor(cursor, repartidor_id):
    repartidor = obtener_repartidor(cursor, repartidor_id)
    if not repartidor:
        return None

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo='cargo' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo='cargo' THEN monto_usd ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo='pago' THEN ABS(monto_usd) ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN tipo IN ('ajuste', 'anulacion') THEN monto_usd ELSE 0 END), 0),
            COALESCE(SUM(monto_usd), 0)
        FROM delivery_movimientos
        WHERE repartidor_id=?
        """,
        (repartidor_id,),
    )
    servicios, generado, pagado, ajustes_netos, pendiente = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            dm.fecha,
            dm.tipo,
            dm.orden_id,
            o.id,
            o.numero_orden,
            dm.monto_usd,
            dm.referencia,
            u.nombre,
            dm.observacion
        FROM delivery_movimientos dm
        LEFT JOIN ordenes o ON o.id = dm.orden_id
        LEFT JOIN usuarios u ON u.id = dm.usuario_id
        WHERE dm.repartidor_id=?
        ORDER BY dm.fecha DESC, dm.id DESC
        """,
        (repartidor_id,),
    )
    movimientos = cursor.fetchall()

    return {
        "repartidor": repartidor,
        "resumen": {
            "servicios": int(servicios or 0),
            "generado": a_float(generado),
            "pagado": a_float(pagado),
            "ajustes_netos": a_float(ajustes_netos),
            "pendiente": a_float(pendiente),
        },
        "movimientos": movimientos,
    }


def registrar_pago_delivery_repartidor(
    cursor, repartidor_id, monto_usd, referencia, observacion, usuario_id, ahora_venezuela, obtener_ultimo_id
):
    repartidor = obtener_repartidor(cursor, repartidor_id)
    if not repartidor:
        raise ValueError("Repartidor no encontrado")

    monto = round(a_float(monto_usd), 2)
    if monto <= TOLERANCIA_COBRO:
        raise ValueError("El monto del pago debe ser mayor a 0.")

    detalle = detalle_delivery_repartidor(cursor, repartidor_id)
    saldo_actual = round(a_float(detalle["resumen"]["pendiente"] if detalle else 0), 2)
    if saldo_actual <= TOLERANCIA_COBRO:
        raise ValueError("Este repartidor no tiene saldo pendiente.")
    if monto > saldo_actual + TOLERANCIA_COBRO:
        raise ValueError("El pago no puede superar el saldo pendiente.")

    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO delivery_movimientos (
            orden_id, repartidor_id, tipo, monto_usd, fecha,
            usuario_id, referencia, observacion, movimiento_revertido_id
        )
        VALUES (NULL, ?, 'pago', ?, ?, ?, ?, ?, NULL)
        """,
        (
            repartidor_id,
            -monto,
            fecha,
            usuario_id,
            (referencia or "").strip()[:120],
            (observacion or "").strip()[:500],
        ),
    )
    return obtener_ultimo_id(cursor, "delivery_movimientos")


def obtener_conductor_delivery_por_defecto(cursor):
    """El UNICO usuario configurado como boton directo al crear un
    Delivery (mision "Configuracion del driver por defecto"). Nunca un
    nombre hardcodeado -- si nadie esta marcado como default, devuelve
    None y la UI cae a "Buscar conductor"."""
    cursor.execute(
        """
        SELECT id, nombre
        FROM usuarios
        WHERE es_conductor_delivery_default=1 AND COALESCE(activo, 1)=1
        ORDER BY id LIMIT 1
        """
    )
    return cursor.fetchone()


def listar_conductores_delivery_activos(cursor):
    cursor.execute(
        """
        SELECT id, nombre
        FROM usuarios
        WHERE es_conductor_delivery=1 AND COALESCE(activo, 1)=1
        ORDER BY nombre
        """
    )
    return cursor.fetchall()


def listar_coordinadores_delivery(cursor):
    """Mecanismo central para quienes reciben aviso cuando un Delivery
    queda NEEDS_DRIVER -- nunca una lista de nombres repetida por el
    codigo."""
    cursor.execute(
        """
        SELECT id, nombre
        FROM usuarios
        WHERE es_coordinador_delivery=1 AND COALESCE(activo, 1)=1
        ORDER BY nombre
        """
    )
    return cursor.fetchall()
