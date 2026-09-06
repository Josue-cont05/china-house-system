"""
items.py (aplicacion)

Casos de uso de gestion de items de una orden ya creada (rutas
/agregar/<orden_id>/<producto_id>, /eliminar_item/<item_id>/<orden_id>
y /actualizar_indicacion_item/<item_id>/<orden_id> en web_app.py).

Cada uno valida contra las reglas de dominio ya existentes en
app/domain/sales/order_states.py y levanta ValueError con un mensaje
listo para mostrar (texto plano, sin status code -- igual que el
comportamiento HTTP original) cuando la operacion no es valida. Ninguno
hace commit/rollback/close: eso lo sigue decidiendo la ruta, que abrio
la conexion.

`construir_items_orden` puede levantar
`app.domain.sales.item_builder.ErrorConstruccionItem` (SI trae su
propio `.mensaje`/`.status_code`, a diferencia de los ValueError de
este modulo) -- se deja propagar sin envolver para que la ruta la seria
capturando exactamente igual que antes.

`emergencia_activa` y `registrar_auditoria_emergencia` se reciben
inyectados (siguen definidos en web_app.py hoy, cross-cutting con la
mision "edicion de emergencia", que toca varios dominios ademas de
ordenes) para no crear un import circular."""

from app.domain.sales.calculations import _a_float as a_float
from app.domain.sales.item_builder import construir_items_orden
from app.domain.sales.item_descriptions import normalizar_indicacion_item
from app.domain.sales.order_states import (
    orden_archivada,
    puede_agregar_item_orden,
    puede_editar_indicacion_item,
    puede_modificar_orden,
)


