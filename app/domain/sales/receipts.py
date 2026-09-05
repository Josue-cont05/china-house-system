"""
receipts.py

Construye el contrato estructurado del recibo del cliente (consumido por
/facturas_pendientes y, en definitiva, por scripts_locales/factura_presentacion.py
via el worker de recibos). Es la UNICA autoridad sobre que monto es "el
total" del cliente: nadie fuera de este modulo debe recalcular USD->Bs,
descuentos ni delivery para el recibo.

Dos casos, nunca mezclados:

1. Orden YA COBRADA (`tasa_cobro` no es None): usa EXCLUSIVAMENTE el
   snapshot historico de /cobrar. Nunca la tasa actual. El resultado de
   una orden cobrada no puede cambiar aunque cambie la tasa despues.

2. Cuenta PROVISIONAL (orden abierta/en cocina/listo, sin cobrar todavia):
   usa la MISMA formula autoritativa que ya usa /orden/<id> para mostrar
   el total de una orden abierta (calcular_totales_visuales_orden), con
   la tasa vigente en ese momento. Si la tasa cambia antes de cobrar, el
   valor definitivo en el cobro real puede diferir - eso es esperado y
   aceptado (aprobado explicitamente): una cuenta provisional no es un
   compromiso financiero.

Compatibilidad con datos historicos (ordenes cobradas ANTES de que
existiera la columna `total_cliente_bs`):

- Legacy (delivery como item normal, `venta_restaurante_usd`/
  `delivery_usd`/`total_cliente_usd` quedaron NULL en /cobrar): `total_bs`
  YA es el total completo del cliente (el delivery nunca se separo) -> se
  usa tal cual.
- Explicito historico sin `total_cliente_bs` (cobrado antes de esta
  migracion): se reconstruye `total_cliente_usd * tasa_cobro` - ambos
  valores 100% historicos del mismo snapshot, nunca tasa viva. Este
  fallback NUNCA se persiste durante una lectura, solo se calcula al
  vuelo para responder ese recibo puntual.
- Explicito nuevo (cobrado con esta migracion ya activa): `total_cliente_bs`
  ya viene persistido por /cobrar -> se usa directo, sin recalcular.
"""

from app.domain.sales.calculations import _a_float, TOLERANCIA_COBRO
from app.domain.sales.item_descriptions import agrupar_items_recibo
from app.domain.sales.order_totals import calcular_totales_visuales_orden


def construir_recibo_provisional(items, delivery_usd, descuento_bs, tasa_actual):
    """Cuenta provisional: orden aun no cobrada. Misma formula que
    /orden/<id> (calcular_totales_visuales_orden), con la tasa vigente en
    este momento. NUNCA se llama con una tasa historica: si la orden ya
    tiene snapshot, se debe usar construir_recibo_cobrado en su lugar."""
    totales = calcular_totales_visuales_orden(items, delivery_usd, tasa_actual, descuento_bs)

    delivery_final = round(_a_float(delivery_usd), 2)
    descuento_final = round(_a_float(descuento_bs) / tasa_actual, 2) if tasa_actual else 0.0

    return {
        "cobrada": False,
        "items": agrupar_items_recibo(items),
        "subtotal": totales["total_usd"],
        "descuento": descuento_final,
        "delivery": delivery_final if delivery_final > TOLERANCIA_COBRO else 0.0,
        "total": totales["total_orden_usd"],
        "total_bs": totales["total_orden_bs"],
    }


def construir_recibo_cobrado(
    items,
    *,
    tasa_cobro,
    subtotal_usd,
    descuento_bs,
    total_usd,
    total_bs,
    venta_restaurante_usd,
    delivery_usd,
    total_cliente_usd,
    total_cliente_bs,
):
    """Orden ya cobrada: usa exclusivamente el snapshot historico de
    /cobrar. `tasa_cobro` nunca se usa para recalcular precios, solo para
    convertir el descuento (guardado en Bs) a USD, y como ultimo recurso
    de compatibilidad si falta `total_cliente_bs` en datos historicos."""
    es_legacy_delivery_como_item = (
        venta_restaurante_usd is None and delivery_usd is None and total_cliente_usd is None
    )

    if es_legacy_delivery_como_item:
        # El delivery nunca se separo de la venta: total_usd/total_bs YA
        # son el total completo que pago el cliente.
        total_final_usd = total_usd
        total_final_bs = total_bs
        delivery_final = 0.0
    else:
        total_final_usd = total_cliente_usd
        delivery_final = round(_a_float(delivery_usd), 2)

        if total_cliente_bs is not None:
            total_final_bs = total_cliente_bs
        elif total_cliente_usd is not None and tasa_cobro:
            # Fallback de compatibilidad: orden explicita cobrada ANTES de
            # que existiera total_cliente_bs. Reconstruccion 100%
            # historica (tasa_cobro del MISMO snapshot), nunca tasa viva.
            # No se persiste aqui: es solo para responder esta lectura.
            total_final_bs = round(_a_float(total_cliente_usd) * tasa_cobro, 2)
        else:
            total_final_bs = total_bs

    descuento_final = round(_a_float(descuento_bs) / tasa_cobro, 2) if tasa_cobro else 0.0

    return {
        "cobrada": True,
        "items": agrupar_items_recibo(items),
        "subtotal": _a_float(subtotal_usd),
        "descuento": descuento_final,
        "delivery": delivery_final if delivery_final > TOLERANCIA_COBRO else 0.0,
        "total": _a_float(total_final_usd),
        "total_bs": _a_float(total_final_bs),
    }
