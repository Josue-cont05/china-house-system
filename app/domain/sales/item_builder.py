from dataclasses import dataclass

from app.domain.sales.calculations import TOLERANCIA_COBRO, es_producto_delivery_legacy
from app.domain.sales.item_descriptions import (
    COMBOS_JSON,
    PROMOCIONES_JSON,
    normalizar_indicacion_item,
    serializar_indicacion,
)
from app.shared.constants.system import SABORES_REFRESCO


@dataclass(frozen=True)
class ItemOrdenConstruido:
    producto: str
    precio: float
    indicacion: str


@dataclass(frozen=True)
class ConstruccionItemsOrden:
    item_principal: ItemOrdenConstruido
    items_extra: tuple[ItemOrdenConstruido, ...] = ()

    @property
    def items(self):
        return (self.item_principal,) + self.items_extra

    @property
    def precio_total(self):
        return round(sum(item.precio for item in self.items), 2)


class ErrorConstruccionItem(ValueError):
    def __init__(self, mensaje, status_code=200):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


def normalizar_sabor_refresco(sabor):
    sabor_limpio = (sabor or "").strip()
    if not sabor_limpio or len(sabor_limpio) > 40:
        return ""

    for opcion in SABORES_REFRESCO:
        if sabor_limpio.lower() == opcion.lower():
            return opcion

    sabor_limpio = sabor_limpio.replace("<", "").replace(">", "")
    return sabor_limpio.strip()


def es_producto_refresco(nombre):
    return "refresco" in (nombre or "").lower()


def construir_items_orden(
    *,
    producto_nombre,
    producto_precio,
    categoria_nombre=None,
    delivery_actual=0,
    sabor=None,
    acompanantes=None,
    bebida=None,
    pollo=None,
    arroces=None,
    sabores=None,
    extra_lumpias="0",
    combos_personales=None,
    acompanantes_combo=None,
    bebidas_combo=None,
    combos_cantidad_acompanantes=None,
    promociones_neko=None,
    promociones_con_pollo=None,
    pollos_promocion=None,
    arroces_promocion=None,
    promo_extra_lumpias_nombre="Promo extra: Ración de Lumpias",
    promo_extra_lumpias_precio=3.00,
):
    producto_nombre_original = producto_nombre or ""
    producto_nombre = producto_nombre_original.strip()
    categoria_nombre = (categoria_nombre or "").strip()
    combos_personales = combos_personales or {}
    acompanantes_combo = acompanantes_combo or []
    bebidas_combo = bebidas_combo or []
    combos_cantidad_acompanantes = combos_cantidad_acompanantes or {}
    promociones_neko = promociones_neko or {}
    promociones_con_pollo = promociones_con_pollo or set()
    pollos_promocion = pollos_promocion or []
    arroces_promocion = arroces_promocion or []
    acompanantes = [(valor or "").strip() for valor in (acompanantes or [])]
    arroces = [(valor or "").strip() for valor in (arroces or [])]
    sabores = list(sabores or [])
    extra_lumpias = (extra_lumpias or "0").strip()

    if es_producto_delivery_legacy(producto_nombre, categoria_nombre):
        raise ErrorConstruccionItem(
            "El delivery ahora se registra desde el campo Delivery de la orden.",
            status_code=400,
        )

    try:
        delivery_actual_num = float(delivery_actual or 0)
    except (TypeError, ValueError):
        delivery_actual_num = 0

    if delivery_actual_num > TOLERANCIA_COBRO and es_producto_delivery_legacy(
        producto_nombre,
        categoria_nombre,
    ):
        raise ErrorConstruccionItem(
            "Esta orden ya tiene delivery explícito configurado.",
            status_code=400,
        )

    indicacion = ""
    if es_producto_refresco(producto_nombre):
        sabor_normalizado = normalizar_sabor_refresco(sabor)
        if not sabor_normalizado:
            raise ErrorConstruccionItem("Debes seleccionar un sabor valido para el refresco")
        indicacion = f"Sabor: {sabor_normalizado}"
    elif producto_nombre in combos_personales:
        cantidad_acompanantes = combos_cantidad_acompanantes.get(producto_nombre, 1)
        bebida = (bebida or "").strip()
        if len(acompanantes) != cantidad_acompanantes or any(
            acompanante not in acompanantes_combo for acompanante in acompanantes
        ):
            raise ErrorConstruccionItem(
                "Debes seleccionar todos los acompañantes validos para este combo"
            )
        if bebida not in bebidas_combo:
            raise ErrorConstruccionItem("Debes seleccionar una bebida valida para este combo")
        indicacion = serializar_indicacion(
            {
                "version": 1,
                "tipo": "combo",
                "producto": COMBOS_JSON[producto_nombre],
                "acompanantes": acompanantes,
                "bebida": bebida,
            }
        )
    elif producto_nombre in promociones_neko:
        promo = promociones_neko[producto_nombre]
        pollo = (pollo or "").strip()
        requiere_pollo = producto_nombre in promociones_con_pollo
        if requiere_pollo and pollo not in pollos_promocion:
            raise ErrorConstruccionItem(
                "Debes seleccionar un tipo de pollo valido para esta promocion"
            )
        if len(arroces) != promo["cantidad_arroces"] or any(
            arroz not in arroces_promocion for arroz in arroces
        ):
            raise ErrorConstruccionItem(
                "Debes seleccionar todos los arroces validos para esta promocion"
            )
        sabores_normalizados = [normalizar_sabor_refresco(valor) for valor in sabores]
        if len(sabores_normalizados) != promo["cantidad_refrescos"] or any(
            not sabor_normalizado for sabor_normalizado in sabores_normalizados
        ):
            raise ErrorConstruccionItem("Debes seleccionar todos los sabores de refresco")
        if extra_lumpias not in {"0", "1"}:
            raise ErrorConstruccionItem("La selecci\u00f3n del extra de lumpias no es valida")
        datos_promocion = {
            "version": 1,
            "tipo": "promocion",
            "producto": PROMOCIONES_JSON[producto_nombre],
            "arroces": arroces,
            "bebidas": sabores_normalizados,
        }
        if requiere_pollo:
            datos_promocion["pollo"] = pollo
        indicacion = serializar_indicacion(datos_promocion)

    item_principal = ItemOrdenConstruido(
        producto=producto_nombre_original,
        precio=producto_precio,
        indicacion=normalizar_indicacion_item(indicacion),
    )
    items_extra = []
    if producto_nombre in promociones_neko and extra_lumpias == "1":
        items_extra.append(
            ItemOrdenConstruido(
                producto=promo_extra_lumpias_nombre,
                precio=promo_extra_lumpias_precio,
                indicacion=normalizar_indicacion_item(f"Agregado con: {producto_nombre}"),
            )
        )

    return ConstruccionItemsOrden(item_principal, tuple(items_extra))
