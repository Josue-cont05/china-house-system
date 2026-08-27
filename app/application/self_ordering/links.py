import datetime
import secrets
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import pytz

from app.application.self_ordering.mesas import MesaSelfOrderingInvalida, normalizar_mesa_clave


CANALES_SELF_ORDERING = frozenset(("mesa", "pickup", "delivery", "whatsapp"))
ESTADO_LINK_ACTIVO = "activo"
ESTADO_LINK_REVOCADO = "revocado"
ESTADO_LINK_EXPIRADO = "expirado"
ESTADO_LINK_INEXISTENTE = "inexistente"
ESTADO_MESA_NO_HABILITADA = "mesa_no_habilitada"
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"
TOKEN_BYTES = 32
MAX_INTENTOS_TOKEN = 5
VENEZUELA_TZ = pytz.timezone("America/Caracas")


class ErrorSelfOrderingLink(ValueError):
    pass


class CanalSelfOrderingInvalido(ErrorSelfOrderingLink):
    pass


class OrdenSelfOrderingNoExiste(ErrorSelfOrderingLink):
    pass


class OrdenSelfOrderingRequerida(ErrorSelfOrderingLink):
    pass


class OrdenSelfOrderingCerrada(ErrorSelfOrderingLink):
    pass


class OrdenSelfOrderingArchivada(ErrorSelfOrderingLink):
    pass


class TokenSelfOrderingDuplicado(ErrorSelfOrderingLink):
    pass


class MesaSelfOrderingDuplicada(ErrorSelfOrderingLink):
    pass


class MesaSelfOrderingOcupada(ErrorSelfOrderingLink):
    pass


class TokenSelfOrderingNoGenerado(ErrorSelfOrderingLink):
    pass


@dataclass(frozen=True)
class SelfOrderLink:
    id: int
    orden_id: Optional[int]
    token: str
    canal: str
    estado: str
    fecha_creacion: str
    fecha_expiracion: Optional[str]
    mesa_clave: Optional[str] = None


@dataclass(frozen=True)
class NuevoSelfOrderLink:
    orden_id: Optional[int]
    token: str
    canal: str
    estado: str
    fecha_creacion: str
    fecha_expiracion: Optional[str]
    mesa_clave: Optional[str] = None


@dataclass(frozen=True)
class ResultadoValidacionLink:
    estado: str
    valido: bool
    link: Optional[SelfOrderLink] = None


class SelfOrderLinkRepository(Protocol):
    def orden_existe(self, orden_id: int) -> bool:
        ...

    def obtener_estado_orden(self, orden_id: int) -> Optional[tuple]:
        ...

    def obtener_datos_orden(self, orden_id: int) -> Optional[tuple]:
        ...

    def insertar_link(self, link: NuevoSelfOrderLink) -> SelfOrderLink:
        ...

    def buscar_por_token(self, token: str) -> Optional[SelfOrderLink]:
        ...

    def listar_links_por_orden_canal(self, orden_id: int, canal: str) -> list[SelfOrderLink]:
        ...

    def buscar_link_mesa_permanente(self, mesa_clave: str) -> Optional[SelfOrderLink]:
        ...

    def adoptar_link_mesa_historico(self, orden_id: int, mesa_clave: str) -> Optional[SelfOrderLink]:
        ...

    def asociar_link_mesa_a_orden(self, link_id: int, orden_id: int) -> SelfOrderLink:
        ...

    def buscar_por_id(self, link_id: int) -> Optional[SelfOrderLink]:
        ...

    def revocar_token(self, token: str) -> bool:
        ...

    def revocar_link_mesa_de_orden(self, orden_id: int, link_id: int) -> bool:
        ...


