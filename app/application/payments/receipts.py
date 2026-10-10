"""
receipts.py (aplicacion)

Caso de uso "activar/reimprimir la impresion del recibo oficial de una
orden" (rutas /activar_factura/<id> y /reimprimir_factura/<id> en
web_app.py). Construye un snapshot INMUTABLE del recibo -- con la MISMA
autoridad financiera que /facturas_pendientes:
`app.domain.sales.receipts.construir_recibo_provisional`/
`construir_recibo_cobrado`, nunca recalculado aparte -- y lo encola
como payload de un print_job nuevo (Printing 2.0,
app.infrastructure.database.print_queue.crear_job_en_cursor).

`token` es None para la activacion normal (evento "base") o el token de
una reimpresion explicita (evento distinto: nunca se confunde con el
original).

Los items se leen ya filtrados por `incluido_en_snapshot` (mision
"recibos post-cobro", dc3f52c): un agregado post-cobro todavia no
liquidado nunca debe colarse en este snapshot congelado.

Si el tipo de orden no es uno de los conocidos (Mesa/Delivery/Para
llevar), NO se crea el job (se loguea y se deja constancia): mejor no
enrutar un recibo a un rol adivinado que enrutarlo mal. El polling
legacy de /facturas_pendientes sigue funcionando como red de seguridad
mientras tanto.

`obtener_tasa_actual` se recibe inyectado (sigue definido en
web_app.py hoy) para no crear un import circular."""

from collections import defaultdict

from app.domain.sales.print_queue import TIPO_JOB_RECIBO, TipoOrdenDesconocido, rol_recibo_por_tipo_orden
from app.domain.sales.receipts import construir_recibo_cobrado, construir_recibo_provisional
from app.infrastructure.database.print_queue import crear_job_en_cursor


def crear_print_job_recibo(cursor, orden_id, token, fecha_evento, obtener_tasa_actual):
    cursor.execute(
        """
        SELECT o.numero_orden, o.tipo, o.cliente, o.referencia, u.nombre,
               o.fecha_hora, o.fecha_cobro, o.tasa_cobro, o.subtotal_usd,
               o.descuento_bs_snapshot, o.total_usd, o.total_bs,
               o.venta_restaurante_usd, o.delivery_usd, o.total_cliente_usd,
               o.total_cliente_bs, o.descuento
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=?
        LIMIT 1
        """,
        (orden_id,),
    )
    o = cursor.fetchone()
    if o is None:
        return False

    try:
        rol = rol_recibo_por_tipo_orden(o[1])
    except TipoOrdenDesconocido as e:
        print(f"ADVERTENCIA: no se creo print_job de recibo para orden {orden_id}: {e}")
        return False

    cursor.execute(
        """
        SELECT producto, precio, COALESCE(indicacion, '')
        FROM orden_items
        WHERE orden_id=? AND COALESCE(incluido_en_snapshot, 1)=1
        ORDER BY id ASC
        """,
        (orden_id,),
    )
    items = cursor.fetchall()

    tasa_cobro = o[7]
    if tasa_cobro is None:
        tasa_actual = obtener_tasa_actual(cursor)
        recibo = construir_recibo_provisional(
            items, delivery_usd=o[13], descuento_bs=o[16], tasa_actual=tasa_actual
        )
    else:
        recibo = construir_recibo_cobrado(
            items,
            tasa_cobro=tasa_cobro,
            subtotal_usd=o[8],
            descuento_bs=o[9],
            total_usd=o[10],
            total_bs=o[11],
            venta_restaurante_usd=o[12],
            delivery_usd=o[13],
            total_cliente_usd=o[14],
            total_cliente_bs=o[15],
        )

    payload = {
        "id": orden_id,
        "numero": o[0],
        "tipo": o[1],
        "cliente": o[2],
        "referencia": o[3],
        "usuario": o[4] if o[4] else "N/A",
        "fecha_hora": o[6] if o[6] else o[5],
        **recibo,
    }
    event_key = f"{orden_id}-{token if token else 'base'}"
    crear_job_en_cursor(
        cursor,
        event_key=event_key,
        job_type=TIPO_JOB_RECIBO,
        required_role=rol,
        payload=payload,
        fecha=fecha_evento,
    )
    return True


