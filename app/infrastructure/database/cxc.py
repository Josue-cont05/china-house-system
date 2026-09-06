"""
cxc.py (infraestructura)

Repositorio SQL puro de cuentas por cobrar (`cuentas_por_cobrar` /
`cuentas_por_cobrar_movimientos`). Deliberadamente NO valida reglas de
negocio de mas alto nivel (eso vive en
app/application/cxc/abonos.py para el flujo de abono, y en las rutas de
web_app.py para el resto mientras no tienen su propio caso de uso) --
aqui solo hay lectura/escritura de filas y los invariantes minimos que
son inherentes al propio dato (p. ej. `agregar_cargo_cuenta_existente`
siempre reabre la cuenta a 'pendiente' porque un cargo nuevo por
definicion implica saldo pendiente nuevo).

`get_connection`/`pk_autoincrement_sql`/`asegurar_columna` y
`obtener_ultimo_id` se reciben inyectados (mismo patron que
notifications.py / kitchen_comandas.py) para no crear un import
circular con web_app.py, que es quien los define hoy.
"""

from app.domain.sales.calculations import _a_float as a_float, convertir_pago_equivalente


def crear_tablas_cuentas_por_cobrar(get_connection, pk_autoincrement_sql, asegurar_columna):
    """Idempotente, no destructiva. Se llama desde web_app.init_db()."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS clientes (
            id {pk_autoincrement_sql()},
            nombre TEXT NOT NULL,
            telefono TEXT,
            documento TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
            id {pk_autoincrement_sql()},
            orden_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            cliente_nombre_snapshot TEXT NOT NULL,
            moneda_saldo TEXT NOT NULL DEFAULT 'USD',
            monto_original_deuda REAL NOT NULL DEFAULT 0 CHECK (monto_original_deuda >= 0),
            saldo_pendiente REAL NOT NULL DEFAULT 0 CHECK (saldo_pendiente >= 0),
            fecha_generacion TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (estado IN ('pendiente', 'pagada', 'anulada')),
            usuario_id INTEGER,
            observacion TEXT,
            UNIQUE (orden_id)
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cuentas_por_cobrar_movimientos (
            id {pk_autoincrement_sql()},
            cuenta_id INTEGER NOT NULL,
            tipo TEXT NOT NULL
                CHECK (tipo IN ('cargo', 'abono', 'ajuste', 'reverso', 'compensacion')),
            -- Delta firmado del saldo de deuda, expresado en moneda_saldo de la cuenta.
            monto_saldo REAL NOT NULL DEFAULT 0,
            moneda_pago TEXT,
            monto_pago REAL,
            tasa_movimiento REAL,
            metodo_pago TEXT,
            referencia TEXT,
            fecha TEXT,
            usuario_id INTEGER,
            observacion TEXT,
            movimiento_revertido_id INTEGER,
            referencia_externa_tipo TEXT,
            referencia_externa_id INTEGER
        )
        """
    )

    conn.commit()
    conn.close()

    asegurar_columna("ordenes", "cliente_id", "INTEGER")
    asegurar_columna("ordenes", "fecha_venta", "TEXT")
    asegurar_columna("cuentas_por_cobrar_movimientos", "movimiento_revertido_id", "INTEGER")


def orden_tiene_cxc(cursor, orden_id):
    cursor.execute("SELECT 1 FROM cuentas_por_cobrar WHERE orden_id=? LIMIT 1", (orden_id,))
    return cursor.fetchone() is not None


