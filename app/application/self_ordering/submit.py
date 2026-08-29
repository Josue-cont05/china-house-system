import datetime
import json
import re
from dataclasses import dataclass
from typing import Optional, Protocol

import pytz

from app.application.self_ordering.catalog import construir_catalogo_self_ordering
from app.application.self_ordering.links import (
    ESTADO_LINK_ACTIVO,
    ESTADO_MESA_NO_HABILITADA,
    ResultadoValidacionLink,
    validar_self_order_link_para_catalogo,
)
from app.domain.sales.item_descriptions import (
    deserializar_indicacion,
    normalizar_indicacion_item,
    serializar_indicacion,
)
from app.domain.sales.item_builder import ErrorConstruccionItem, construir_items_orden


MAX_ITEMS_ENVIO = 20
MAX_CANTIDAD_LINEA = 12
MAX_INDICACION = 180
MAX_SUBMISSION_ID = 80
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"
VENEZUELA_TZ = pytz.timezone("America/Caracas")
SUBMISSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")


class ErrorSubmitSelfOrdering(ValueError):
    def __init__(self, mensaje, status_code=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


@dataclass(frozen=True)
class OrdenItemPreparado:
    producto: str
    precio: float
    indicacion: str


@dataclass(frozen=True)
class RequestItemPreparado:
    producto_id: int
    producto_nombre_snapshot: str
    precio_unitario_snapshot: float
    cantidad: int
    indicacion: str
    configuracion_json: str
    subtotal_usd: float


@dataclass(frozen=True)
class ResultadoSubmitSelfOrdering:
    request_id: int
    estado: str
    total_usd: float
    items: tuple[RequestItemPreparado, ...]
    idempotente: bool = False
    comanda_id: int | None = None
    comanda_secuencia: int | None = None
    numero_orden: int | None = None


class SubmitSelfOrderingRepository(Protocol):
    def buscar_por_token(self, token: str):
        ...

    def obtener_producto_catalogo(self, producto_id: int, orden_id: int) -> Optional[tuple]:
        ...

    def guardar_submit_atomico(
        self,
        *,
        token: str,
        link_id: int,
        orden_id: int,
        canal: str,
        submission_id: str,
        fecha: str,
        request_items: tuple[RequestItemPreparado, ...],
        orden_items: tuple[OrdenItemPreparado, ...],
    ) -> ResultadoSubmitSelfOrdering:
        ...


def procesar_submit_self_ordering(
    *,
    repository: SubmitSelfOrderingRepository,
    catalog_repository,
    reglas,
    token: str,
    payload: dict,
    ahora_fn=None,
) -> ResultadoSubmitSelfOrdering:
    resultado_link = validar_self_order_link_para_catalogo(repository, token, ahora_fn=ahora_fn)
    _validar_link_destino(resultado_link)
    link = resultado_link.link

    submission_id = _validar_submission_id(payload.get("submission_id"))
    if not isinstance(payload, dict):
        raise ErrorSubmitSelfOrdering("Payload invalido.", 400)

    lineas_payload = _validar_items_payload(payload.get("items"))
    productos_permitidos = _productos_catalogo_permitidos(catalog_repository, reglas)

    request_items = []
    orden_items = []
    for linea in lineas_payload:
        producto_id = _validar_producto_id(linea.get("producto_id"))
        cantidad = _validar_cantidad(linea.get("cantidad"))
        indicacion = _validar_indicacion(linea.get("indicacion", ""))
        configuracion = _normalizar_configuracion(linea.get("configuracion"))

        producto = repository.obtener_producto_catalogo(producto_id, link.orden_id)
        if producto is None:
            raise ErrorSubmitSelfOrdering("Producto no disponible para autoservicio.", 400)
        nombre, precio, categoria, producto_activo, categoria_activa, delivery_actual = producto
        if int(producto_activo or 0) != 1 or int(categoria_activa or 0) != 1:
            raise ErrorSubmitSelfOrdering("Producto no disponible para autoservicio.", 400)
        producto_catalogo = productos_permitidos.get(producto_id)
        if producto_catalogo is None:
            raise ErrorSubmitSelfOrdering("Producto no permitido en autoservicio.", 400)

        _validar_configuracion_contrato(configuracion, producto_catalogo.opciones)
        args_builder = _configuracion_a_builder_args(nombre, configuracion, reglas)
        try:
            construidos = construir_items_orden(
                producto_nombre=nombre,
                producto_precio=float(precio or 0),
                categoria_nombre=categoria,
                delivery_actual=delivery_actual,
                combos_personales=reglas.combos_personales,
                acompanantes_combo=reglas.acompanantes_combo,
                bebidas_combo=reglas.bebidas_combo,
                combos_cantidad_acompanantes=reglas.combos_cantidad_acompanantes,
                promociones_neko=reglas.promociones_neko,
                promociones_con_pollo=reglas.promociones_con_pollo,
                pollos_promocion=reglas.pollos_promocion,
                arroces_promocion=reglas.arroces_promocion,
                promo_extra_lumpias_nombre=reglas.promo_extra_lumpias_nombre,
                promo_extra_lumpias_precio=reglas.promo_extra_lumpias_precio,
                **args_builder,
            )
        except ErrorConstruccionItem as exc:
            raise ErrorSubmitSelfOrdering(exc.mensaje, 400) from exc

        configuracion_json = _serializar_configuracion(configuracion)
        precio_unitario = construidos.precio_total
        request_items.append(
            RequestItemPreparado(
                producto_id=producto_id,
                producto_nombre_snapshot=nombre,
                precio_unitario_snapshot=precio_unitario,
                cantidad=cantidad,
                indicacion=indicacion,
                configuracion_json=configuracion_json,
                subtotal_usd=round(precio_unitario * cantidad, 2),
            )
        )
        for _ in range(cantidad):
            for item in construidos.items:
                orden_items.append(
                    OrdenItemPreparado(
                        producto=item.producto,
                        precio=item.precio,
                        indicacion=_combinar_indicacion_cliente(item.indicacion, indicacion),
                    )
                )

    return repository.guardar_submit_atomico(
        token=token,
        link_id=link.id,
        orden_id=link.orden_id,
        canal=link.canal,
        submission_id=submission_id,
        fecha=_formatear_fecha(_ahora(ahora_fn)),
        request_items=tuple(request_items),
        orden_items=tuple(orden_items),
    )


def _validar_link_destino(resultado: ResultadoValidacionLink):
    if resultado.estado == ESTADO_MESA_NO_HABILITADA:
        raise ErrorSubmitSelfOrdering("Mesa no habilitada para autoservicio.", 409)
    if not resultado.valido or resultado.link is None:
        raise ErrorSubmitSelfOrdering("Enlace no disponible.", 404)
    if resultado.link.estado != ESTADO_LINK_ACTIVO or resultado.link.canal != "mesa":
        raise ErrorSubmitSelfOrdering("Enlace no disponible.", 404)
    if resultado.link.orden_id is None:
        raise ErrorSubmitSelfOrdering("Mesa no habilitada para autoservicio.", 409)


def _validar_submission_id(valor) -> str:
    texto = str(valor or "").strip()
    if not texto or len(texto) > MAX_SUBMISSION_ID or not SUBMISSION_ID_RE.match(texto):
        raise ErrorSubmitSelfOrdering("Identificador de envio invalido.", 400)
    return texto


def _validar_items_payload(items) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise ErrorSubmitSelfOrdering("El pedido no contiene items.", 400)
    if len(items) > MAX_ITEMS_ENVIO:
        raise ErrorSubmitSelfOrdering("El pedido excede el limite de items.", 400)
    if not all(isinstance(item, dict) for item in items):
        raise ErrorSubmitSelfOrdering("Formato de items invalido.", 400)
    return items


def _validar_producto_id(valor) -> int:
    try:
        producto_id = int(valor)
    except (TypeError, ValueError):
        raise ErrorSubmitSelfOrdering("Producto invalido.", 400)
    if producto_id <= 0:
        raise ErrorSubmitSelfOrdering("Producto invalido.", 400)
    return producto_id


def _validar_cantidad(valor) -> int:
    try:
        cantidad = int(valor)
    except (TypeError, ValueError):
        raise ErrorSubmitSelfOrdering("Cantidad invalida.", 400)
    if cantidad <= 0:
        raise ErrorSubmitSelfOrdering("Cantidad invalida.", 400)
    if cantidad > MAX_CANTIDAD_LINEA:
        raise ErrorSubmitSelfOrdering("Cantidad excede el limite permitido.", 400)
    return cantidad


def _validar_indicacion(valor) -> str:
    texto = str(valor or "").strip()
    if len(texto) > MAX_INDICACION:
        raise ErrorSubmitSelfOrdering("Indicacion demasiado larga.", 400)
    return texto


def _normalizar_configuracion(configuracion) -> dict[str, tuple[str, ...]]:
    if configuracion is None:
        return {}
    if not isinstance(configuracion, list):
        raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)
    normalizada = {}
    for grupo in configuracion:
        if not isinstance(grupo, dict):
            raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)
        titulo = str(grupo.get("titulo") or "").strip()
        valores = grupo.get("valores") or []
        if not titulo or not isinstance(valores, list):
            raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)
        normalizada[titulo] = tuple(str(valor or "").strip() for valor in valores)
    return normalizada


