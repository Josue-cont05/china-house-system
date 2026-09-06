"""
pendiente.py (aplicacion)

Casos de uso "cobrar el saldo pendiente de un consumo post-cobro"
(ruta /orden/<id>/cobrar_pendiente en web_app.py, mision "seguridad
financiera de agregados post-cobro"): Mesa 4 cobra $6, agrega $2 mas
antes de que la orden quede lista para retirar -> estas funciones
cobran SOLO esos $2, nunca borran ni recalculan el cobro anterior.

Ver `app.infrastructure.database.payments.calcular_pendiente_post_cobro`
para como se detecta el pendiente (solo lectura); este modulo decide
que escribir una vez que el usuario elige una de las dos acciones:

- `pagar_pendiente_ahora`: el cliente paga el pendiente completo ahora
  mismo. Se AGREGA (nunca se borra) un nuevo registro en `pagos` -- el
  cobro original permanece intacto.
- `dejar_pendiente_a_cliente`: el pendiente se registra en
  cuentas_por_cobrar (reutilizando la cuenta existente de la orden si
  ya tenia una, o creando una nueva si es la primera vez), exactamente
  el mismo motor ya usado por el cobro normal en modo parcial/credito.

Ambas levantan ValueError con un mensaje listo para mostrar al usuario
si la entrada no es valida; ninguna hace commit/rollback -- eso lo
decide el caller (la ruta), que es quien tiene ownership de la
transaccion completa (abre el cursor, decide cuando confirmar).

`formato_usd` y `obtener_ultimo_id` se reciben inyectados (siguen
definidos en web_app.py hoy) para no crear un import circular.
"""

from app.domain.sales.calculations import (
    _a_float as a_float,
    TOLERANCIA_COBRO,
    convertir_pago_equivalente,
    normalizar_metodo_pago,
)
from app.infrastructure.database.clientes import obtener_cliente_para_cxc
from app.infrastructure.database.cxc import agregar_cargo_cuenta_existente, crear_cuenta_por_cobrar_inicial
from app.infrastructure.database.payments import aplicar_totales_post_cobro, marcar_items_incluidos_en_snapshot
from app.shared.constants.system import METODOS_PAGO_VALIDOS


def pagar_pendiente_ahora(cursor, *, orden_id, metodo, monto, referencia, pendiente, fecha, formato_usd):
    metodo = normalizar_metodo_pago(metodo)
    if metodo not in METODOS_PAGO_VALIDOS:
        raise ValueError("Selecciona un metodo de pago valido")
    monto = a_float(monto)
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0")
    referencia = (referencia or "").strip()

    _pago_bs, pago_usd = convertir_pago_equivalente(metodo, monto, pendiente["tasa_actual"])
    if pago_usd + TOLERANCIA_COBRO < pendiente["pendiente_usd"]:
        raise ValueError(
            "El pago no cubre el saldo pendiente nuevo "
            f"({formato_usd(pendiente['pendiente_usd'])}). "
            "Usa 'Dejar pendiente a un cliente' si no se puede cobrar todo ahora."
        )

    cursor.execute(
        "INSERT INTO pagos (orden_id, metodo, monto, referencia, fecha) VALUES (?, ?, ?, ?, ?)",
        (orden_id, metodo, monto, referencia, fecha),
    )
    aplicar_totales_post_cobro(cursor, orden_id, pendiente["totales_actuales"])
    marcar_items_incluidos_en_snapshot(cursor, orden_id)


def dejar_pendiente_a_cliente(
    cursor,
    *,
    orden_id,
    cliente_id_form,
    cuenta_id_existente,
    pendiente,
    fecha,
    usuario_id,
    observacion,
    obtener_ultimo_id,
):
    cliente_cxc = obtener_cliente_para_cxc(cursor, cliente_id_form)
    if cuenta_id_existente is not None:
        agregar_cargo_cuenta_existente(
            cursor,
            cuenta_id_existente,
            pendiente["pendiente_usd"],
            fecha,
            usuario_id,
            observacion,
        )
    else:
        crear_cuenta_por_cobrar_inicial(
            cursor,
            orden_id,
            cliente_cxc[0],
            cliente_cxc[1],
            pendiente["pendiente_usd"],
            fecha,
            usuario_id,
            obtener_ultimo_id,
        )
    aplicar_totales_post_cobro(
        cursor,
        orden_id,
        pendiente["totales_actuales"],
        cliente_id=cliente_cxc[0],
        cliente_nombre=cliente_cxc[1],
    )
    marcar_items_incluidos_en_snapshot(cursor, orden_id)
