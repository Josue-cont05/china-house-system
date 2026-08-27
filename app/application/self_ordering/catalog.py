from dataclasses import dataclass
from typing import Protocol

from app.domain.sales.calculations import es_producto_delivery_legacy
from app.domain.sales.item_builder import es_producto_refresco


@dataclass(frozen=True)
class OpcionCatalogo:
    titulo: str
    valores: tuple[str, ...]
    requeridas: int
    maximas: int
    opcional: bool = False
    ayuda: str = ""
    precios_adicionales_centavos: dict[str, int] | None = None


@dataclass(frozen=True)
class ProductoCatalogo:
    id: int
    nombre: str
    precio: float
    categoria: str
    categoria_publica: str
    descripcion: str
    tipo_configuracion: str
    opciones: tuple[OpcionCatalogo, ...]


@dataclass(frozen=True)
class CategoriaCatalogo:
    nombre: str
    productos: tuple[ProductoCatalogo, ...]


@dataclass(frozen=True)
class ProductoFueraCatalogo:
    id: int
    nombre: str
    categoria: str
    motivo: str


@dataclass(frozen=True)
class CatalogoSelfOrdering:
    categorias: tuple[CategoriaCatalogo, ...]
    productos_fuera: tuple[ProductoFueraCatalogo, ...] = ()


@dataclass(frozen=True)
class ReglasCatalogoSelfOrdering:
    orden_categorias: tuple[str, ...]
    combos_personales: dict
    acompanantes_combo: tuple[str, ...]
    bebidas_combo: tuple[str, ...]
    combos_cantidad_acompanantes: dict
    promociones_neko: dict
    promociones_con_pollo: frozenset[str]
    pollos_promocion: tuple[str, ...]
    arroces_promocion: tuple[str, ...]
    sabores_refresco: tuple[str, ...]
    promo_extra_lumpias_nombre: str
    promo_extra_lumpias_precio: float


class CatalogoRepository(Protocol):
    def listar_productos_publicos(self) -> list[tuple]:
        ...


PUBLIC_CATEGORIES = (
    "Combos personales",
    "Arroz chino",
    "Promociones",
    "Bebidas",
)


def construir_catalogo_self_ordering(
    repository: CatalogoRepository,
    reglas: ReglasCatalogoSelfOrdering,
) -> CatalogoSelfOrdering:
    categorias = {nombre: [] for nombre in PUBLIC_CATEGORIES}
    productos_fuera = []
    for producto_id, nombre, precio, categoria in repository.listar_productos_publicos():
        categoria_nombre = categoria or "Sin categoria"
        if es_producto_delivery_legacy(nombre, categoria_nombre):
            continue

        categoria_publica = _categoria_publica(nombre, categoria_nombre, reglas)
        if not categoria_publica:
            productos_fuera.append(
                ProductoFueraCatalogo(
                    id=producto_id,
                    nombre=nombre,
                    categoria=categoria_nombre,
                    motivo="No pertenece a una categoria publica Self-Ordering definida.",
                )
            )
            continue

        producto = ProductoCatalogo(
            id=producto_id,
            nombre=nombre,
            precio=float(precio or 0),
            categoria=categoria_nombre,
            categoria_publica=categoria_publica,
            descripcion=_descripcion_producto(nombre, categoria_nombre, reglas),
            tipo_configuracion=_tipo_configuracion(nombre, reglas),
            opciones=_opciones_producto(nombre, reglas),
        )
        categorias[categoria_publica].append(producto)

    return CatalogoSelfOrdering(
        categorias=tuple(
            CategoriaCatalogo(nombre=nombre, productos=tuple(productos))
            for nombre, productos in categorias.items()
        ),
        productos_fuera=tuple(productos_fuera),
    )


def _categoria_publica(nombre, categoria, reglas):
    categoria_limpia = (categoria or "").lower()
    if nombre in reglas.combos_personales:
        return "Combos personales"
    if nombre in reglas.promociones_neko:
        return "Promociones"
    if es_producto_refresco(nombre):
        return "Bebidas"
    if categoria_limpia in {"neko clan", "neko duo", "neko dúo"}:
        return "Arroz chino"
    return None


def _tipo_configuracion(nombre, reglas):
    if es_producto_refresco(nombre):
        return "refresco"
    if nombre in reglas.combos_personales:
        return "combo"
    if nombre in reglas.promociones_neko:
        return "promocion"
    return "simple"


def _descripcion_producto(nombre, categoria, reglas):
    if nombre in reglas.combos_personales:
        cantidad = reglas.combos_cantidad_acompanantes.get(nombre, 1)
        acompanantes = "acompanante" if cantidad == 1 else "acompanantes"
        return f"Arroz chino con {cantidad} {acompanantes} y bebida."

    if nombre in reglas.promociones_neko:
        promo = reglas.promociones_neko[nombre]
        arroces = promo.get("cantidad_arroces", 0)
        refrescos = promo.get("cantidad_refrescos", 0)
        if nombre in reglas.promociones_con_pollo:
            return "Promocion familiar con pollo, arroz y refresco."
        if arroces == 2 or refrescos == 2:
            return f"Promocion para compartir con {arroces} arroces y {refrescos} refrescos."
        return "Promocion para compartir con arroz y refresco."

    if es_producto_refresco(nombre):
        return "Elige tu sabor."

    if _categoria_publica(nombre, categoria, reglas) == "Arroz chino":
        return "Arroz chino preparado para compartir."

    return "Producto disponible para autoservicio."


def _opciones_producto(nombre, reglas):
    if es_producto_refresco(nombre):
        return (
            OpcionCatalogo(
                titulo="Sabores",
                valores=reglas.sabores_refresco,
                requeridas=1,
                maximas=1,
            ),
        )

    if nombre in reglas.combos_personales:
        cantidad_acompanantes = reglas.combos_cantidad_acompanantes.get(nombre, 1)
        return (
            OpcionCatalogo(
                titulo="Acompanantes",
                valores=reglas.acompanantes_combo,
                requeridas=cantidad_acompanantes,
                maximas=cantidad_acompanantes,
            ),
            OpcionCatalogo(
                titulo="Bebidas",
                valores=reglas.bebidas_combo,
                requeridas=1,
                maximas=1,
            ),
        )

    if nombre in reglas.promociones_neko:
        promo = reglas.promociones_neko[nombre]
        opciones = [
            OpcionCatalogo(
                titulo="Arroces",
                valores=reglas.arroces_promocion,
                requeridas=promo["cantidad_arroces"],
                maximas=promo["cantidad_arroces"],
            ),
            OpcionCatalogo(
                titulo="Sabores",
                valores=reglas.sabores_refresco,
                requeridas=promo["cantidad_refrescos"],
                maximas=promo["cantidad_refrescos"],
                ayuda=f"Incluye: {promo.get('refresco', '')}",
            ),
        ]
        if nombre in reglas.promociones_con_pollo:
            opciones.insert(
                0,
                OpcionCatalogo(
                    titulo="Pollos",
                    valores=reglas.pollos_promocion,
                    requeridas=1,
                    maximas=1,
                ),
            )
            opciones.append(
                OpcionCatalogo(
                    titulo="Extra",
                    valores=(reglas.promo_extra_lumpias_nombre,),
                    requeridas=0,
                    maximas=1,
                    opcional=True,
                    precios_adicionales_centavos={
                        reglas.promo_extra_lumpias_nombre: _centavos(
                            reglas.promo_extra_lumpias_precio
                        )
                    },
                )
            )
        return tuple(opciones)

    return ()


def _centavos(monto):
    return int(round(float(monto or 0) * 100))
