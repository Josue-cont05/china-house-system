"""
abonos.py (aplicacion)

Caso de uso "registrar un abono sobre una cuenta por cobrar existente"
(ruta /cuentas_por_cobrar/<id>/abono en web_app.py). Valida las reglas
de negocio (consistencia saldo/movimientos, estado de la cuenta, moneda
soportada, metodo y monto validos, tolerancia de redondeo al saldar por
completo) y delega la persistencia en
app.infrastructure.database.cxc (insertar_movimiento_abono_cxc /
actualizar_saldo_cxc / calcular_suma_movimientos_cxc).

`obtener_tasa_cobro`, `ahora_venezuela` y `formato_usd` se reciben
inyectados (siguen definidos en web_app.py hoy; inyectarlos evita un
import circular sin bloquear esta extraccion en que esos utilitarios
tengan su propio modulo, tarea aparte de "SQL/helpers residuales")."""

from app.domain.sales.calculations import (
    _a_float as a_float,
    TOLERANCIA_COBRO,
    normalizar_metodo_pago,
)
from app.infrastructure.database.cxc import (
    actualizar_saldo_cxc,
    calcular_suma_movimientos_cxc,
    insertar_movimiento_abono_cxc,
)
from app.shared.constants.system import METODOS_PAGO_VALIDOS


def metodo_pago_es_usd(metodo):
    return normalizar_metodo_pago(metodo) == "usd"


def metodo_pago_es_bs(metodo):
    return normalizar_metodo_pago(metodo) in ("punto_venta", "bs_pago_movil", "bs_efectivo")


def moneda_pago_desde_metodo(metodo):
    metodo = normalizar_metodo_pago(metodo)
    if metodo_pago_es_usd(metodo):
        return "USD"
    if metodo_pago_es_bs(metodo):
        return "BS"
    return ""


def registrar_abono_cuenta(
    cursor,
    cuenta_id,
    metodo_pago,
    monto_recibido,
    referencia,
    observacion,
    usuario_id,
    obtener_tasa_cobro,
    ahora_venezuela,
    formato_usd,
):
    cursor.execute(
        """
        SELECT id, saldo_pendiente, estado, moneda_saldo, cliente_nombre_snapshot
        FROM cuentas_por_cobrar
        WHERE id=?
        """,
        (cuenta_id,),
    )
    cuenta = cursor.fetchone()
    if not cuenta:
        raise ValueError("Cuenta por cobrar no encontrada")

    cuenta_id, saldo_actual, estado, moneda_saldo, cliente_nombre = cuenta
    saldo_actual = round(a_float(saldo_actual), 2)
    suma_movimientos = calcular_suma_movimientos_cxc(cursor, cuenta_id)

    if abs(round(saldo_actual - suma_movimientos, 2)) > 0.01:
        raise ValueError("La cuenta tiene una inconsistencia entre saldo y movimientos. No se puede registrar el abono.")
    if estado != "pendiente" or saldo_actual <= TOLERANCIA_COBRO:
        raise ValueError("Solo se pueden registrar abonos en cuentas pendientes con saldo.")
    if (moneda_saldo or "USD") != "USD":
        raise ValueError("La moneda de saldo de la cuenta no esta soportada para abonos.")

    metodo_pago = normalizar_metodo_pago(metodo_pago)
    if metodo_pago not in METODOS_PAGO_VALIDOS:
        raise ValueError("Metodo de pago invalido")

    monto_pago = a_float(monto_recibido)
    if monto_pago <= 0:
        raise ValueError("El monto del abono debe ser mayor a 0.")

    moneda_pago = moneda_pago_desde_metodo(metodo_pago)
    tasa_movimiento = None
    if moneda_pago == "USD":
        abono_usd = round(monto_pago, 2)
    elif moneda_pago == "BS":
        try:
            tasa_movimiento = obtener_tasa_cobro(cursor)
        except ValueError:
            raise ValueError("No hay una tasa de cambio valida para registrar el abono.")
        abono_usd = round(monto_pago / tasa_movimiento, 2)
    else:
        raise ValueError("Metodo de pago invalido")

    if abono_usd <= 0:
        raise ValueError("El monto del abono debe ser mayor a 0.")
    if abono_usd > saldo_actual + TOLERANCIA_COBRO:
        raise ValueError(f"El abono supera el saldo pendiente de {formato_usd(saldo_actual)}.")

    if abs(abono_usd - saldo_actual) <= TOLERANCIA_COBRO:
        abono_usd = saldo_actual

    nuevo_saldo = round(max(saldo_actual - abono_usd, 0.0), 2)
    nuevo_estado = "pagada" if nuevo_saldo <= TOLERANCIA_COBRO else "pendiente"
    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    observacion = (observacion or "").strip()
    referencia = (referencia or "").strip()

    insertar_movimiento_abono_cxc(
        cursor,
        cuenta_id,
        -abono_usd,
        moneda_pago,
        round(monto_pago, 2),
        tasa_movimiento,
        metodo_pago,
        referencia,
        fecha,
        usuario_id,
        observacion,
    )
    actualizar_saldo_cxc(cursor, cuenta_id, nuevo_saldo, nuevo_estado)

    return {
        "cuenta_id": cuenta_id,
        "cliente": cliente_nombre,
        "saldo_anterior": saldo_actual,
        "abono_usd": abono_usd,
        "nuevo_saldo": nuevo_saldo,
        "estado": nuevo_estado,
        "moneda_pago": moneda_pago,
        "monto_pago": round(monto_pago, 2),
        "tasa_movimiento": tasa_movimiento,
        "fecha": fecha,
    }