def generar_token_seguro() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def crear_self_order_link(
    repository: SelfOrderLinkRepository,
    canal: str,
    orden_id: Optional[int] = None,
    fecha_expiracion: Optional[object] = None,
    ahora_fn: Optional[Callable[[], datetime.datetime]] = None,
    token_generator: Callable[[], str] = generar_token_seguro,
    max_intentos: int = MAX_INTENTOS_TOKEN,
) -> SelfOrderLink:
    canal_normalizado = _validar_canal(canal)
    orden_id_normalizado = _normalizar_orden_id(orden_id)

    if canal_normalizado == "mesa" and orden_id_normalizado is None:
        raise OrdenSelfOrderingRequerida("La orden es obligatoria para links de mesa.")

    mesa_clave = None
    if canal_normalizado == "mesa":
        if not repository.orden_existe(orden_id_normalizado):
            raise OrdenSelfOrderingNoExiste("La orden indicada no existe.")
        mesa_clave = _mesa_clave_de_orden(repository, orden_id_normalizado)

    fecha_creacion = _formatear_fecha_hora(_ahora(ahora_fn))
    fecha_expiracion_texto = _normalizar_fecha_expiracion(fecha_expiracion)

    for _ in range(max_intentos):
        token = token_generator()
        link = NuevoSelfOrderLink(
            orden_id=orden_id_normalizado,
            token=token,
            canal=canal_normalizado,
            estado=ESTADO_LINK_ACTIVO,
            fecha_creacion=fecha_creacion,
            fecha_expiracion=fecha_expiracion_texto,
            mesa_clave=mesa_clave,
        )
        try:
            return repository.insertar_link(link)
        except TokenSelfOrderingDuplicado:
            continue
        except MesaSelfOrderingDuplicada:
            if mesa_clave:
                link_existente = repository.buscar_link_mesa_permanente(mesa_clave)
                if link_existente is not None:
                    _validar_reasignacion_link_mesa(repository, link_existente, orden_id_normalizado)
                    if link_existente.orden_id != orden_id_normalizado:
                        return repository.asociar_link_mesa_a_orden(link_existente.id, orden_id_normalizado)
                    return link_existente
            raise

    raise TokenSelfOrderingNoGenerado("No se pudo generar un token unico.")


def validar_self_order_link(
    repository: SelfOrderLinkRepository,
    token: str,
    ahora_fn: Optional[Callable[[], datetime.datetime]] = None,
) -> ResultadoValidacionLink:
    link = repository.buscar_por_token(token)
    if link is None:
        return ResultadoValidacionLink(estado=ESTADO_LINK_INEXISTENTE, valido=False)

    if link.estado == ESTADO_LINK_REVOCADO:
        return ResultadoValidacionLink(estado=ESTADO_LINK_REVOCADO, valido=False, link=link)

    if _esta_expirado(link.fecha_expiracion, _ahora(ahora_fn)):
        return ResultadoValidacionLink(estado=ESTADO_LINK_EXPIRADO, valido=False, link=link)

    if link.estado != ESTADO_LINK_ACTIVO:
        return ResultadoValidacionLink(estado=link.estado, valido=False, link=link)

    return ResultadoValidacionLink(estado=ESTADO_LINK_ACTIVO, valido=True, link=link)


def validar_self_order_link_para_catalogo(
    repository: SelfOrderLinkRepository,
    token: str,
    ahora_fn: Optional[Callable[[], datetime.datetime]] = None,
) -> ResultadoValidacionLink:
    resultado = validar_self_order_link(repository, token, ahora_fn=ahora_fn)
    if not resultado.valido or resultado.link is None:
        return resultado

    if resultado.link.canal == "mesa":
        try:
            _validar_orden_mesa_abierta(repository, resultado.link.orden_id)
        except OrdenSelfOrderingNoExiste:
            return ResultadoValidacionLink(estado=ESTADO_MESA_NO_HABILITADA, valido=False, link=resultado.link)
        except OrdenSelfOrderingArchivada:
            return ResultadoValidacionLink(estado=ESTADO_MESA_NO_HABILITADA, valido=False, link=resultado.link)
        except OrdenSelfOrderingCerrada:
            return ResultadoValidacionLink(estado=ESTADO_MESA_NO_HABILITADA, valido=False, link=resultado.link)

    return resultado


def obtener_o_crear_link_mesa(
    repository: SelfOrderLinkRepository,
    orden_id: int,
    ahora_fn: Optional[Callable[[], datetime.datetime]] = None,
    token_generator: Callable[[], str] = generar_token_seguro,
) -> tuple[SelfOrderLink, bool]:
    _validar_orden_mesa_abierta(repository, orden_id)
    mesa_clave = _mesa_clave_de_orden(repository, orden_id)

    link_permanente = repository.buscar_link_mesa_permanente(mesa_clave)
    if link_permanente is not None:
        resultado = validar_self_order_link(repository, link_permanente.token, ahora_fn=ahora_fn)
        if resultado.valido and resultado.link is not None:
            _validar_reasignacion_link_mesa(repository, resultado.link, orden_id)
            if resultado.link.orden_id != orden_id:
                return repository.asociar_link_mesa_a_orden(resultado.link.id, orden_id), False
            return resultado.link, False

    link_historico = repository.adoptar_link_mesa_historico(orden_id, mesa_clave)
    if link_historico is not None:
        return link_historico, False

    link = crear_self_order_link(
        repository,
        canal="mesa",
        orden_id=orden_id,
        ahora_fn=ahora_fn,
        token_generator=token_generator,
    )
    return link, True