def _configuracion_a_builder_args(nombre, configuracion, reglas):
    if nombre in reglas.combos_personales:
        return {
            "acompanantes": list(configuracion.get("Acompanantes", ())),
            "bebida": _unico(configuracion.get("Bebidas", ())),
        }
    if nombre in reglas.promociones_neko:
        extra = configuracion.get("Extra", ())
        if len(extra) > 1 or any(valor != reglas.promo_extra_lumpias_nombre for valor in extra):
            raise ErrorSubmitSelfOrdering("La seleccion del extra de lumpias no es valida", 400)
        return {
            "pollo": _unico(configuracion.get("Pollos", ())),
            "arroces": list(configuracion.get("Arroces", ())),
            "sabores": list(configuracion.get("Sabores", ())),
            "extra_lumpias": "1" if extra else "0",
        }
    if "refresco" in (nombre or "").lower():
        return {"sabor": _unico(configuracion.get("Sabores", ()))}
    return {}


def _validar_configuracion_contrato(configuracion, opciones):
    grupos_esperados = {opcion.titulo: opcion for opcion in opciones}
    grupos_recibidos = set(configuracion)
    grupos_desconocidos = grupos_recibidos - set(grupos_esperados)
    if grupos_desconocidos:
        raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)

    for titulo, opcion in grupos_esperados.items():
        valores = configuracion.get(titulo, ())
        if len(valores) > opcion.maximas:
            raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)
        if not opcion.opcional and len(valores) != opcion.requeridas:
            raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)
        if opcion.opcional and len(valores) < opcion.requeridas:
            raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)
        permitidos = set(opcion.valores)
        if any(valor not in permitidos for valor in valores):
            raise ErrorSubmitSelfOrdering("Configuracion invalida.", 400)