def activar_factura_orden(cursor, orden_id, ahora_venezuela, obtener_tasa_actual):
    """Marca una orden para facturar y encola la impresion del recibo
    oficial -- la MISMA logica que ya usa la ruta /activar_factura/<id>
    (web_app.py), extraida aqui para que /cobrar pueda facturar
    directamente al cobrar ("FACTURAR Y CONTINUAR") sin duplicarla. El
    UPDATE respeta la misma condicion que la ruta original
    (`cierre_id IS NULL`: nunca factura una orden ya archivada), y se
    llama ANTES del commit de /cobrar para que quede atomico con el
    cobro -- si facturar fallara, todo el cobro se revierte, igual que
    ya pasa hoy con CxC/delivery/inventario en esa misma ruta."""
    cursor.execute(
        "UPDATE ordenes SET facturar=1, factura_reimpresion_token=NULL WHERE id=? AND cierre_id IS NULL",
        (orden_id,),
    )
    crear_print_job_recibo(
        cursor, orden_id, None, ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S"), obtener_tasa_actual
    )


def obtener_facturas_pendientes(cursor, obtener_tasa_actual):
    """Caso de uso "preparar recibo provisional/oficial" para el polling
    legacy de /facturas_pendientes (red de seguridad para impresoras que
    no hablan Printing 2.0). Devuelve una lista de dicts listos para
    `jsonify`, uno por cada orden con `facturar=1`, usando la MISMA
    autoridad financiera (`construir_recibo_provisional`/
    `construir_recibo_cobrado`) que `crear_print_job_recibo`. Batch (una
    sola consulta de `orden_items` para todas las ordenes) para evitar
    N+1 en el polling."""
    cursor.execute(
        """
        SELECT o.id, o.numero_orden, o.tipo, o.cliente, o.referencia, u.nombre,
               o.factura_reimpresion_token, o.fecha_hora, o.fecha_cobro,
               o.tasa_cobro, o.subtotal_usd, o.descuento_bs_snapshot,
               o.total_usd, o.total_bs, o.venta_restaurante_usd,
               o.delivery_usd, o.total_cliente_usd, o.total_cliente_bs,
               o.descuento
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.facturar = 1
          AND o.cierre_id IS NULL
        """
    )
    ordenes = cursor.fetchall()
    if not ordenes:
        return []

    orden_ids = [o[0] for o in ordenes]
    placeholders = ",".join("?" for _ in orden_ids)
    cursor.execute(
        f"""
        SELECT orden_id, producto, precio, COALESCE(indicacion, '')
        FROM orden_items
        WHERE orden_id IN ({placeholders})
          AND COALESCE(incluido_en_snapshot, 1)=1
        ORDER BY id ASC
        """,
        orden_ids,
    )

    items_por_orden = defaultdict(list)
    for orden_id, producto, precio, indicacion in cursor.fetchall():
        items_por_orden[orden_id].append((producto, precio, indicacion))

    tasa_actual = None
    if any(o[9] is None for o in ordenes):
        tasa_actual = obtener_tasa_actual(cursor)

    resultado = []
    for o in ordenes:
        items = items_por_orden[o[0]]
        tasa_cobro = o[9]

        if tasa_cobro is None:
            recibo = construir_recibo_provisional(
                items,
                delivery_usd=o[15],
                descuento_bs=o[18],
                tasa_actual=tasa_actual,
            )
        else:
            recibo = construir_recibo_cobrado(
                items,
                tasa_cobro=tasa_cobro,
                subtotal_usd=o[10],
                descuento_bs=o[11],
                total_usd=o[12],
                total_bs=o[13],
                venta_restaurante_usd=o[14],
                delivery_usd=o[15],
                total_cliente_usd=o[16],
                total_cliente_bs=o[17],
            )

        resultado.append(
            {
                "id": o[0],
                "numero": o[1],
                "tipo": o[2],
                "cliente": o[3],
                "referencia": o[4],
                "usuario": o[5] if o[5] else "N/A",
                "fecha_hora": o[8] if o[8] else o[7],
                "evento_impresion": f"{o[0]}-{o[6] if o[6] else 'base'}",
                **recibo,
            }
        )

    return resultado
