from app.domain.sales.calculations import (
    TOLERANCIA_COBRO,
    _a_float,
    es_producto_delivery_legacy,
)


def calcular_totales_visuales_delivery(items, delivery_usd):
    venta_restaurante = 0.0
    delivery_legacy = 0.0
    for item in items:
        producto = item[0]
        precio = _a_float(item[1])
        categoria = item[4] if len(item) > 4 else None
        if es_producto_delivery_legacy(producto, categoria):
            delivery_legacy += precio
        else:
            venta_restaurante += precio

    delivery_explicit = _a_float(delivery_usd)
    return {
        "venta_restaurante_usd": round(venta_restaurante, 2),
        "delivery_usd": round(delivery_explicit, 2),
        "delivery_legacy_usd": round(delivery_legacy, 2),
        "total_cliente_usd": round(
            venta_restaurante + delivery_legacy + delivery_explicit,
            2,
        ),
    }


def calcular_totales_visuales_orden(items, delivery_usd, tasa, descuento):
    delivery_usd_convertido = _a_float(delivery_usd)
    totales_visuales = calcular_totales_visuales_delivery(items, delivery_usd)

    total_usd = totales_visuales["venta_restaurante_usd"]
    total_bs = total_usd * tasa
    total_cliente_usd = totales_visuales["total_cliente_usd"]
    total_cliente_bs = total_cliente_usd * tasa
    delivery_legacy_usd = totales_visuales["delivery_legacy_usd"]
    tiene_delivery_legacy = delivery_legacy_usd > TOLERANCIA_COBRO
    total_bs_final = max(total_bs - descuento, 0)
    total_delivery_bs = round((delivery_usd_convertido + delivery_legacy_usd) * tasa, 2)
    total_orden_bs = round(total_bs_final + total_delivery_bs, 2)
    total_orden_usd = round((total_orden_bs / tasa) if tasa else total_cliente_usd, 2)

    return {
        "total_usd": total_usd,
        "total_bs": total_bs,
        "total_cliente_usd": total_cliente_usd,
        "total_cliente_bs": total_cliente_bs,
        "delivery_legacy_usd": delivery_legacy_usd,
        "tiene_delivery_legacy": tiene_delivery_legacy,
        "descuento": descuento,
        "total_bs_final": total_bs_final,
        "total_delivery_bs": total_delivery_bs,
        "total_orden_bs": total_orden_bs,
        "total_orden_usd": total_orden_usd,
    }
