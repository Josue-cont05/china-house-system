"""
create.py (aplicacion)

Caso de uso "crear una orden nueva" (ruta /crear_orden en web_app.py):
Mesa, Pick Up o Delivery.

Preserva DELIBERADAMENTE el patron existente de conexiones
independientes por paso -- NO es una sola transaccion grande. El
INSERT de la orden es la unica escritura que importa de forma
atomica/financiera; activar el link permanente de self-ordering para
Mesa y notificar el estado de delivery son efectos SECUNDARIOS de
mejor esfuerzo que pueden completarse (o fallar de forma visible)
DESPUES de que la orden ya exista, exactamente igual que el
comportamiento original.

Levanta:
- `app.application.self_ordering.mesas.MesaSelfOrderingInvalida` si la
  referencia de mesa no es valida (re-exportada aqui por conveniencia).
- `OrdenYaAbiertaError` si ya hay una orden Mesa abierta con esa
  referencia.
- `app.application.self_ordering.links.MesaSelfOrderingOcupada` si el
  link permanente no se pudo activar DESPUES de crear la orden (la
  orden YA existe en ese punto -- comportamiento preexistente).

`get_connection`, `obtener_ultimo_id`, `ahora_venezuela`,
`obtener_conductor_delivery_por_defecto`, `notificar_delivery_asignado`
y `notificar_delivery_necesita_conductor` se reciben inyectados (siguen
definidos en web_app.py hoy) para no crear un import circular."""

from app.application.self_ordering.links import activar_link_permanente_para_nueva_orden_mesa
from app.application.self_ordering.mesas import (
    MesaSelfOrderingInvalida,
    etiqueta_mesa,
    normalizar_mesa_clave,
)
from app.infrastructure.database.self_ordering_links import SqlSelfOrderLinkRepository

ESTADO_DELIVERY_ASIGNADO_INTERNO = "ASSIGNED_INTERNAL"
ESTADO_DELIVERY_NECESITA_CONDUCTOR = "NEEDS_DRIVER"


class OrdenYaAbiertaError(RuntimeError):
    pass


def crear_orden_nueva(
    *,
    get_connection,
    obtener_ultimo_id,
    ahora_venezuela,
    obtener_conductor_delivery_por_defecto,
    notificar_delivery_asignado,
    notificar_delivery_necesita_conductor,
    tipo,
    referencia,
    referencia_mesa,
    cliente,
    usuario_id,
    delivery_driver_choice,
):
    tipo = (tipo or "").strip()
    es_mesa = tipo.lower() == "mesa"
    if es_mesa:
        tipo = "Mesa"
        referencia = normalizar_mesa_clave(referencia_mesa)
        conn_validacion = get_connection()
        cursor_validacion = conn_validacion.cursor()
        cursor_validacion.execute(
            """
            SELECT id
            FROM ordenes
            WHERE LOWER(tipo)='mesa'
              AND referencia=?
              AND estado='abierta'
              AND cierre_id IS NULL
            LIMIT 1
            """,
            (referencia,),
        )
        orden_abierta = cursor_validacion.fetchone()
        conn_validacion.close()
        if orden_abierta is not None:
            raise OrdenYaAbiertaError(f"{etiqueta_mesa(referencia)} ya tiene una orden abierta.")

    es_delivery = tipo.lower() == "delivery"
    delivery_driver_user_id = None
    delivery_driver_status = None
    if es_delivery:
        eleccion = (delivery_driver_choice or "").strip()
        conn_conductor = get_connection()
        cursor_conductor = conn_conductor.cursor()
        conductor_default = obtener_conductor_delivery_por_defecto(cursor_conductor)
        conn_conductor.close()
        if eleccion == "default" and conductor_default:
            delivery_driver_user_id = conductor_default[0]
            delivery_driver_status = ESTADO_DELIVERY_ASIGNADO_INTERNO
        else:
            delivery_driver_status = ESTADO_DELIVERY_NECESITA_CONDUCTOR

    fecha_hora = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    fecha = ahora_venezuela().strftime("%Y-%m-%d")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO ordenes (
            numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id,
            delivery_driver_user_id, delivery_driver_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            None, fecha_hora, fecha, tipo, referencia, cliente, "abierta", usuario_id,
            delivery_driver_user_id, delivery_driver_status,
        ),
    )
    orden_id = obtener_ultimo_id(cursor, "ordenes")
    conn.commit()
    conn.close()

    if es_mesa:
        activar_link_permanente_para_nueva_orden_mesa(
            SqlSelfOrderLinkRepository(get_connection, obtener_ultimo_id),
            orden_id,
        )

    if es_delivery:
        if delivery_driver_status == ESTADO_DELIVERY_ASIGNADO_INTERNO:
            notificar_delivery_asignado(orden_id, delivery_driver_user_id, None, cliente, referencia)
        elif delivery_driver_status == ESTADO_DELIVERY_NECESITA_CONDUCTOR:
            conn_notif = get_connection()
            cursor_notif = conn_notif.cursor()
            notificar_delivery_necesita_conductor(cursor_notif, orden_id, None, cliente, referencia)
            conn_notif.close()

    return orden_id
