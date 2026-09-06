"""
lifecycle.py (aplicacion)

Caso de uso "eliminar una orden completa" (ruta
/eliminar_orden/<orden_id> en web_app.py, ya protegida por clave de
supervisor + permiso admin en la ruta antes de llegar aqui). Borra la
orden y todo lo que le pertenece exclusivamente (items, pagos) -- nunca
se llama sobre una orden archivada o que ya no cumple
`puede_eliminar_orden` (app/domain/sales/order_states.py).

Levanta ValueError con un mensaje listo para mostrar cuando la
operacion no es valida; no hace commit/rollback/close (ownership de la
transaccion sigue siendo de la ruta)."""

from app.domain.sales.order_states import orden_archivada, puede_eliminar_orden


def eliminar_orden_completa(cursor, *, orden_id):
    cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=?", (orden_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Orden no encontrada")

    estado, cierre_id = row
    if orden_archivada(cierre_id):
        raise ValueError("No se puede eliminar una orden archivada")

    if not puede_eliminar_orden(estado, cierre_id):
        raise ValueError("No se puede eliminar esta orden")

    cursor.execute("DELETE FROM orden_items WHERE orden_id=?", (orden_id,))
    cursor.execute("DELETE FROM pagos WHERE orden_id=?", (orden_id,))
    cursor.execute("DELETE FROM ordenes WHERE id=?", (orden_id,))
