from dataclasses import dataclass


ESTADO_COMANDA_EN_COCINA = "en_cocina"
ESTADO_COMANDA_LISTO = "listo"
ORIGEN_COMANDA_MANUAL = "manual"
ORIGEN_COMANDA_SELF_ORDERING = "self_ordering"


class ErrorComanda(ValueError):
    pass


class OrdenComandaNoExiste(ErrorComanda):
    pass


class OrdenComandaSinItems(ErrorComanda):
    pass


@dataclass(frozen=True)
class ResultadoComanda:
    comanda_id: int
    orden_id: int
    numero_orden: int
    secuencia: int
    estado: str


def texto_numero_comanda(numero_orden, secuencia):
    base = f"Orden {numero_orden}" if numero_orden is not None else "Orden Sin numero"
    if int(secuencia or 0) <= 0:
        return base
    return f"{base}.{int(secuencia)}"