def obtener_cuenta_cxc_por_orden(cursor, orden_id):
    cursor.execute("SELECT id FROM cuentas_por_cobrar WHERE orden_id=?", (orden_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def validar_recobro_cxc(cursor, orden_id):
    cuenta_id = obtener_cuenta_cxc_por_orden(cursor, orden_id)
    if cuenta_id is None:
        return None

    raise ValueError(
        "Esta orden tiene una cuenta por cobrar asociada y no puede recobrarse directamente. "
        "Debe utilizarse un proceso administrativo de reversion."
    )


def filtros_cxc_admin(busqueda, estado, cliente_id):
    condiciones = []
    params = []
    busqueda = (busqueda or "").strip().lower()
    estado = (estado or "pendiente").strip().lower()
    cliente_id = (str(cliente_id or "")).strip()

    if estado in ("pendiente", "pagada", "anulada"):
        condiciones.append("cx.estado=?")
        params.append(estado)

    if cliente_id:
        condiciones.append("cx.cliente_id=?")
        params.append(cliente_id)

    if busqueda:
        condiciones.append(
            """
            (
                LOWER(cx.cliente_nombre_snapshot) LIKE ?
                OR LOWER(COALESCE(c.nombre, '')) LIKE ?
                OR LOWER(COALESCE(c.telefono, '')) LIKE ?
                OR LOWER(COALESCE(c.documento, '')) LIKE ?
                OR LOWER(CAST(COALESCE(o.numero_orden, o.id) AS TEXT)) LIKE ?
            )
            """
        )
        patron = f"%{busqueda}%"
        params.extend([patron, patron, patron, patron, patron])

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    return where, params


def resumen_cuentas_por_cobrar(cursor):
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN estado='pendiente' THEN saldo_pendiente ELSE 0 END), 0),
            COUNT(DISTINCT CASE WHEN estado='pendiente' AND saldo_pendiente > 0 THEN cliente_id END),
            COALESCE(SUM(CASE WHEN estado='pendiente' AND saldo_pendiente > 0 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN estado='pagada' THEN 1 ELSE 0 END), 0)
        FROM cuentas_por_cobrar
        """
    )
    row = cursor.fetchone() or (0, 0, 0, 0)
    return {
        "saldo_total": a_float(row[0]),
        "clientes_con_deuda": int(row[1] or 0),
        "cuentas_pendientes": int(row[2] or 0),
        "cuentas_pagadas": int(row[3] or 0),
    }


def listar_cuentas_por_cobrar_admin(cursor, busqueda="", estado="pendiente", cliente_id=""):
    where, params = filtros_cxc_admin(busqueda, estado, cliente_id)
    cursor.execute(
        f"""
        SELECT
            cx.id,
            cx.cliente_id,
            cx.cliente_nombre_snapshot,
            COALESCE(c.nombre, ''),
            COALESCE(c.telefono, ''),
            COALESCE(c.documento, ''),
            cx.orden_id,
            o.numero_orden,
            cx.fecha_generacion,
            cx.monto_original_deuda,
            cx.saldo_pendiente,
            cx.estado
        FROM cuentas_por_cobrar cx
        LEFT JOIN clientes c ON c.id = cx.cliente_id
        LEFT JOIN ordenes o ON o.id = cx.orden_id
        {where}
        ORDER BY cx.fecha_generacion DESC, cx.id DESC
        LIMIT 300
        """,
        params,
    )
    return cursor.fetchall()


def calcular_suma_movimientos_cxc(cursor, cuenta_id):
    cursor.execute(
        """
        SELECT COALESCE(SUM(monto_saldo), 0)
        FROM cuentas_por_cobrar_movimientos
        WHERE cuenta_id=?
        """,
        (cuenta_id,),
    )
    row = cursor.fetchone()
    return round(a_float(row[0] if row else 0), 2)


def calcular_pagado_inicial_orden(cursor, orden_id, tasa_historica):
    cursor.execute(
        """
        SELECT metodo, monto
        FROM pagos
        WHERE orden_id=?
        ORDER BY id
        """,
        (orden_id,),
    )
    pagos = cursor.fetchall()
    total_usd = 0.0
    total_bs = 0.0
    for metodo, monto in pagos:
        pago_bs, pago_usd = convertir_pago_equivalente(metodo, monto, tasa_historica)
        total_bs += pago_bs
        total_usd += pago_usd
    return {
        "usd": round(total_usd, 2),
        "bs": round(total_bs, 2),
        "pagos": pagos,
    }


def obtener_detalle_cuenta_cxc(cursor, cuenta_id):
    cursor.execute(
        """
        SELECT
            cx.id, cx.orden_id, cx.cliente_id, cx.cliente_nombre_snapshot,
            cx.moneda_saldo, cx.monto_original_deuda, cx.saldo_pendiente,
            cx.fecha_generacion, cx.estado, COALESCE(cx.observacion, ''),
            COALESCE(c.nombre, ''), COALESCE(c.telefono, ''), COALESCE(c.documento, ''),
            o.numero_orden, o.fecha_venta, o.fecha_cobro, o.tasa_cobro,
            o.subtotal_usd, o.descuento_bs_snapshot, o.total_usd, o.total_bs
        FROM cuentas_por_cobrar cx
        LEFT JOIN clientes c ON c.id = cx.cliente_id
        LEFT JOIN ordenes o ON o.id = cx.orden_id
        WHERE cx.id=?
        """,
        (cuenta_id,),
    )
    cuenta = cursor.fetchone()
    if not cuenta:
        return None

    cursor.execute(
        """
        SELECT m.fecha, m.tipo, m.monto_saldo, m.moneda_pago, m.monto_pago,
               m.tasa_movimiento, m.metodo_pago, m.referencia,
               COALESCE(u.nombre, ''), COALESCE(m.observacion, '')
        FROM cuentas_por_cobrar_movimientos m
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE m.cuenta_id=?
        ORDER BY m.fecha ASC, m.id ASC
        """,
        (cuenta_id,),
    )
    movimientos = cursor.fetchall()
    suma_movimientos = calcular_suma_movimientos_cxc(cursor, cuenta_id)
    tasa_historica = a_float(cuenta[16])
    pagado_inicial = calcular_pagado_inicial_orden(cursor, cuenta[1], tasa_historica)
    inconsistente = abs(round(a_float(cuenta[6]) - suma_movimientos, 2)) > 0.01

    return {
        "cuenta": cuenta,
        "movimientos": movimientos,
        "suma_movimientos": suma_movimientos,
        "pagado_inicial": pagado_inicial,
        "inconsistente": inconsistente,
    }


def insertar_movimiento_abono_cxc(
    cursor,
    cuenta_id,
    monto_saldo,
    moneda_pago,
    monto_pago,
    tasa_movimiento,
    metodo_pago,
    referencia,
    fecha,
    usuario_id,
    observacion,
):
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar_movimientos (
            cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
            tasa_movimiento, metodo_pago, referencia, fecha,
            usuario_id, observacion, movimiento_revertido_id,
            referencia_externa_tipo, referencia_externa_id
        )
        VALUES (?, 'abono', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """,
        (
            cuenta_id,
            monto_saldo,
            moneda_pago,
            monto_pago,
            tasa_movimiento,
            metodo_pago,
            referencia,
            fecha,
            usuario_id,
            observacion,
        ),
    )