def agregar_item_a_orden(
    cursor,
    *,
    orden_id,
    producto_id,
    sabor,
    acompanantes,
    bebida,
    pollo,
    arroces,
    sabores,
    extra_lumpias,
    combos_personales,
    acompanantes_combo,
    bebidas_combo,
    combos_cantidad_acompanantes,
    promociones_neko,
    promociones_con_pollo,
    pollos_promocion,
    arroces_promocion,
    promo_extra_lumpias_nombre,
    promo_extra_lumpias_precio,
    emergencia_activa,
    registrar_auditoria_emergencia,
):
    cursor.execute(
        "SELECT estado, cierre_id, listo_despacho_at FROM ordenes WHERE id=?", (orden_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("Orden no encontrada")
    estado, cierre_id, listo_despacho_at = row

    if orden_archivada(cierre_id):
        raise ValueError("No puedes modificar una orden archivada en cierre de jornada")

    edicion_emergencia_activa = emergencia_activa(orden_id)
    # Agregar un item NUEVO (para enviar a cocina) esta permitido aunque
    # la orden ya este cobrada (estado='cerrada'), mientras todavia no
    # se haya marcado LISTA PARA RETIRAR -- CERRADA != LISTA PARA
    # RETIRAR (mision Despacho). Ver puede_agregar_item_orden.
    if not puede_agregar_item_orden(cierre_id, listo_despacho_at, edicion_emergencia_activa):
        raise ValueError("No puedes agregar productos a una orden ya lista para retirar")

    cursor.execute(
        """
        SELECT p.nombre, p.precio, c.nombre
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE p.id=?
        """,
        (producto_id,),
    )
    p = cursor.fetchone()
    if not p:
        raise ValueError("Producto no encontrado")

    cursor.execute("SELECT COALESCE(delivery_usd, 0) FROM ordenes WHERE id=?", (orden_id,))
    delivery_actual = a_float(cursor.fetchone()[0])

    items_construidos = construir_items_orden(
        producto_nombre=p[0],
        producto_precio=p[1],
        categoria_nombre=p[2],
        delivery_actual=delivery_actual,
        sabor=sabor,
        acompanantes=acompanantes,
        bebida=bebida,
        pollo=pollo,
        arroces=arroces,
        sabores=sabores,
        extra_lumpias=extra_lumpias,
        combos_personales=combos_personales,
        acompanantes_combo=acompanantes_combo,
        bebidas_combo=bebidas_combo,
        combos_cantidad_acompanantes=combos_cantidad_acompanantes,
        promociones_neko=promociones_neko,
        promociones_con_pollo=promociones_con_pollo,
        pollos_promocion=pollos_promocion,
        arroces_promocion=arroces_promocion,
        promo_extra_lumpias_nombre=promo_extra_lumpias_nombre,
        promo_extra_lumpias_precio=promo_extra_lumpias_precio,
    )

    # Un agregado a una orden YA cobrada (estado='cerrada') es consumo
    # post-cobro todavia no liquidado: arranca fuera del snapshot
    # oficial (incluido_en_snapshot=0) hasta que se cobre/liquide (ver
    # app.infrastructure.database.payments.marcar_items_incluidos_en_snapshot).
    # Si la orden sigue abierta, es consumo normal que sera parte del
    # proximo cobro de todos modos.
    incluido_en_snapshot = 0 if estado == "cerrada" else 1
    cursor.execute(
        """
        INSERT INTO orden_items (orden_id, producto, precio, indicacion, incluido_en_snapshot)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            orden_id,
            items_construidos.item_principal.producto,
            items_construidos.item_principal.precio,
            items_construidos.item_principal.indicacion,
            incluido_en_snapshot,
        ),
    )
    for item_extra in items_construidos.items_extra:
        cursor.execute(
            """
            INSERT INTO orden_items (orden_id, producto, precio, indicacion, incluido_en_snapshot)
            VALUES (?, ?, ?, ?, ?)
            """,
            (orden_id, item_extra.producto, item_extra.precio, item_extra.indicacion, incluido_en_snapshot),
        )

    if estado == "cerrada" and edicion_emergencia_activa:
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "agregar_producto_emergencia",
            f"Producto agregado: {items_construidos.item_principal.producto} - ${items_construidos.item_principal.precio}",
        )


def eliminar_item_de_orden(
    cursor, *, item_id, orden_id, emergencia_activa, registrar_auditoria_emergencia
):
    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Orden no encontrada")

    estado, cierre_id = row
    if orden_archivada(cierre_id):
        raise ValueError("Orden archivada, no se puede modificar")

    edicion_emergencia_activa = emergencia_activa(orden_id)
    if not puede_modificar_orden(estado, cierre_id, edicion_emergencia_activa):
        raise ValueError("Orden cerrada, no se puede modificar")

    cursor.execute(
        "SELECT id, producto, precio FROM orden_items WHERE id=? AND orden_id=?",
        (item_id, orden_id),
    )
    item_row = cursor.fetchone()
    if not item_row:
        raise ValueError("Producto no encontrado en esta orden")

    cursor.execute("DELETE FROM orden_items WHERE id=? AND orden_id=?", (item_id, orden_id))
    if estado == "cerrada" and edicion_emergencia_activa:
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "eliminar_producto_emergencia",
            f"Producto eliminado: {item_row[1]} - ${item_row[2]}",
        )


def actualizar_indicacion_de_item(
    cursor,
    *,
    item_id,
    orden_id,
    indicacion,
    emergencia_activa,
    registrar_auditoria_emergencia,
):
    indicacion = normalizar_indicacion_item(indicacion)

    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Orden no encontrada")

    estado, cierre_id = row
    if orden_archivada(cierre_id):
        raise ValueError("Orden archivada, no se puede modificar")

    edicion_emergencia_activa = emergencia_activa(orden_id)
    if not puede_editar_indicacion_item(estado, cierre_id, edicion_emergencia_activa):
        raise ValueError("Orden cerrada, no se puede modificar")

    cursor.execute(
        "SELECT id, producto FROM orden_items WHERE id=? AND orden_id=?",
        (item_id, orden_id),
    )
    item_row = cursor.fetchone()
    if not item_row:
        raise ValueError("Producto no encontrado en esta orden")

    cursor.execute(
        "UPDATE orden_items SET indicacion=? WHERE id=? AND orden_id=?",
        (indicacion, item_id, orden_id),
    )

    if estado == "cerrada" and edicion_emergencia_activa:
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "editar_indicacion_emergencia",
            f"Indicacion actualizada para {item_row[1]}: {indicacion}",
        )
