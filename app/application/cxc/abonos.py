"""
abonos.py (aplicacion)

Caso de uso "registrar un abono sobre una cuenta por cobrar existente"
(ruta /cuentas_por_cobrar/<id>/abono en web_app.py) y su variante de
pago masivo (un solo pago distribuido entre varias cuentas del mismo
cliente, manual o automaticamente de la deuda mas antigua a la mas
reciente -- /cuentas_por_cobrar/clientes/<id>/pago_masivo). Valida las
reglas de negocio (consistencia saldo/movimientos, estado de la
cuenta, moneda soportada, metodo y monto validos, tolerancia de
redondeo al saldar por completo) y delega la persistencia en
app.infrastructure.database.cxc (insertar_movimiento_abono_cxc /
actualizar_saldo_cxc / calcular_suma_movimientos_cxc).

Las dos funciones publicas (`registrar_abono_cuenta` y
`registrar_pago_masivo_cliente`) comparten el mismo nucleo de
validacion/escritura por cuenta (`_aplicar_abono_validado`) para no
duplicar las reglas de negocio: la unica diferencia real entre abonar
UNA cuenta y repartir un pago entre VARIAS es que la conversion de
moneda->USD se hace una sola vez sobre el monto TOTAL recibido (no una
vez por cuenta, para no arrastrar error de redondeo ni permitir que la
tasa cambie a mitad de la distribucion).

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
    actualizar_totales_pago_masivo_cxc,
    calcular_suma_movimientos_cxc,
    crear_pago_masivo_cxc,
    insertar_movimiento_abono_cxc,
    listar_cuentas_pendientes_cliente,
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


def _normalizar_metodo_y_convertir_a_usd(metodo_pago, monto_recibido, obtener_tasa_cobro, cursor):
    """Fase compartida de conversion de moneda: valida el metodo/monto
    recibidos y devuelve (metodo_pago_normalizado, moneda_pago,
    monto_pago_redondeado, tasa_movimiento, monto_usd). Se ejecuta UNA
    sola vez por pago (sea de una cuenta o repartido entre varias)."""
    metodo_pago = normalizar_metodo_pago(metodo_pago)
    if metodo_pago not in METODOS_PAGO_VALIDOS:
        raise ValueError("Metodo de pago invalido")

    monto_pago = a_float(monto_recibido)
    if monto_pago <= 0:
        raise ValueError("El monto del abono debe ser mayor a 0.")

    moneda_pago = moneda_pago_desde_metodo(metodo_pago)
    tasa_movimiento = None
    if moneda_pago == "USD":
        monto_usd = round(monto_pago, 2)
    elif moneda_pago == "BS":
        try:
            tasa_movimiento = obtener_tasa_cobro(cursor)
        except ValueError:
            raise ValueError("No hay una tasa de cambio valida para registrar el abono.")
        monto_usd = round(monto_pago / tasa_movimiento, 2)
    else:
        raise ValueError("Metodo de pago invalido")

    if monto_usd <= 0:
        raise ValueError("El monto del abono debe ser mayor a 0.")

    return metodo_pago, moneda_pago, round(monto_pago, 2), tasa_movimiento, monto_usd


def _aplicar_abono_validado(
    cursor,
    cuenta_id,
    abono_usd,
    moneda_pago,
    monto_pago,
    tasa_movimiento,
    metodo_pago,
    referencia,
    observacion,
    usuario_id,
    ahora_venezuela,
    formato_usd,
    referencia_externa_tipo=None,
    referencia_externa_id=None,
):
    """Nucleo compartido: valida que la cuenta pueda recibir `abono_usd`
    (consistencia, estado, moneda de saldo, no exceder el saldo) y
    escribe el movimiento + nuevo saldo. `abono_usd` ya viene calculado
    (una sola conversion de moneda por pago, ver
    `_normalizar_metodo_y_convertir_a_usd`)."""
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
        referencia_externa_tipo=referencia_externa_tipo,
        referencia_externa_id=referencia_externa_id,
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
    metodo_pago, moneda_pago, monto_pago, tasa_movimiento, abono_usd = (
        _normalizar_metodo_y_convertir_a_usd(metodo_pago, monto_recibido, obtener_tasa_cobro, cursor)
    )
    return _aplicar_abono_validado(
        cursor,
        cuenta_id,
        abono_usd,
        moneda_pago,
        monto_pago,
        tasa_movimiento,
        metodo_pago,
        referencia,
        observacion,
        usuario_id,
        ahora_venezuela,
        formato_usd,
    )


def distribuir_pago_automatico(cuentas_pendientes, monto_disponible_usd):
    """`cuentas_pendientes`: lista de (cuenta_id, saldo_pendiente) ya
    ordenada de la MAS ANTIGUA a la MAS RECIENTE (ver
    listar_cuentas_pendientes_cliente). Aplica `monto_disponible_usd` a
    cada cuenta en ese orden hasta agotarlo. Devuelve (distribucion,
    sobrante_usd) donde distribucion es una lista de (cuenta_id,
    monto_a_aplicar_usd); nunca asigna mas que el saldo de cada cuenta,
    asi que nunca puede dejar un saldo negativo."""
    distribucion = []
    restante = round(a_float(monto_disponible_usd), 2)
    for cuenta_id, saldo in cuentas_pendientes:
        if restante <= TOLERANCIA_COBRO:
            break
        saldo = round(a_float(saldo), 2)
        aplicar = round(min(saldo, restante), 2)
        if aplicar <= 0:
            continue
        distribucion.append((cuenta_id, aplicar))
        restante = round(restante - aplicar, 2)
    return distribucion, round(max(restante, 0.0), 2)


def registrar_pago_masivo_cliente(
    cursor,
    *,
    cliente_id,
    metodo_pago,
    monto_recibido,
    modo,
    cuentas_manual,
    referencia,
    observacion,
    usuario_id,
    obtener_tasa_cobro,
    ahora_venezuela,
    formato_usd,
    obtener_ultimo_id,
):
    """Registra UN pago y lo distribuye entre varias cuentas por cobrar
    pendientes del mismo cliente, dentro de la MISMA transaccion que ya
    administra la ruta (igual patron que /cobrar y /abono: esta funcion
    nunca hace commit/rollback). `modo`: "automatico" (de la deuda mas
    antigua a la mas reciente, hasta agotar el pago) o "manual"
    (`cuentas_manual`: lista de (cuenta_id, monto_usd) ya decidida por
    quien cobra). Cada abono resultante queda enlazado a una fila nueva
    en pagos_masivos_cxc (referencia_externa_tipo='pago_masivo') para
    poder explicar despues como se repartio. Si CUALQUIER cuenta de la
    distribucion falla su propia validacion (saldo insuficiente,
    inconsistencia, cuenta no pendiente), se levanta la misma
    ValueError que un abono individual -- nada de lo ya escrito en esta
    llamada debe persistir, lo cual logra la ruta haciendo rollback
    sobre la conexion completa."""
    metodo_pago, moneda_pago, monto_pago, tasa_movimiento, monto_total_usd = (
        _normalizar_metodo_y_convertir_a_usd(metodo_pago, monto_recibido, obtener_tasa_cobro, cursor)
    )

    if modo == "automatico":
        cuentas_pendientes = listar_cuentas_pendientes_cliente(cursor, cliente_id)
        distribucion, _sobrante_estimado = distribuir_pago_automatico(cuentas_pendientes, monto_total_usd)
    elif modo == "manual":
        distribucion = []
        total_manual = 0.0
        for cuenta_id, monto_usd in cuentas_manual or []:
            monto_usd = round(a_float(monto_usd), 2)
            if monto_usd <= 0:
                continue
            distribucion.append((cuenta_id, monto_usd))
            total_manual = round(total_manual + monto_usd, 2)
        if total_manual > monto_total_usd + TOLERANCIA_COBRO:
            raise ValueError(
                f"La suma de los montos seleccionados ({formato_usd(total_manual)}) "
                f"supera el pago recibido ({formato_usd(monto_total_usd)})."
            )
    else:
        raise ValueError("Modo de distribucion invalido.")

    if not distribucion:
        raise ValueError("No hay cuentas pendientes a las cuales aplicar este pago.")

    fecha = ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
    pago_masivo_id = crear_pago_masivo_cxc(
        cursor,
        obtener_ultimo_id,
        cliente_id=cliente_id,
        metodo_pago=metodo_pago,
        moneda_pago=moneda_pago,
        monto_pago=monto_pago,
        tasa_movimiento=tasa_movimiento,
        referencia=(referencia or "").strip(),
        observacion=(observacion or "").strip(),
        fecha=fecha,
        usuario_id=usuario_id,
        monto_total_usd=monto_total_usd,
    )

    resultados = []
    monto_aplicado_usd = 0.0
    for cuenta_id, monto_usd in distribucion:
        monto_pago_cuenta = round(monto_usd * tasa_movimiento, 2) if moneda_pago == "BS" else monto_usd
        resultado = _aplicar_abono_validado(
            cursor,
            cuenta_id,
            monto_usd,
            moneda_pago,
            monto_pago_cuenta,
            tasa_movimiento,
            metodo_pago,
            referencia,
            observacion,
            usuario_id,
            ahora_venezuela,
            formato_usd,
            referencia_externa_tipo="pago_masivo",
            referencia_externa_id=pago_masivo_id,
        )
        resultados.append(resultado)
        monto_aplicado_usd = round(monto_aplicado_usd + resultado["abono_usd"], 2)

    sobrante_usd = round(monto_total_usd - monto_aplicado_usd, 2)
    actualizar_totales_pago_masivo_cxc(
        cursor, pago_masivo_id, monto_aplicado_usd=monto_aplicado_usd, monto_sobrante_usd=sobrante_usd
    )

    return {
        "pago_masivo_id": pago_masivo_id,
        "distribucion": resultados,
        "monto_total_usd": monto_total_usd,
        "monto_aplicado_usd": monto_aplicado_usd,
        "monto_sobrante_usd": sobrante_usd,
    }
