"""
descripcion.py (dominio CxC)

Texto descriptivo de una cuenta por cobrar, DERIVADO de datos que ya
se persisten en la venta origen (ordenes.tipo/referencia/observacion y
los nombres historicos de orden_items.producto). No se guarda nada
nuevo: `cuentas_por_cobrar.observacion` solo contiene un texto fijo de
creacion, asi que la descripcion util sale de la orden. Modulo puro.
"""

_ETIQUETAS_TIPO = {
    "mesa": "Mesa",
    "delivery": "Delivery",
    "para llevar": "Pick Up",
}


def etiqueta_tipo_orden(tipo):
    texto = (tipo or "").strip()
    return _ETIQUETAS_TIPO.get(texto.lower(), texto)


def agrupar_productos(nombres):
    """[(nombre, cantidad)] en orden de primera aparicion."""
    conteo = {}
    for nombre in nombres:
        nombre = (nombre or "").strip()
        if nombre:
            conteo[nombre] = conteo.get(nombre, 0) + 1
    return list(conteo.items())


def texto_productos(productos, max_productos=None):
    if not productos:
        return ""
    visibles = productos if max_productos is None else productos[:max_productos]
    texto = ", ".join(f"{cantidad}× {nombre}" for nombre, cantidad in visibles)
    restantes = len(productos) - len(visibles)
    if restantes > 0:
        texto += f" +{restantes} más"
    return texto


def texto_descripcion_cxc(tipo, referencia, observacion, productos, max_productos=3):
    """Ej.: "Mesa · Mesa 4 — 2× Neko Combo 1, 1× Cerveza Polar · Obs: sin picante".
    `productos` = salida de agrupar_productos."""
    contexto = " · ".join(
        parte
        for parte in (etiqueta_tipo_orden(tipo), (referencia or "").strip())
        if parte and parte != "-"
    )
    partes = []
    if contexto:
        partes.append(contexto)
    lista = texto_productos(productos, max_productos)
    if lista:
        partes.append(lista)
    texto = " — ".join(partes)
    obs = (observacion or "").strip()
    if obs and obs != "-":
        texto = f"{texto} · Obs: {obs}" if texto else f"Obs: {obs}"
    return texto or "Sin detalle de la venta"
