"""
assignment.py (aplicacion)

Caso de uso "asignacion posterior de conductor de un Delivery" (ruta
/orden/<id>/delivery_conductor en web_app.py): un Delivery creado como
NEEDS_DRIVER (o EXTERNAL) puede resolverse mas tarde asignando un
conductor interno (usuario real, nunca un nombre) o marcandolo
EXTERNO. NEEDS_DRIVER solo se resuelve asignando -- leer la
notificacion NUNCA lo resuelve.

Levanta:
- `OrdenNoEncontradaError` si la orden no existe (la ruta responde 404).
- `ValueError` para el resto de validaciones (la ruta responde 400).

No envia la notificacion de conductor asignado: eso lo hace la ruta
DESPUES del commit (mismo orden que el comportamiento original --
notificar solo cuando la asignacion ya quedo persistida), pasandole a
`notificar_delivery_conductor_asignado_posteriormente` (sigue definida
en web_app.py hoy) los datos que devuelve `asignar_conductor_interno`.
"""

from app.domain.delivery.rules import ESTADO_DELIVERY_ASIGNADO_INTERNO, ESTADO_DELIVERY_EXTERNO
from app.domain.sales.order_states import orden_archivada


class OrdenNoEncontradaError(ValueError):
    pass


def _obtener_orden_delivery(cursor, orden_id):
    cursor.execute(
        "SELECT tipo, numero_orden, cliente, referencia, cierre_id FROM ordenes WHERE id=?",
        (orden_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise OrdenNoEncontradaError("Orden no encontrada")
    tipo, numero_orden, cliente, referencia, cierre_id = row
    if (tipo or "").strip().lower() != "delivery":
        raise ValueError("Esta orden no es un Delivery")
    if orden_archivada(cierre_id):
        raise ValueError("No puedes modificar una orden archivada en cierre de jornada")
    return numero_orden, cliente, referencia


def asignar_conductor_interno(cursor, *, orden_id, conductor_user_id):
    numero_orden, cliente, referencia = _obtener_orden_delivery(cursor, orden_id)

    try:
        conductor_id = int(conductor_user_id)
    except (TypeError, ValueError):
        raise ValueError("Selecciona un conductor valido")

    cursor.execute(
        "SELECT id FROM usuarios WHERE id=? AND es_conductor_delivery=1 AND COALESCE(activo,1)=1",
        (conductor_id,),
    )
    if not cursor.fetchone():
        raise ValueError("Ese usuario no esta habilitado como conductor de delivery")

    cursor.execute(
        "UPDATE ordenes SET delivery_driver_user_id=?, delivery_driver_status=? WHERE id=?",
        (conductor_id, ESTADO_DELIVERY_ASIGNADO_INTERNO, orden_id),
    )
    return conductor_id, numero_orden, cliente, referencia


def marcar_conductor_externo(cursor, *, orden_id):
    _obtener_orden_delivery(cursor, orden_id)
    cursor.execute(
        "UPDATE ordenes SET delivery_driver_user_id=NULL, delivery_driver_status=? WHERE id=?",
        (ESTADO_DELIVERY_EXTERNO, orden_id),
    )