def actualizar_saldo_cxc(cursor, cuenta_id, nuevo_saldo, nuevo_estado):
    cursor.execute(
        """
        UPDATE cuentas_por_cobrar
        SET saldo_pendiente=?, estado=?
        WHERE id=?
        """,
        (nuevo_saldo, nuevo_estado, cuenta_id),
    )


def insertar_movimiento_cxc_inicial(cursor, cuenta_id, saldo_usd, fecha, usuario_id):
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar_movimientos (
            cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
            tasa_movimiento, metodo_pago, referencia, fecha,
            usuario_id, observacion, movimiento_revertido_id,
            referencia_externa_tipo, referencia_externa_id
        )
        VALUES (?, 'cargo', ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL)
        """,
        (
            cuenta_id,
            saldo_usd,
            fecha,
            usuario_id,
            "Cargo inicial generado al cobrar la orden",
        ),
    )


def crear_cuenta_por_cobrar_inicial(
    cursor, orden_id, cliente_id, cliente_nombre, saldo_usd, fecha, usuario_id, obtener_ultimo_id
):
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar (
            orden_id, cliente_id, cliente_nombre_snapshot, moneda_saldo,
            monto_original_deuda, saldo_pendiente, fecha_generacion,
            estado, usuario_id, observacion
        )
        VALUES (?, ?, ?, 'USD', ?, ?, ?, 'pendiente', ?, ?)
        """,
        (
            orden_id,
            cliente_id,
            cliente_nombre,
            saldo_usd,
            saldo_usd,
            fecha,
            usuario_id,
            "Cuenta por cobrar generada al cobrar la orden",
        ),
    )
    cuenta_id = obtener_ultimo_id(cursor, "cuentas_por_cobrar")
    insertar_movimiento_cxc_inicial(cursor, cuenta_id, saldo_usd, fecha, usuario_id)
    return cuenta_id


def agregar_cargo_cuenta_existente(cursor, cuenta_id, monto_cargo, fecha, usuario_id, observacion):
    """Agrega deuda NUEVA a una cuenta por cobrar que ya existe (mision
    "seguridad financiera de agregados post-cobro", seccion 7: una orden
    que ya genero CxC y despues recibe consumo nuevo debe sumarse a la
    MISMA cuenta -- cuentas_por_cobrar.orden_id es UNIQUE, nunca se crea
    una segunda -- sin perder ni duplicar el saldo previo). Inserta un
    movimiento 'cargo' positivo (mismo patron que
    insertar_movimiento_cxc_inicial) y reabre la cuenta a 'pendiente' si
    ya se habia saldado por completo."""
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar_movimientos (
            cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
            tasa_movimiento, metodo_pago, referencia, fecha,
            usuario_id, observacion, movimiento_revertido_id,
            referencia_externa_tipo, referencia_externa_id
        )
        VALUES (?, 'cargo', ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL)
        """,
        (cuenta_id, monto_cargo, fecha, usuario_id, observacion),
    )
    cursor.execute("SELECT saldo_pendiente FROM cuentas_por_cobrar WHERE id=?", (cuenta_id,))
    nuevo_saldo = round(a_float(cursor.fetchone()[0]) + monto_cargo, 2)
    cursor.execute(
        "UPDATE cuentas_por_cobrar SET saldo_pendiente=?, estado='pendiente' WHERE id=?",
        (nuevo_saldo, cuenta_id),
    )
    return nuevo_saldo
