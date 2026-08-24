import re


DELIVERY_MONTO_MAXIMO = 100.0
TOLERANCIA_COBRO = 0.0001


def _a_float(valor, default=0.0):
    try:
        if valor is None:
            return default
        texto = str(valor).strip().replace(",", ".")
        if texto == "":
            return default
        return float(texto)
    except Exception:
        return default


def normalizar_metodo_pago(metodo):
    metodo = (metodo or "").strip()
    if metodo == "pago_movil":
        return "bs_pago_movil"
    return metodo


def es_categoria_delivery(categoria):
    return (categoria or "").strip().lower() == "delivery"


def es_producto_delivery_legacy(nombre, categoria=None):
    nombre_limpio = (nombre or "").strip().lower()
    if es_categoria_delivery(categoria):
        return True
    return bool(re.fullmatch(r"delivery\s+\d+(?:[.,]\d{1,2})?", nombre_limpio))


def normalizar_monto_delivery(valor):
    texto = str(valor if valor is not None else "").strip().replace(",", ".")
    if texto == "":
        texto = "0"
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", texto):
        raise ValueError("El monto de delivery debe ser cero o positivo, con maximo 2 decimales.")
    monto = round(float(texto), 2)
    if monto < 0:
        raise ValueError("El monto de delivery no puede ser negativo.")
    if monto > DELIVERY_MONTO_MAXIMO:
        raise ValueError(f"El monto de delivery no puede superar ${DELIVERY_MONTO_MAXIMO:.2f}.")
    return monto


def convertir_pago_equivalente(metodo, monto, tasa):
    metodo = normalizar_metodo_pago(metodo)
    monto = _a_float(monto)

    if metodo == "usd":
        return monto * tasa, monto

    if metodo in ("punto_venta", "bs_pago_movil", "bs_efectivo"):
        usd = (monto / tasa) if tasa else 0.0
        return monto, usd

    return 0.0, 0.0


def calcular_totales_cobro(precios_items, tasa, descuento_bs):
    subtotal_usd = round(sum(_a_float(precio) for precio in precios_items), 2)
    tasa_cobro = _a_float(tasa)
    if tasa_cobro <= 0:
        raise ValueError("La tasa de cobro debe ser mayor a 0")
    descuento_bs = round(_a_float(descuento_bs), 2)
    total_bs = round(max((subtotal_usd * tasa_cobro) - descuento_bs, 0.0), 2)
    total_usd = round((total_bs / tasa_cobro) if tasa_cobro else 0.0, 2)

    return {
        "subtotal_usd": subtotal_usd,
        "tasa_cobro": tasa_cobro,
        "descuento_bs": descuento_bs,
        "total_usd": total_usd,
        "total_bs": total_bs,
    }


def calcular_totales_financieros_delivery(items, tasa, descuento_bs, delivery_usd):
    tasa_cobro = _a_float(tasa)
    if tasa_cobro <= 0:
        raise ValueError("La tasa de cobro debe ser mayor a 0")

    descuento_bs = round(_a_float(descuento_bs), 2)
    delivery_explicit = round(_a_float(delivery_usd), 2)
    if delivery_explicit < 0:
        raise ValueError("El monto de delivery no puede ser negativo")

    subtotal_restaurante_usd = 0.0
    delivery_legacy_usd = 0.0
    for item in items:
        producto = item[0]
        precio = _a_float(item[1])
        categoria = item[2] if len(item) > 2 else None
        if es_producto_delivery_legacy(producto, categoria):
            delivery_legacy_usd += precio
        else:
            subtotal_restaurante_usd += precio

    subtotal_restaurante_usd = round(subtotal_restaurante_usd, 2)
    delivery_legacy_usd = round(delivery_legacy_usd, 2)
    tiene_delivery_legacy = delivery_legacy_usd > TOLERANCIA_COBRO

    if tiene_delivery_legacy:
        if delivery_explicit > TOLERANCIA_COBRO:
            raise ValueError("Esta orden contiene delivery legacy y delivery explicito. Corrige la orden antes de cobrar.")
        precios_legacy = [item[1] for item in items]
        totales_legacy = calcular_totales_cobro(precios_legacy, tasa_cobro, descuento_bs)
        return {
            "modo": "legacy",
            "tasa": tasa_cobro,
            "subtotal_restaurante_usd": totales_legacy["subtotal_usd"],
            "descuento_bs": totales_legacy["descuento_bs"],
            "venta_restaurante_usd": totales_legacy["total_usd"],
            "delivery_usd": 0.0,
            "delivery_legacy_usd": delivery_legacy_usd,
            "total_cliente_usd": totales_legacy["total_usd"],
            "venta_restaurante_bs": totales_legacy["total_bs"],
            "delivery_bs": 0.0,
            "total_cliente_bs": totales_legacy["total_bs"],
            "subtotal_snapshot_usd": totales_legacy["subtotal_usd"],
            "total_usd": totales_legacy["total_usd"],
            "total_bs": totales_legacy["total_bs"],
            "snapshot_delivery_usd": None,
            "snapshot_venta_restaurante_usd": None,
            "snapshot_total_cliente_usd": None,
        }

    subtotal_restaurante_bs = round(subtotal_restaurante_usd * tasa_cobro, 2)
    venta_restaurante_bs = round(max(subtotal_restaurante_bs - descuento_bs, 0.0), 2)
    venta_restaurante_usd = round((venta_restaurante_bs / tasa_cobro) if tasa_cobro else 0.0, 2)
    delivery_bs = round(delivery_explicit * tasa_cobro, 2)
    total_cliente_bs = round(venta_restaurante_bs + delivery_bs, 2)
    total_cliente_usd = round(venta_restaurante_usd + delivery_explicit, 2)

    return {
        "modo": "explicito",
        "tasa": tasa_cobro,
        "subtotal_restaurante_usd": subtotal_restaurante_usd,
        "descuento_bs": descuento_bs,
        "venta_restaurante_usd": venta_restaurante_usd,
        "delivery_usd": delivery_explicit,
        "delivery_legacy_usd": 0.0,
        "total_cliente_usd": total_cliente_usd,
        "venta_restaurante_bs": venta_restaurante_bs,
        "delivery_bs": delivery_bs,
        "total_cliente_bs": total_cliente_bs,
        "subtotal_snapshot_usd": subtotal_restaurante_usd,
        "total_usd": venta_restaurante_usd,
        "total_bs": venta_restaurante_bs,
        "snapshot_delivery_usd": delivery_explicit,
        "snapshot_venta_restaurante_usd": venta_restaurante_usd,
        "snapshot_total_cliente_usd": total_cliente_usd,
    }
