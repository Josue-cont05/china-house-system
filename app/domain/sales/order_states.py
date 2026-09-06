ESTADO_ABIERTA = "abierta"
ESTADO_EN_COCINA = "en cocina"
ESTADO_LISTO = "listo"
ESTADO_CERRADA = "cerrada"


def orden_archivada(cierre_id):
    return cierre_id is not None


def orden_cerrada(estado):
    return estado == ESTADO_CERRADA


def puede_modificar_orden(estado, cierre_id, emergencia_activa=False):
    return (not orden_archivada(cierre_id)) and (
        not orden_cerrada(estado) or bool(emergencia_activa)
    )


def puede_editar_indicacion_item(estado, cierre_id, emergencia_activa=False):
    if orden_archivada(cierre_id):
        return False
    return estado in (ESTADO_ABIERTA, ESTADO_EN_COCINA) or (
        orden_cerrada(estado) and bool(emergencia_activa)
    )


def puede_eliminar_orden(estado, cierre_id):
    return (not orden_archivada(cierre_id)) and estado in (
        ESTADO_ABIERTA,
        ESTADO_EN_COCINA,
    )


def puede_agregar_item_orden(cierre_id, listo_despacho_at, emergencia_activa=False):
    # Agregar un item NUEVO (para enviar a cocina) es distinto de editar
    # precios/descuentos/items existentes (ver puede_modificar_orden /
    # puede_editar_indicacion_item, que si deben seguir bloqueados tras
    # cobrar salvo emergencia -- eso es correccion financiera). Una
    # orden ya cobrada (estado='cerrada') pero que Monica todavia no
    # marco LISTA PARA RETIRAR (listo_despacho_at IS NULL) sigue siendo
    # una mesa operativamente activa: el cliente puede seguir pidiendo
    # mientras espera su comida o su cuenta. CERRADA != LISTA PARA
    # RETIRAR.
    if orden_archivada(cierre_id):
        return False
    return listo_despacho_at is None or bool(emergencia_activa)