def _unico(valores):
    return valores[0] if valores else ""


def _productos_catalogo_permitidos(catalog_repository, reglas) -> dict[int, object]:
    catalogo = construir_catalogo_self_ordering(catalog_repository, reglas)
    return {
        producto.id: producto
        for categoria in catalogo.categorias
        for producto in categoria.productos
    }


def _serializar_configuracion(configuracion) -> str:
    return json.dumps(
        {clave: list(valores) for clave, valores in sorted(configuracion.items())},
        ensure_ascii=False,
        sort_keys=True,
    )


def _combinar_indicacion_cliente(indicacion_builder, indicacion_cliente):
    nota = normalizar_indicacion_item(indicacion_cliente)[:MAX_INDICACION]
    indicacion_builder = normalizar_indicacion_item(indicacion_builder)
    if not nota:
        return indicacion_builder
    if not indicacion_builder:
        return nota

    datos = deserializar_indicacion(indicacion_builder)
    if datos is not None:
        datos["nota"] = nota
        return normalizar_indicacion_item(serializar_indicacion(datos))

    return normalizar_indicacion_item(f"{indicacion_builder}; Nota: {nota}")


def _ahora(ahora_fn) -> datetime.datetime:
    return ahora_fn() if ahora_fn is not None else datetime.datetime.now(VENEZUELA_TZ)


def _formatear_fecha(fecha: datetime.datetime) -> str:
    return fecha.strftime(FORMATO_FECHA_HORA)
