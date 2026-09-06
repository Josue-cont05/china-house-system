"""
events.py (aplicacion)

Casos de uso "resolver un evento de negocio en una notificacion
interna" (motor general de notificaciones, mision "Mesa" + "Pick Up" +
"Delivery"): Mesa/Pick Up/Delivery listo para retirar, Delivery
asignado al crear la orden, Delivery sin conductor (NEEDS_DRIVER), y
Delivery con conductor asignado despues. Cada funcion construye el
titulo/mensaje (conocimiento de negocio del evento) y delega la
persistencia idempotente en
app.infrastructure.database.notifications.crear_notificacion
(event_key UNIQUE + INSERT...WHERE NOT EXISTS -- un reintento HTTP o
un doble evento nunca duplica una notificacion).

`get_connection`, `ahora_venezuela` y `texto_numero_orden` se reciben
inyectados (siguen definidos en web_app.py hoy) para no crear un
import circular."""

import html as html_lib

from app.infrastructure.database.delivery import listar_coordinadores_delivery
from app.infrastructure.database.notifications import crear_notificacion


def _crear_notificacion(
    get_connection,
    ahora_venezuela,
    event_key,
    usuario_destino_id,
    tipo,
    titulo,
    mensaje,
    orden_id=None,
    datos=None,
):
    return crear_notificacion(
        get_connection,
        event_key=event_key,
        usuario_destino_id=usuario_destino_id,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        orden_id=orden_id,
        datos=datos,
        fecha=ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S"),
    )


def notificar_orden_lista_para_retirar(
    get_connection,
    ahora_venezuela,
    texto_numero_orden,
    orden_id,
    usuario_destino_id,
    tipo_orden,
    numero_orden,
    referencia,
    cliente,
):
    """ORDER_READY_FOR_HANDOFF: Monica termino de armar el pedido en
    Despacho. NUNCA dice "entregado" -- el responsable todavia debe
    retirarlo (mesonero) o avisar al cliente (Pick Up)."""
    if not usuario_destino_id:
        return
    tipo_normalizado = (tipo_orden or "").strip().lower()
    numero_texto = texto_numero_orden(numero_orden)
    if tipo_normalizado == "mesa":
        titulo = f"🍜 {html_lib.escape(referencia or 'MESA')} — PEDIDO LISTO"
        mensaje = f"El pedido {numero_texto} esta listo en Despacho. Retiralo para llevarlo a la mesa."
    elif tipo_normalizado in ("para llevar", "pickup", "pick up"):
        titulo = "🛍️ PICK UP LISTO"
        mensaje = f"El pedido {numero_texto}" + (f" (Cliente: {cliente})" if cliente else "") + " esta listo. Puedes avisarle al cliente para retirar."
    else:
        titulo = f"🛵 DELIVERY {numero_texto} LISTO"
        mensaje = "El pedido esta listo en Despacho. Ya puedes retirarlo para salir."

    _crear_notificacion(
        get_connection,
        ahora_venezuela,
        f"ORDER_READY_FOR_HANDOFF:{orden_id}",
        usuario_destino_id,
        "ORDER_READY_FOR_HANDOFF",
        titulo,
        mensaje,
        orden_id=orden_id,
    )


def notificar_delivery_asignado(
    get_connection, ahora_venezuela, texto_numero_orden, orden_id, conductor_user_id, numero_orden, cliente, referencia
):
    _crear_notificacion(
        get_connection,
        ahora_venezuela,
        f"DELIVERY_CREATED_ASSIGNED:{orden_id}:{conductor_user_id}",
        conductor_user_id,
        "DELIVERY_CREATED_ASSIGNED",
        "🛵 NUEVO DELIVERY ASIGNADO",
        (
            f"Pedido {texto_numero_orden(numero_orden)}"
            + (f"\nCliente: {cliente}" if cliente else "")
            + (f"\nReferencia/Zona: {referencia}" if referencia else "")
            + "\n\nTienes asignado este delivery."
        ),
        orden_id=orden_id,
    )


def notificar_delivery_necesita_conductor(
    cursor, get_connection, ahora_venezuela, texto_numero_orden, orden_id, numero_orden, cliente, referencia
):
    mensaje = (
        f"Pedido {texto_numero_orden(numero_orden)}"
        + (f"\nCliente: {cliente}" if cliente else "")
        + (f"\nReferencia/Zona: {referencia}" if referencia else "")
        + "\n\nEntro un delivery y hay que conseguir conductor."
    )
    coordinadores = listar_coordinadores_delivery(cursor)
    if not coordinadores:
        print(f"ADVERTENCIA: Delivery {orden_id} quedo NEEDS_DRIVER pero no hay coordinadores configurados.")
        return
    for coordinador_id, _nombre in coordinadores:
        _crear_notificacion(
            get_connection,
            ahora_venezuela,
            f"DELIVERY_NEEDS_DRIVER:{orden_id}:{coordinador_id}",
            coordinador_id,
            "DELIVERY_NEEDS_DRIVER",
            "⚠️ NUEVO DELIVERY — CONDUCTOR PENDIENTE",
            mensaje,
            orden_id=orden_id,
        )


def notificar_delivery_listo(get_connection, ahora_venezuela, texto_numero_orden, orden_id, driver_id, numero_orden):
    """DELIVERY_READY: la orden quedo LISTA PARA RETIRAR y ya tiene
    conductor interno asignado -- se le avisa a ESE conductor. Si el
    Delivery sigue NEEDS_DRIVER/EXTERNAL, deliberadamente no se
    notifica esta etapa (no se inventa un conductor; evita ruido hasta
    que se asigne uno real)."""
    _crear_notificacion(
        get_connection,
        ahora_venezuela,
        f"DELIVERY_READY:{orden_id}",
        driver_id,
        "DELIVERY_READY",
        f"🛵 DELIVERY {texto_numero_orden(numero_orden)} LISTO",
        "El pedido esta listo en Despacho. Ya puedes retirarlo para salir.",
        orden_id=orden_id,
    )


def notificar_delivery_conductor_asignado_posteriormente(
    get_connection, ahora_venezuela, texto_numero_orden, orden_id, conductor_user_id, numero_orden, cliente, referencia
):
    _crear_notificacion(
        get_connection,
        ahora_venezuela,
        f"DELIVERY_DRIVER_ASSIGNED:{orden_id}:{conductor_user_id}",
        conductor_user_id,
        "DELIVERY_DRIVER_ASSIGNED",
        "🛵 NUEVO DELIVERY ASIGNADO",
        (
            f"Pedido {texto_numero_orden(numero_orden)}"
            + (f"\nCliente: {cliente}" if cliente else "")
            + (f"\nReferencia/Zona: {referencia}" if referencia else "")
            + "\n\nTienes asignado este delivery."
        ),
        orden_id=orden_id,
    )
