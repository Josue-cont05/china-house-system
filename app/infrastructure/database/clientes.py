"""
clientes.py (infraestructura)

Repositorio SQL puro del catalogo de clientes (tabla `clientes`) usado
por CxC y por el cobro a credito/parcial. Deliberadamente NO incluye
reglas de negocio (esas quedan en el dominio/aplicacion que lo invoque)
ni HTML de presentacion (eso sigue en web_app.py hasta que exista un
Blueprint propio de CxC/clientes).
"""

from app.domain.sales.calculations import _a_float as a_float


def crear_cliente(cursor, nombre, telefono, documento, notas, activo, fecha, obtener_ultimo_id):
    cursor.execute(
        """
        INSERT INTO clientes (nombre, telefono, documento, notas, activo, fecha_creacion)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (nombre, telefono, documento, notas, activo, fecha),
    )
    return obtener_ultimo_id(cursor, "clientes")


def obtener_cliente_para_cxc(cursor, cliente_id):
    try:
        cliente_id = int(cliente_id)
    except (TypeError, ValueError):
        raise ValueError("Debes seleccionar un cliente valido para la cuenta por cobrar")

    cursor.execute(
        """
        SELECT id, nombre
        FROM clientes
        WHERE id=? AND COALESCE(activo, 1)=1
        """,
        (cliente_id,),
    )
    cliente = cursor.fetchone()
    if not cliente:
        raise ValueError("Debes seleccionar un cliente valido para la cuenta por cobrar")
    return cliente


def listar_clientes_activos(cursor, busqueda=""):
    busqueda = (busqueda or "").strip().lower()
    params = []
    filtro = ""
    if busqueda:
        filtro = """
          AND (
              LOWER(nombre) LIKE ?
              OR LOWER(COALESCE(telefono, '')) LIKE ?
              OR LOWER(COALESCE(documento, '')) LIKE ?
          )
        """
        patron = f"%{busqueda}%"
        params = [patron, patron, patron]

    cursor.execute(
        f"""
        SELECT id, nombre, telefono, documento
        FROM clientes
        WHERE COALESCE(activo, 1)=1
        {filtro}
        ORDER BY LOWER(nombre), id
        LIMIT 100
        """,
        params,
    )
    return cursor.fetchall()


def cliente_json_desde_fila(cliente):
    return {
        "id": cliente[0],
        "nombre": cliente[1] or "",
        "telefono": cliente[2] or "",
        "documento": cliente[3] or "",
    }


def filtros_clientes_admin(busqueda, filtro):
    condiciones = []
    params = []
    busqueda = (busqueda or "").strip().lower()
    filtro = (filtro or "todos").strip().lower()

    if busqueda:
        condiciones.append(
            """
            (
                LOWER(c.nombre) LIKE ?
                OR LOWER(COALESCE(c.telefono, '')) LIKE ?
                OR LOWER(COALESCE(c.documento, '')) LIKE ?
            )
            """
        )
        patron = f"%{busqueda}%"
        params.extend([patron, patron, patron])

    if filtro == "activos":
        condiciones.append("COALESCE(c.activo, 1)=1")
    elif filtro == "inactivos":
        condiciones.append("COALESCE(c.activo, 1)=0")
    elif filtro == "con_saldo":
        condiciones.append(
            """
            EXISTS (
                SELECT 1 FROM cuentas_por_cobrar cxp
                WHERE cxp.cliente_id = c.id
                AND cxp.estado = 'pendiente'
                AND cxp.saldo_pendiente > 0
            )
            """
        )
    elif filtro == "sin_saldo":
        condiciones.append(
            """
            NOT EXISTS (
                SELECT 1 FROM cuentas_por_cobrar cxs
                WHERE cxs.cliente_id = c.id
                AND cxs.estado = 'pendiente'
                AND cxs.saldo_pendiente > 0
            )
            """
        )

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    return where, params


def listar_clientes_admin(cursor, busqueda="", filtro="todos"):
    where, params = filtros_clientes_admin(busqueda, filtro)
    cursor.execute(
        f"""
        SELECT
            c.id,
            c.nombre,
            COALESCE(c.telefono, ''),
            COALESCE(c.documento, ''),
            COALESCE(c.activo, 1),
            COALESCE(SUM(CASE
                WHEN cx.estado='pendiente' THEN cx.saldo_pendiente
                ELSE 0
            END), 0) AS saldo_pendiente_total,
            COALESCE(SUM(CASE
                WHEN cx.estado='pendiente' AND cx.saldo_pendiente > 0 THEN 1
                ELSE 0
            END), 0) AS cuentas_pendientes,
            COALESCE(SUM(CASE WHEN cx.estado='pagada' THEN 1 ELSE 0 END), 0) AS cuentas_pagadas
        FROM clientes c
        LEFT JOIN cuentas_por_cobrar cx ON cx.cliente_id = c.id
        {where}
        GROUP BY c.id, c.nombre, c.telefono, c.documento, c.activo
        ORDER BY COALESCE(c.activo, 1) DESC, LOWER(c.nombre), c.id
        LIMIT 300
        """,
        params,
    )
    return cursor.fetchall()


def obtener_cliente_admin(cursor, cliente_id):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(telefono, ''), COALESCE(documento, ''),
               COALESCE(notas, ''), COALESCE(activo, 1), fecha_creacion
        FROM clientes
        WHERE id=?
        """,
        (cliente_id,),
    )
    return cursor.fetchone()


def obtener_resumen_cliente(cursor, cliente_id):
    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN estado='pendiente' THEN saldo_pendiente ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN estado='pendiente' AND saldo_pendiente > 0 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN estado='pagada' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(monto_original_deuda), 0)
        FROM cuentas_por_cobrar
        WHERE cliente_id=?
        """,
        (cliente_id,),
    )
    row = cursor.fetchone() or (0, 0, 0, 0)
    return {
        "saldo_pendiente": a_float(row[0]),
        "cuentas_pendientes": int(row[1] or 0),
        "cuentas_pagadas": int(row[2] or 0),
        "total_deuda_generada": a_float(row[3]),
    }


def listar_cuentas_cliente(cursor, cliente_id):
    cursor.execute(
        """
        SELECT cx.id, cx.orden_id, o.numero_orden, cx.fecha_generacion,
               cx.monto_original_deuda, cx.saldo_pendiente, cx.estado,
               cx.cliente_nombre_snapshot
        FROM cuentas_por_cobrar cx
        LEFT JOIN ordenes o ON o.id = cx.orden_id
        WHERE cx.cliente_id=?
        ORDER BY cx.fecha_generacion DESC, cx.id DESC
        """,
        (cliente_id,),
    )
    return cursor.fetchall()
