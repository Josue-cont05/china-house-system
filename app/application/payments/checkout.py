"""
checkout.py (aplicacion)

Caso de uso "cobrar una orden" (ruta /cobrar/<id> en web_app.py, POST).
La ruta sigue validando el formulario (modo de cobro, metodos, montos,
cliente para CxC, delivery -- logica de HTTP/re-render de formulario
que no es trivial de separar de `request.form` todavia); UNA VEZ que
esa validacion pasa, `ejecutar_cobro` hace TODAS las escrituras
financieras de un cobro dentro de la MISMA transaccion que ya abrio la
ruta: reemplaza los pagos, cierra la orden con su snapshot financiero
completo, marca el snapshot de recibos (mision "recibos post-cobro"),
genera la cuenta por cobrar inicial si aplica, genera el cargo de
delivery si aplica, deja constancia de auditoria si fue un recobro de
emergencia, y descuenta inventario.

Deliberadamente NO hace commit/rollback/close: eso lo decide el
caller (la ruta), que abrio la conexion y tiene ownership de la
transaccion completa (mismo patron que
app.application.cxc.abonos.registrar_abono_cuenta y
app.application.payments.pendiente). Si la orden ya no se puede cerrar
(otro proceso la cerro o archivo justo antes), levanta
OrdenYaCerradaOArchivadaError para que la ruta responda exactamente
igual que antes (mensaje plano, sin generar el resto de los efectos ni
propagar como error 500).

`crear_cuenta_por_cobrar_inicial`, `insertar_cargo_delivery`,
`emergencia_activa`, `registrar_auditoria_emergencia`,
`descontar_inventario_por_orden` y `obtener_ultimo_id` se reciben
inyectados. Los ultimos 5 siguen definidos en web_app.py hoy (evita un
import circular); `crear_cuenta_por_cobrar_inicial` YA vive en
app.infrastructure.database.cxc pero se inyecta igual a proposito: los
tests de atomicidad existentes (tests/test_sales_snapshot.py) hacen
`mock.patch("web_app.crear_cuenta_por_cobrar_inicial", ...)` para
forzar el rollback -- al recibirla como parametro que la ruta pasa
desde SU PROPIO namespace, ese patch sigue funcionando sin cambios
(la ruta evalua el nombre en web_app.__dict__ en el momento de la
llamada, que es exactamente lo que mock.patch reemplaza).

`usuario_nombre` (mision "sacar session del flujo de inventario"): la
ruta resuelve `usuario_activo()` (que lee `session`) ANTES de llamar
`ejecutar_cobro` y lo pasa como valor plano, exactamente igual que ya
hacia con `usuario_id=session.get("usuario_id")`. Esta funcion nunca
toca `session` directamente -- solo reenvia el nombre a
`descontar_inventario_por_orden`, que lo necesita para el registro de
`movimientos_inventario` (columna `usuario`, texto libre para reportes,
no una FK)."""

from app.domain.sales.calculations import TOLERANCIA_COBRO
from app.infrastructure.database.payments import marcar_items_incluidos_en_snapshot


class OrdenYaCerradaOArchivadaError(RuntimeError):
    pass


def ejecutar_cobro(
    cursor,
    *,
    orden_id,
    fecha,
    fecha_cobro,
    totales_cobro,
    cliente_id_orden,
    cliente_nombre_orden,
    insertar_pago_1,
    metodo1,
    monto1,
    ref1,
    insertar_pago_2,
    metodo2,
    monto2,
    ref2,
    saldo_cxc_usd,
    cliente_cxc,
    usuario_id,
    usuario_nombre,
    estado_previo,
    repartidor_delivery_cobro,
    obtener_ultimo_id,
    crear_cuenta_por_cobrar_inicial,
    insertar_cargo_delivery,
    emergencia_activa,
    registrar_auditoria_emergencia,
    descontar_inventario_por_orden,
):
    cursor.execute("DELETE FROM pagos WHERE orden_id = ?", (orden_id,))

    if insertar_pago_1:
        cursor.execute(
            """
            INSERT INTO pagos (orden_id, metodo, monto, referencia, fecha)
            VALUES (?, ?, ?, ?, ?)
            """,
            (orden_id, metodo1, monto1, ref1, fecha),
        )

    if insertar_pago_2:
        cursor.execute(
            """
            INSERT INTO pagos (orden_id, metodo, monto, referencia, fecha)
            VALUES (?, ?, ?, ?, ?)
            """,
            (orden_id, metodo2, monto2, ref2, fecha),
        )

    cursor.execute(
        """
        UPDATE ordenes
        SET estado='cerrada',
            descuento=?,
            fecha_venta=?,
            fecha_cobro=?,
            tasa_cobro=?,
            subtotal_usd=?,
            descuento_bs_snapshot=?,
            total_usd=?,
            total_bs=?,
            venta_restaurante_usd=?,
            delivery_usd=?,
            total_cliente_usd=?,
            total_cliente_bs=?,
            cliente_id=?,
            cliente=?
        WHERE id=?
          AND cierre_id IS NULL
          AND estado IN ('abierta', 'en cocina', 'listo', 'cerrada')
        """,
        (
            totales_cobro["descuento_bs"],
            fecha,
            fecha_cobro,
            totales_cobro["tasa"],
            totales_cobro["subtotal_snapshot_usd"],
            totales_cobro["descuento_bs"],
            totales_cobro["total_usd"],
            totales_cobro["total_bs"],
            totales_cobro["snapshot_venta_restaurante_usd"],
            totales_cobro["snapshot_delivery_usd"],
            totales_cobro["snapshot_total_cliente_usd"],
            totales_cobro["total_cliente_bs"],
            cliente_id_orden,
            cliente_nombre_orden,
            orden_id,
        ),
    )

    if getattr(cursor, "rowcount", 0) == 0:
        raise OrdenYaCerradaOArchivadaError(
            "Esta orden ya fue cerrada o pertenece a un cierre de jornada"
        )

    marcar_items_incluidos_en_snapshot(cursor, orden_id)

    if saldo_cxc_usd > TOLERANCIA_COBRO:
        crear_cuenta_por_cobrar_inicial(
            cursor,
            orden_id,
            cliente_cxc[0],
            cliente_cxc[1],
            saldo_cxc_usd,
            fecha,
            usuario_id,
            obtener_ultimo_id,
        )

    if totales_cobro["delivery_usd"] > TOLERANCIA_COBRO:
        insertar_cargo_delivery(
            cursor,
            orden_id,
            repartidor_delivery_cobro,
            totales_cobro["delivery_usd"],
            fecha,
            usuario_id,
            obtener_ultimo_id,
        )

    if estado_previo == "cerrada" and emergencia_activa(orden_id):
        registrar_auditoria_emergencia(
            cursor,
            orden_id,
            "volver_a_cobrar_emergencia",
            "Pagos reemplazados durante edicion de emergencia",
        )

    descontar_inventario_por_orden(cursor, orden_id, usuario_nombre)
