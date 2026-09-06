"""
reports.py (infraestructura)

Query service de reportes por rango de fechas (ventas, pagos, platos
vendidos, delivery) usado por /reportes, /exportar_reporte y
/dashboard -- las 3 rutas comparten EXACTAMENTE el mismo calculo, una
sola fuente de verdad. Es de SOLO LECTURA; no valida reglas de negocio
nuevas, solo agrega/formatea lo que ya esta en las tablas.

`obtener_tasa_actual` se recibe inyectado (sigue definido en
web_app.py hoy) para no crear un import circular.
"""

from collections import defaultdict

from app.domain.sales.calculations import (
    _a_float as a_float,
    convertir_pago_equivalente,
    etiqueta_metodo_pago,
    normalizar_metodo_pago,
    sumar_total_por_metodo,
)
from app.infrastructure.database.delivery import resumen_delivery_movimientos


def construir_reporte_rango(cursor, desde, hasta, obtener_tasa_actual):
    inicio = f"{desde} 00:00:00"
    fin = f"{hasta} 23:59:59"
    tasa = obtener_tasa_actual(cursor)

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            o.fecha_hora,
            COALESCE(o.tipo, ''),
            COALESCE(o.referencia, ''),
            COALESCE(o.cliente, ''),
            COALESCE(o.descuento, 0),
            o.cierre_id,
            COALESCE(u.nombre, ''),
            COALESCE(SUM(oi.precio), 0),
            o.venta_restaurante_usd,
            o.delivery_usd,
            o.total_cliente_usd
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        LEFT JOIN orden_items oi ON oi.orden_id = o.id
        WHERE o.estado = 'cerrada'
          AND o.fecha_hora >= ?
          AND o.fecha_hora <= ?
        GROUP BY o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia,
                 o.cliente, o.descuento, o.cierre_id, u.nombre,
                 o.venta_restaurante_usd, o.delivery_usd, o.total_cliente_usd
        ORDER BY o.fecha_hora ASC, o.id ASC
        """,
        (inicio, fin),
    )
    ordenes_db = cursor.fetchall()

    ventas_por_orden = []
    ventas_por_dia = defaultdict(lambda: {"total_usd": 0.0, "total_bs": 0.0, "ordenes": 0})
    total_vendido_usd = 0.0
    total_vendido_bs = 0.0
    orden_ids = []

    for orden in ordenes_db:
        (
            orden_id,
            numero_orden,
            fecha_hora,
            tipo,
            referencia,
            cliente,
            descuento_bs,
            cierre_id,
            mesonera,
            subtotal_usd,
            venta_restaurante_usd,
            delivery_usd,
            total_cliente_usd,
        ) = orden
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
        dia = (fecha_hora or "")[:10]

        total_vendido_usd += total_neto_usd
        total_vendido_bs += total_neto_bs
        orden_ids.append(orden_id)
        ventas_por_dia[dia]["total_usd"] += total_neto_usd
        ventas_por_dia[dia]["total_bs"] += total_neto_bs
        ventas_por_dia[dia]["ordenes"] += 1

        ventas_por_orden.append(
            {
                "orden_id": orden_id,
                "numero_orden": numero_orden,
                "fecha_hora": fecha_hora,
                "tipo": tipo,
                "referencia": referencia,
                "cliente": cliente,
                "cierre_id": cierre_id,
                "mesonera": mesonera,
                "subtotal_usd": round(subtotal_reporte_usd, 2),
                "descuento_bs": round(descuento_bs, 2),
                "total_usd": round(total_neto_usd, 2),
                "total_bs": round(total_neto_bs, 2),
                "delivery_usd": round(a_float(delivery_usd), 2),
                "total_cliente_usd": round(a_float(total_cliente_usd), 2),
            }
        )

    cursor.execute(
        """
        SELECT
            o.id,
            o.numero_orden,
            o.fecha_hora,
            COALESCE(o.cliente, ''),
            p.metodo,
            p.monto,
            COALESCE(p.referencia, ''),
            COALESCE(p.fecha, '')
        FROM pagos p
        JOIN ordenes o ON p.orden_id = o.id
        WHERE o.estado = 'cerrada'
          AND o.fecha_hora >= ?
          AND o.fecha_hora <= ?
        ORDER BY o.fecha_hora ASC, o.id ASC, p.id ASC
        """,
        (inicio, fin),
    )
    pagos_db = cursor.fetchall()

    pagos = []
    metodos_pago = defaultdict(lambda: {"cantidad": 0, "total_bs": 0.0, "total_usd": 0.0})
    total_punto_venta_bs = 0.0
    total_pago_movil_bs = 0.0
    total_efectivo_bs = 0.0
    total_efectivo_usd = 0.0

    for orden_id, numero_orden, fecha_hora, cliente, metodo, monto, referencia, fecha_pago in pagos_db:
        metodo = normalizar_metodo_pago(metodo)
        monto = a_float(monto)
        equiv_bs, equiv_usd = convertir_pago_equivalente(metodo, monto, tasa)

        total_punto_venta_bs, total_pago_movil_bs, total_efectivo_bs, total_efectivo_usd = sumar_total_por_metodo(
            metodo, monto, total_punto_venta_bs, total_pago_movil_bs, total_efectivo_bs, total_efectivo_usd
        )

        metodos_pago[metodo]["cantidad"] += 1
        metodos_pago[metodo]["total_bs"] += equiv_bs
        metodos_pago[metodo]["total_usd"] += equiv_usd

        pagos.append(
            {
                "orden_id": orden_id,
                "numero_orden": numero_orden,
                "fecha_hora": fecha_hora,
                "cliente": cliente,
                "metodo": metodo,
                "metodo_label": etiqueta_metodo_pago(metodo),
                "monto": round(monto, 2),
                "referencia": referencia,
                "fecha_pago": fecha_pago,
                "equivalente_bs": round(equiv_bs, 2),
                "equivalente_usd": round(equiv_usd, 2),
            }
        )

    cursor.execute(
        """
        SELECT oi.producto, COUNT(oi.id) as cantidad
        FROM orden_items oi
        JOIN ordenes o ON oi.orden_id = o.id
        WHERE o.estado = 'cerrada'
          AND o.fecha_hora >= ?
          AND o.fecha_hora <= ?
        GROUP BY oi.producto
        ORDER BY cantidad DESC, oi.producto ASC
        """,
        (inicio, fin),
    )
    platos_vendidos = [
        {"producto": producto, "cantidad": int(cantidad or 0)}
        for producto, cantidad in cursor.fetchall()
    ]

    total_equiv_bs = total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs + (total_efectivo_usd * tasa)
    total_equiv_usd = total_efectivo_usd + (
        ((total_punto_venta_bs + total_pago_movil_bs + total_efectivo_bs) / tasa) if tasa else 0.0
    )
    delivery_resumen = resumen_delivery_movimientos(cursor, inicio=inicio, fin=fin)

    ventas_por_dia_lista = []
    for dia in sorted(ventas_por_dia):
        datos = ventas_por_dia[dia]
        ventas_por_dia_lista.append(
            {
                "fecha": dia,
                "ordenes": datos["ordenes"],
                "total_usd": round(datos["total_usd"], 2),
                "total_bs": round(datos["total_bs"], 2),
            }
        )

    metodos_pago_lista = []
    for metodo, datos in sorted(metodos_pago.items()):
        metodos_pago_lista.append(
            {
                "metodo": metodo,
                "metodo_label": etiqueta_metodo_pago(metodo),
                "cantidad": datos["cantidad"],
                "total_bs": round(datos["total_bs"], 2),
                "total_usd": round(datos["total_usd"], 2),
            }
        )

    return {
        "desde": desde,
        "hasta": hasta,
        "inicio": inicio,
        "fin": fin,
        "tasa": round(tasa, 2),
        "total_vendido_usd": round(total_vendido_usd, 2),
        "total_vendido_bs": round(total_vendido_bs, 2),
        "delivery_generado_usd": delivery_resumen["generado"],
        "delivery_pagado_usd": delivery_resumen["pagado"],
        "delivery_pendiente_actual_usd": delivery_resumen["pendiente_actual"],
        "total_punto_venta_bs": round(total_punto_venta_bs, 2),
        "total_pago_movil_bs": round(total_pago_movil_bs, 2),
        "total_efectivo_bs": round(total_efectivo_bs, 2),
        "total_efectivo_usd": round(total_efectivo_usd, 2),
        "total_equiv_usd": round(total_equiv_usd, 2),
        "total_equiv_bs": round(total_equiv_bs, 2),
        "cantidad_ordenes": len(orden_ids),
        "ventas_por_orden": ventas_por_orden,
        "pagos": pagos,
        "platos_vendidos": platos_vendidos,
        "ventas_por_dia": ventas_por_dia_lista,
        "metodos_pago": metodos_pago_lista,
    }