def obtener_link_activo_mesa(
    repository: SelfOrderLinkRepository,
    orden_id: int,
    ahora_fn: Optional[Callable[[], datetime.datetime]] = None,
) -> Optional[SelfOrderLink]:
    try:
        mesa_clave = _mesa_clave_de_orden(repository, orden_id)
    except ErrorSelfOrderingLink:
        mesa_clave = None
    links = []
    if mesa_clave:
        link_mesa = repository.buscar_link_mesa_permanente(mesa_clave)
        if link_mesa is not None:
            links.append(link_mesa)
    links.extend(repository.listar_links_por_orden_canal(orden_id, "mesa"))

    vistos = set()
    for link in links:
        if link.id in vistos:
            continue
        vistos.add(link.id)
        resultado = validar_self_order_link(repository, link.token, ahora_fn=ahora_fn)
        if resultado.valido and resultado.link is not None:
            return resultado.link
    return None


def revocar_link_mesa_de_orden(repository: SelfOrderLinkRepository, orden_id: int, link_id: int) -> bool:
    _validar_orden_mesa_abierta(repository, orden_id)
    return repository.revocar_link_mesa_de_orden(orden_id, link_id)


def revocar_self_order_link(repository: SelfOrderLinkRepository, token: str) -> bool:
    return repository.revocar_token(token)


def _validar_canal(canal: str) -> str:
    canal_normalizado = (canal or "").strip().lower()
    if canal_normalizado not in CANALES_SELF_ORDERING:
        raise CanalSelfOrderingInvalido("Canal de self-ordering invalido.")
    return canal_normalizado


def _normalizar_orden_id(orden_id: Optional[int]) -> Optional[int]:
    if orden_id is None:
        return None
    return int(orden_id)


def _validar_orden_mesa_abierta(repository: SelfOrderLinkRepository, orden_id: int) -> None:
    orden = repository.obtener_estado_orden(orden_id)
    if orden is None:
        raise OrdenSelfOrderingNoExiste("La orden indicada no existe.")

    estado, cierre_id = orden
    if cierre_id is not None:
        raise OrdenSelfOrderingArchivada("No se puede usar self-ordering en una orden archivada.")
    if estado == "cerrada":
        raise OrdenSelfOrderingCerrada("No se puede usar self-ordering en una orden cerrada.")


def _orden_esta_activa(repository: SelfOrderLinkRepository, orden_id: Optional[int]) -> bool:
    if orden_id is None:
        return False
    orden = repository.obtener_estado_orden(orden_id)
    if orden is None:
        return False
    estado, cierre_id = orden
    return estado == "abierta" and cierre_id is None


def _validar_reasignacion_link_mesa(
    repository: SelfOrderLinkRepository,
    link: SelfOrderLink,
    nuevo_orden_id: int,
) -> None:
    if link.orden_id == nuevo_orden_id:
        return
    if _orden_esta_activa(repository, link.orden_id):
        raise MesaSelfOrderingOcupada("La mesa ya tiene una orden abierta.")


def _mesa_clave_de_orden(repository: SelfOrderLinkRepository, orden_id: int) -> str:
    datos = repository.obtener_datos_orden(orden_id)
    if datos is None:
        raise OrdenSelfOrderingNoExiste("La orden indicada no existe.")
    tipo, referencia = datos
    if (tipo or "").strip().lower() != "mesa":
        raise MesaSelfOrderingInvalida("Self-ordering de mesa solo aplica a ordenes de mesa.")
    return normalizar_mesa_clave(referencia)


def _ahora(ahora_fn: Optional[Callable[[], datetime.datetime]]) -> datetime.datetime:
    return ahora_fn() if ahora_fn is not None else datetime.datetime.now(VENEZUELA_TZ)


def _formatear_fecha_hora(fecha: datetime.datetime) -> str:
    return fecha.strftime(FORMATO_FECHA_HORA)


def _normalizar_fecha_expiracion(fecha_expiracion: Optional[object]) -> Optional[str]:
    if fecha_expiracion is None:
        return None
    if isinstance(fecha_expiracion, datetime.datetime):
        return _formatear_fecha_hora(fecha_expiracion)
    texto = str(fecha_expiracion).strip()
    return texto or None


def _esta_expirado(fecha_expiracion: Optional[str], ahora: datetime.datetime) -> bool:
    if not fecha_expiracion:
        return False
    fecha_limite = datetime.datetime.strptime(fecha_expiracion, FORMATO_FECHA_HORA)
    ahora_comparable = ahora.replace(tzinfo=None)
    return fecha_limite <= ahora_comparable
