"""
cierre.py (infraestructura)

Query service + escrituras del cierre de jornada. `construir_resumen_cierre`
es de SOLO LECTURA (usado tanto para previsualizar el cierre en
/cierre como para decidir si /cerrar_jornada puede proceder);
`ejecutar_cierre_jornada` hace las escrituras reales (INSERT
cierres_caja, INSERT cierre_detalle por producto, UPDATE ordenes SET
cierre_id) una vez que la ruta ya valido las precondiciones (sin
ordenes activas, sin pedidos pendientes en Despacho, al menos una
orden cerrada).

`obtener_tasa_actual` se recibe inyectado (sigue definido en
web_app.py hoy) para no crear un import circular.
"""

from app.domain.sales.calculations import (
    _a_float as a_float,
    etiqueta_metodo_pago,
    normalizar_metodo_pago,
    sumar_total_por_metodo,
)
from app.infrastructure.database.delivery import resumen_delivery_movimientos


def construir_resumen_cierre(cursor, obtener_tasa_actual):
    tasa = obtener_tasa_actual(cursor)

    cursor.execute(
        """
        SELECT MIN(fecha_hora)
        FROM ordenes
        WHERE cierre_id IS NULL
        """
    )
    row_inicio = cursor.fetchone()
    inicio_jornada = row_inicio[0] if row_inicio and row_inicio[0] else "Sin ordenes pendientes"

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM ordenes
        WHERE cierre_id IS NULL
          AND estado != 'cerrada'
        """,
    )
    ordenes_activas = int(cursor.fetchone()[0] or 0)

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            COALESCE(o.cliente, ''),
            COALESCE(o.descuento, 0),
            COALESCE(SUM(oi.precio), 0),
            o.venta_restaurante_usd,
            o.delivery_usd,
            o.total_cliente_usd
        FROM ordenes o
        LEFT JOIN orden_items oi ON oi.orden_id = o.id
        WHERE o.cierre_id IS NULL
          AND o.estado = 'cerrada'
        GROUP BY o.id, o.numero_orden, o.cliente, o.descuento,
                 o.venta_restaurante_usd, o.delivery_usd, o.total_cliente_usd
        ORDER BY o.id ASC
        """
    )
    filas_ordenes = cursor.fetchall()

    ordenes_cerradas = []
    ordenes_cerradas_detalle = []
    orden_ids = []
    total_ventas_usd = 0.0
    total_ventas_bs = 0.0

    for orden_id, numero_orden, cliente, descuento_bs, subtotal_usd, venta_restaurante_usd, delivery_usd, total_cliente_usd in filas_ordenes:
        subtotal_usd = a_float(subtotal_usd)
        descuento_bs = a_float(descuento_bs)
        descuento_usd = (descuento_bs / tasa) if tasa else 0.0
        if venta_restaurante_usd is not None:
            total_neto_usd = max(a_float(venta_restaurante_usd), 0.0)
            subtotal_reporte_usd = total_neto_usd
            total_neto_bs = round(total_neto_usd * tasa, 2)
        else:
            total_neto_usd = max(subtotal_usd - descuento_usd, 0.0)
            subtotal_reporte_usd = subtotal_usd
            total_neto_bs = max((subtotal_usd * tasa) - descuento_bs, 0.0)

        total_ventas_usd += total_neto_usd
        total_ventas_bs += total_neto_bs
        orden_ids.append(orden_id)
        ordenes_cerradas.append((orden_id, numero_orden, descuento_bs))
        ordenes_cerradas_detalle.append(
            {
                "id": orden_id,
                "numero_orden": numero_orden,
                "cliente": cliente,
                "descuento_bs": descuento_bs,
                "subtotal_usd": subtotal_reporte_usd,
                "total_neto_usd": total_neto_usd,
                "total_neto_bs": total_neto_bs,
                "delivery_usd": a_float(delivery_usd),
                "total_cliente_usd": a_float(total_cliente_usd),
            }
        )

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            COALESCE(o.cliente, ''),
            p.metodo,
            p.monto,
            p.referencia,
            p.fecha
        FROM pagos p
        JOIN ordenes o ON p.orden_id = o.id
        WHERE o.cierre_id IS NULL
          AND o.estado = 'cerrada'
        ORDER BY o.numero_orden ASC, o.id ASC, p.id ASC
        """
    )
    filas_pagos = cursor.fetchall()

    total_punto_venta_bs = 0.0
    total_pago_movil_bs = 0.0
    total_efectivo_bs = 0.0
    total_efectivo_usd = 0.0
    auditoria_pagos = []

    for orden_id, numero_orden, cliente, metodo, monto, referencia, fecha in filas_pagos:
        metodo = normalizar_metodo_pago(metodo)
        monto = a_float(monto)

        total_punto_venta_bs, total_pago_movil_bs, total_efectivo_bs, total_efectivo_usd = sumar_total_por_metodo(
            metodo, monto, total_punto_venta_bs, total_pago_movil_bs, total_efectivo_bs, total_efectivo_usd
        )

        auditoria_pagos.append(
            {
                "orden_id": orden_id,
                "numero_orden": numero_orden,
                "cliente": cliente,
                "metodo": metodo,
                "metodo_label": etiqueta_metodo_pago(metodo),
                "monto": monto,
                "referencia": referencia or "",
                "fecha": fecha or "",
            }
        )

    cursor.execute(
        """
        SELECT oi.producto, COUNT(oi.id) as cantidad
        FROM orden_items oi
        JOIN ordenes o ON oi.orden_id = o.id
        WHERE o.cierre_id IS NULL
          AND o.estado = 'cerrada'
        GROUP BY oi.producto
        ORDER BY cantidad DESC, oi.producto ASC
        """
    )
    productos = cursor.fetchall()
    inicio_delivery = inicio_jornada if inicio_jornada != "Sin ordenes pendientes" else None
    delivery_resumen = resumen_delivery_movimientos(
        cursor,
        inicio=inicio_delivery,
        solo_ordenes_sin_cierre=True,
    )

    total_cobrado_equiv_bs = (
        total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs + (total_efectivo_usd * tasa)
    )
    total_cobrado_equiv_usd = total_efectivo_usd + (
        ((total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs) / tasa) if tasa else 0.0
    )
    diferencia_usd = total_ventas_usd - total_cobrado_equiv_usd
    diferencia_bs = total_ventas_bs - total_cobrado_equiv_bs

    return {
        "inicio_jornada": inicio_jornada,
        "tasa": tasa,
        "ordenes_activas": ordenes_activas,
        "ordenes_cerradas": ordenes_cerradas,
        "ordenes_cerradas_detalle": ordenes_cerradas_detalle,
        "orden_ids": orden_ids,
        "cantidad_ordenes_cerradas": len(ordenes_cerradas),
        "total_ventas_usd": round(total_ventas_usd, 2),
        "total_ventas_bs": round(total_ventas_bs, 2),
        "total_ventas": round(total_ventas_bs, 2),
        "delivery_generado_usd": delivery_resumen["generado"],
        "delivery_pagado_usd": delivery_resumen["pagado"],
        "delivery_pendiente_actual_usd": delivery_resumen["pendiente_actual"],
        "total_punto_venta_bs": round(total_punto_venta_bs, 2),
        "total_pago_movil_bs": round(total_pago_movil_bs, 2),
        "total_efectivo_bs": round(total_efectivo_bs, 2),
        "total_efectivo_usd": round(total_efectivo_usd, 2),
        "total_cobrado_equiv_bs": round(total_cobrado_equiv_bs, 2),
        "total_cobrado_equiv_usd": round(total_cobrado_equiv_usd, 2),
        "total_cobrado": round(total_cobrado_equiv_bs, 2),
        "diferencia_usd": round(diferencia_usd, 2),
        "diferencia_bs": round(diferencia_bs, 2),
        "diferencia": round(diferencia_bs, 2),
        "auditoria_pagos": auditoria_pagos,
        "productos": productos,
    }


def ejecutar_cierre_jornada(cursor, resumen, fecha_cierre, usuario_id, obtener_ultimo_id):
    cursor.execute(
        """
        INSERT INTO cierres_caja (fecha, total_ventas, usuario_id)
        VALUES (?, ?, ?)
        """,
        (fecha_cierre, resumen["total_ventas_bs"], usuario_id),
    )
    cierre_id = obtener_ultimo_id(cursor, "cierres_caja")

    for producto, cantidad in resumen["productos"]:
        cursor.execute(
            """
            INSERT INTO cierre_detalle (cierre_id, producto, cantidad)
            VALUES (?, ?, ?)
            """,
            (cierre_id, producto, cantidad),
        )

    orden_ids = resumen["orden_ids"]
    if orden_ids:
        placeholders = ",".join("?" for _ in orden_ids)
        cursor.execute(
            f"""
            UPDATE ordenes
            SET cierre_id = ?
            WHERE id IN ({placeholders})
            """,
            [cierre_id] + orden_ids,
        )

    return cierre_id
