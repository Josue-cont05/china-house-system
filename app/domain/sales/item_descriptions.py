import json
import re


COMBOS_JSON = {
    "Neko Combo 1": "combo1",
    "Neko Combo 2": "combo2",
    "Neko Combo 3": "combo3",
}

PROMOCIONES_JSON = {
    "Wok para Dos": "wok_para_dos",
    "Familiar": "familiar",
    "Mega Familiar": "mega_familiar",
}

NOMBRES_COCINA_SIMPLIFICADOS = {
    "Neko Combo 1": "COMBO #1",
    "Neko Combo 2": "COMBO #2",
    "Neko Combo 3": "COMBO #3",
    "Wok para Dos": "WOK PARA DOS",
    "Familiar": "FAMILIAR",
    "Mega Familiar": "MEGA FAMILIAR",
}


def normalizar_indicacion_item(indicacion):
    indicacion = (indicacion or "").strip()
    indicacion = re.sub(r"\s+", " ", indicacion)
    return indicacion[:500]


def deserializar_indicacion(indicacion):
    texto = (indicacion or "").strip()
    if not texto or not texto.startswith("{"):
        return None
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    if datos.get("version") != 1:
        return None
    return datos


def es_indicacion_json(indicacion):
    return deserializar_indicacion(indicacion) is not None


def serializar_indicacion(datos):
    if not isinstance(datos, dict):
        return ""
    datos = dict(datos)
    datos.setdefault("version", 1)
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def quitar_prefijo_cantidad_visual(texto):
    texto = (texto or "").strip()

    while True:
        limpio = re.sub(r"^1x\s+(\d+x\s+.+)$", r"\1", texto, flags=re.IGNORECASE)
        if limpio == texto:
            return texto
        texto = limpio.strip()


def _separar_prefijo_cantidad(producto):
    producto = quitar_prefijo_cantidad_visual(producto)
    match = re.match(r"^(\d+)x\s+(.+)$", producto, flags=re.IGNORECASE)
    if not match:
        return 1, producto

    cantidad = int(match.group(1))
    producto_limpio = match.group(2).strip()
    return max(cantidad, 1), producto_limpio


def producto_sin_prefijo_cantidad(producto):
    _, producto_limpio = _separar_prefijo_cantidad(producto)
    return producto_limpio


def datos_combo_desde_indicacion(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    datos = deserializar_indicacion(indicacion)
    if not datos or datos.get("tipo") != "combo":
        return None
    if COMBOS_JSON.get(producto) != datos.get("producto"):
        return None
    acompanantes = datos.get("acompanantes")
    bebida = datos.get("bebida")
    if not isinstance(acompanantes, list) or not isinstance(bebida, str):
        return None
    lineas = [str(valor).strip() for valor in acompanantes if str(valor).strip()]
    bebida = bebida.strip()
    if bebida:
        lineas.append(bebida)
    nota = (datos.get("nota") or "").strip()
    if nota:
        lineas.append(f"Nota: {nota}")
    if not lineas:
        return None
    return {"datos": datos, "lineas": lineas}


def datos_promocion_desde_indicacion(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    datos = deserializar_indicacion(indicacion)
    if not datos or datos.get("tipo") != "promocion":
        return None
    if PROMOCIONES_JSON.get(producto) != datos.get("producto"):
        return None
    pollo = datos.get("pollo")
    arroces = datos.get("arroces")
    bebidas = datos.get("bebidas")
    if pollo is not None and not isinstance(pollo, str):
        return None
    if not isinstance(arroces, list) or not isinstance(bebidas, list):
        return None
    lineas = []
    pollo = (pollo or "").strip()
    if pollo:
        lineas.append(pollo)
    lineas.extend(f"Arroz {str(arroz).strip()}" for arroz in arroces if str(arroz).strip())
    lineas.extend(str(bebida).strip() for bebida in bebidas if str(bebida).strip())
    nota = (datos.get("nota") or "").strip()
    if nota:
        lineas.append(f"Nota: {nota}")
    if not lineas:
        return None
    return {"datos": datos, "lineas": lineas}


def texto_descripcion_combo_orden(producto, indicacion):
    combo = datos_combo_desde_indicacion(producto, indicacion)
    if not combo:
        return ""
    return "\n".join(f"• {linea}" for linea in combo["lineas"])


def texto_descripcion_combo_cocina(producto, indicacion):
    combo = datos_combo_desde_indicacion(producto, indicacion)
    if not combo:
        return ""
    datos = combo["datos"]
    lineas = [
        f"    - {str(acompanante).strip()}"
        for acompanante in datos.get("acompanantes", [])
        if str(acompanante).strip()
    ]
    bebida = (datos.get("bebida") or "").strip()
    if bebida:
        lineas.append(f"    [{bebida}]")
    nota = (datos.get("nota") or "").strip()
    if nota:
        lineas.append(f"    Nota: {nota}")
    return "\n".join(lineas)


def texto_descripcion_combo_factura(producto, indicacion):
    combo = datos_combo_desde_indicacion(producto, indicacion)
    if not combo:
        return ""
    return "\n".join(f"• {linea}" for linea in combo["lineas"])


def texto_descripcion_promocion_orden(producto, indicacion):
    promocion = datos_promocion_desde_indicacion(producto, indicacion)
    if not promocion:
        return ""
    return "\n".join(f"• {linea}" for linea in promocion["lineas"])


def texto_descripcion_promocion_cocina(producto, indicacion):
    promocion = datos_promocion_desde_indicacion(producto, indicacion)
    if not promocion:
        return ""
    datos = promocion["datos"]
    lineas = []
    pollo = (datos.get("pollo") or "").strip()
    if pollo:
        lineas.append(f"    - {pollo}")
    lineas.extend(
        f"    - Arroz {str(arroz).strip()}"
        for arroz in datos.get("arroces", [])
        if str(arroz).strip()
    )
    lineas.extend(
        f"    [{str(bebida).strip()}]"
        for bebida in datos.get("bebidas", [])
        if str(bebida).strip()
    )
    nota = (datos.get("nota") or "").strip()
    if nota:
        lineas.append(f"    Nota: {nota}")
    return "\n".join(lineas)


def texto_descripcion_promocion_factura(producto, indicacion):
    promocion = datos_promocion_desde_indicacion(producto, indicacion)
    if not promocion:
        return ""
    return "\n".join(f"• {linea}" for linea in promocion["lineas"])


def texto_item_con_indicacion(producto, indicacion):
    producto = producto_sin_prefijo_cantidad(producto)
    indicacion = normalizar_indicacion_item(indicacion)
    if indicacion:
        return f"{producto} ({indicacion})"
    return producto


def nombre_producto_cocina(producto):
    producto = producto_sin_prefijo_cantidad(producto)
    return NOMBRES_COCINA_SIMPLIFICADOS.get(producto, producto)
