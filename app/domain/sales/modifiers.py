"""
modifiers.py (dominio)

Sistema GENERAL de grupos de modificadores/opciones para productos
(caso inicial: Jugo Natural -> grupo "Sabor" + grupo "Azucar", pero
sirve para cualquier producto sin tocar codigo Python -- a diferencia
de COMBOS_PERSONALES/PROMOCIONES_NEKO en web_app.py, que son
diccionarios hardcodeados). Los grupos y opciones viven en BD
(app.infrastructure.database.modifiers) y se administran desde el
modulo Menu; este modulo solo valida una seleccion contra las reglas
de un grupo (requerido/opcional, seleccion unica/multiple, min/max,
activo/disponible) y es puro: no toca BD ni Flask.

La seleccion validada se serializa en `orden_items.indicacion` con el
MISMO protocolo JSON versionado que ya usan combos/promociones
(app.domain.sales.item_descriptions.serializar_indicacion), asi que
hereda gratis persistencia a traves de cocina/factura/edicion/checkout/
historico sin tocar ninguna de esas capas.
"""

from dataclasses import dataclass

from app.domain.sales.item_builder import ErrorConstruccionItem


@dataclass(frozen=True)
class OpcionModificador:
    id: int
    nombre: str
    activa: bool
    disponible: bool
    precio_adicional: float
    orden: int


@dataclass(frozen=True)
class GrupoModificador:
    id: int
    nombre: str
    activo: bool
    obligatorio: bool
    seleccion_multiple: bool
    minimo: int
    maximo: int
    orden: int
    opciones: tuple  # tuple[OpcionModificador, ...]


def validar_seleccion_modificadores(grupos, seleccion):
    """`grupos`: iterable de GrupoModificador (ya filtrados a los
    asociados al producto). `seleccion`: dict {grupo_id: [nombre_opcion, ...]}.

    Devuelve (grupos_resultado, precio_adicional_total):
    - grupos_resultado: lista de {"grupo_id", "nombre", "opciones": [...]}
      lista para guardar en la indicacion JSON (solo grupos con alguna
      opcion elegida; un grupo inactivo se ignora por completo, nunca
      se exige ni se guarda).
    - precio_adicional_total: suma de precio_adicional de las opciones
      elegidas, redondeado a 2 decimales.

    Levanta ErrorConstruccionItem (mismo tipo que ya usa
    construir_items_orden, para que la ruta /agregar_con_modificadores
    reutilice el manejo de errores existente) si: un grupo obligatorio
    no cumple su minimo, se excede el maximo, se elige una opcion que
    no existe/esta inactiva, o la opcion esta agotada."""
    grupos_resultado = []
    precio_adicional_total = 0.0

    for grupo in grupos:
        if not grupo.activo:
            continue

        valores = seleccion.get(grupo.id, [])
        if not isinstance(valores, (list, tuple)):
            valores = [valores] if valores else []
        valores = [str(v).strip() for v in valores if str(v).strip()]

        if grupo.obligatorio and len(valores) < grupo.minimo:
            raise ErrorConstruccionItem(f"Debes seleccionar {grupo.nombre}.")
        if len(valores) > grupo.maximo:
            raise ErrorConstruccionItem(
                f"Maximo {grupo.maximo} opcion(es) permitidas para {grupo.nombre}."
            )
        if not grupo.seleccion_multiple and len(valores) > 1:
            raise ErrorConstruccionItem(f"{grupo.nombre} solo admite una opcion.")

        opciones_activas = {o.nombre: o for o in grupo.opciones if o.activa}
        elegidas = []
        for valor in valores:
            opcion = opciones_activas.get(valor)
            if not opcion:
                raise ErrorConstruccionItem(f"Opcion invalida para {grupo.nombre}.")
            if not opcion.disponible:
                raise ErrorConstruccionItem(f"{opcion.nombre} esta agotado.")
            elegidas.append(opcion.nombre)
            precio_adicional_total += opcion.precio_adicional

        if elegidas:
            grupos_resultado.append(
                {"grupo_id": grupo.id, "nombre": grupo.nombre, "opciones": elegidas}
            )

    return grupos_resultado, round(precio_adicional_total, 2)


def producto_agotado_por_modificadores(grupos):
    """True si el producto NO se puede vender ahora mismo porque algun
    grupo activo y obligatorio (minimo >= 1) no tiene ninguna opcion
    activa y disponible: validar_seleccion_modificadores rechazaria
    cualquier intento de agregarlo. No es una regla nueva -- solo
    anticipa en la UI (badge AGOTADO) lo que el backend ya impone."""
    for grupo in grupos or ():
        if not grupo.activo or not grupo.obligatorio or grupo.minimo < 1:
            continue
        if not any(o.activa and o.disponible for o in grupo.opciones):
            return True
    return False
