"""
payments.py (infraestructura)

Repositorio SQL puro del ciclo de cobro de una orden (columnas
financieras de `ordenes` + el flag `orden_items.incluido_en_snapshot`
de la mision "recibos post-cobro"). Deliberadamente NO valida reglas de
negocio de alto nivel ni conoce Flask/HTTP -- eso vive en
app/application/payments/*, que orquesta estas funciones dentro de la
transaccion de /cobrar y /orden/<id>/cobrar_pendiente.

`obtener_tasa_cobro` se recibe inyectado (sigue definido en web_app.py
hoy) para no crear un import circular.
"""

from app.domain.sales.calculations import (
    _a_float as a_float,
    TOLERANCIA_COBRO,
    calcular_totales_financieros_delivery,
)
from app.domain.sales.order_states import orden_archivada


def calcular_pendiente_post_cobro(cursor, orden_id, obtener_tasa_cobro):
    """Mision "seguridad financiera de agregados post-cobro": una orden
    ya cobrada (estado='cerrada') pero todavia no despachada puede
    recibir productos nuevos (ver puede_agregar_item_orden en
    app/domain/sales/order_states.py). Esta funcion es de SOLO LECTURA:
    compara el total recalculado ahora mismo desde orden_items/delivery
    contra el snapshot total_cliente_usd que quedo grabado en el ultimo
    cobro, y devuelve cuanto hay pendiente de cobrar por ese consumo
    nuevo (o None si no aplica: orden no cerrada, archivada, ya
    despachada, delivery legacy, o sin diferencia real)."""
    cursor.execute(
        """
        SELECT estado, cierre_id, listo_despacho_at, descuento, delivery_usd,
               total_cliente_usd
        FROM ordenes WHERE id=?
        """,
        (orden_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    estado, cierre_id, listo_despacho_at, descuento, delivery_usd, total_previo = row
    if estado != "cerrada" or orden_archivada(cierre_id) or listo_despacho_at is not None:
        return None

    cursor.execute(
        """
        SELECT oi.producto, oi.precio,
               (
                   SELECT c.nombre FROM productos p
                   LEFT JOIN categorias c ON p.categoria_id = c.id
                   WHERE LOWER(p.nombre)=LOWER(oi.producto)
                   ORDER BY COALESCE(p.activo, 1) DESC, p.id
                   LIMIT 1
               ) AS categoria
        FROM orden_items oi
        WHERE oi.orden_id=?
        """,
        (orden_id,),
    )
    items = cursor.fetchall()
    try:
        tasa_actual = obtener_tasa_cobro(cursor)
        totales_actuales = calcular_totales_financieros_delivery(
            items, tasa_actual, a_float(descuento), a_float(delivery_usd)
        )
    except ValueError:
        return None

    if totales_actuales["modo"] == "legacy":
        # Ordenes con delivery legacy (categoria delivery mezclada en
        # orden_items) no soportan el flujo de cobro incremental: sus
        # campos snapshot_* vienen en None (ver calculations.py).
        return None

    total_actual_usd = totales_actuales["total_cliente_usd"]
    total_previo_usd = a_float(total_previo)
    pendiente_usd = round(total_actual_usd - total_previo_usd, 2)
    if pendiente_usd <= TOLERANCIA_COBRO:
        return None

    return {
        "pendiente_usd": pendiente_usd,
        "total_actual_usd": total_actual_usd,
        "total_previo_usd": total_previo_usd,
        "tasa_actual": tasa_actual,
        "totales_actuales": totales_actuales,
    }


def aplicar_totales_post_cobro(cursor, orden_id, totales, cliente_id=None, cliente_nombre=None):
    """Actualiza SOLO los campos agregados de la orden (consumo total
    recalculado) tras liquidar un cobro incremental. Nunca toca
    estado/fecha_cobro/fecha_venta/tasa_cobro/descuento ni borra pagos o
    movimientos previos -- el cobro original queda intacto (mision
    seccion 8: "no reescribir historia financiera")."""
    if cliente_id is not None:
        cursor.execute(
            """
            UPDATE ordenes
            SET subtotal_usd=?, total_usd=?, total_bs=?,
                venta_restaurante_usd=?, delivery_usd=?,
                total_cliente_usd=?, total_cliente_bs=?,
                cliente_id=COALESCE(cliente_id, ?), cliente=COALESCE(cliente, ?)
            WHERE id=? AND cierre_id IS NULL
            """,
            (
                totales["subtotal_snapshot_usd"],
                totales["total_usd"],
                totales["total_bs"],
                totales["snapshot_venta_restaurante_usd"],
                totales["snapshot_delivery_usd"],
                totales["snapshot_total_cliente_usd"],
                totales["total_cliente_bs"],
                cliente_id,
                cliente_nombre,
                orden_id,
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE ordenes
            SET subtotal_usd=?, total_usd=?, total_bs=?,
                venta_restaurante_usd=?, delivery_usd=?,
                total_cliente_usd=?, total_cliente_bs=?
            WHERE id=? AND cierre_id IS NULL
            """,
            (
                totales["subtotal_snapshot_usd"],
                totales["total_usd"],
                totales["total_bs"],
                totales["snapshot_venta_restaurante_usd"],
                totales["snapshot_delivery_usd"],
                totales["snapshot_total_cliente_usd"],
                totales["total_cliente_bs"],
                orden_id,
            ),
        )
    return cursor.rowcount > 0


def marcar_items_incluidos_en_snapshot(cursor, orden_id):
    """Mision "recibos post-cobro": llamar SIEMPRE que una orden termine
    de cobrarse (cobro inicial o liquidacion de un pendiente
    incremental): TODOS los orden_items presentes en ese instante pasan
    a formar parte oficial del snapshot/recibo (incluido_en_snapshot=1).
    Cualquier item agregado DESPUES de este punto empieza en 0 (ver
    /agregar) hasta que se liquide con un cobro/cobro-pendiente
    posterior. Este flag responde "esta oficialmente incluido en el
    total vigente ahora mismo", no "a que cobro numero pertenece" -- por
    eso sigue siendo correcto sin importar cuantos ciclos
    cobrar->agregar->cobrar_pendiente se repitan."""
    cursor.execute(
        "UPDATE orden_items SET incluido_en_snapshot=1 WHERE orden_id=?",
        (orden_id,),
    )
