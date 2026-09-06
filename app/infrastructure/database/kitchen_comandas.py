from app.application.kitchen.comandas import (
    ESTADO_COMANDA_EN_COCINA,
    ESTADO_COMANDA_LISTO,
    ORIGEN_COMANDA_MANUAL,
    ORIGEN_COMANDA_SELF_ORDERING,
    OrdenComandaNoExiste,
    OrdenComandaSinItems,
    ResultadoComanda,
)
from app.domain.sales.print_queue import ROL_COCINA, TIPO_JOB_COMANDA
from app.domain.sales.service_alerts import (
    TIPO_BEBIDA_ADICIONAL,
    agrupar_items_alerta,
    debe_evaluar_alerta,
    separar_cantidad,
)
from app.infrastructure.database.print_queue import crear_job_en_cursor
from app.infrastructure.database.service_alerts import crear_alerta_en_cursor


class SqlKitchenComandaRepository:
    def __init__(self, connection_factory, last_id_getter, numero_orden_provider):
        self._connection_factory = connection_factory
        self._last_id_getter = last_id_getter
        self._numero_orden_provider = numero_orden_provider

    def crear_manual_para_pendientes(self, orden_id, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            numero_reserva = self._numero_si_hace_falta(cursor, orden_id)
            item_ids = _ids_items_sin_comanda(cursor, orden_id)
            if not item_ids:
                raise OrdenComandaSinItems("No hay items pendientes para enviar a cocina.")
            resultado = crear_comanda_en_cursor(
                cursor,
                self._last_id_getter,
                orden_id=orden_id,
                origen=ORIGEN_COMANDA_MANUAL,
                self_order_request_id=None,
                orden_item_ids=item_ids,
                fecha=fecha,
                numero_orden_reserva=numero_reserva,
            )
            conn.commit()
            return resultado
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def marcar_lista(self, comanda_id, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT orden_id
                FROM orden_comandas
                WHERE id=?
                LIMIT 1
                """,
                (comanda_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise OrdenComandaNoExiste("Comanda no encontrada.")

            orden_id = row[0]
            cursor.execute(
                """
                UPDATE orden_comandas
                SET estado=?, fecha_listo=?
                WHERE id=?
                """,
                (ESTADO_COMANDA_LISTO, fecha, comanda_id),
            )
            sincronizar_estado_orden_cursor(cursor, orden_id)
            conn.commit()
            return orden_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def marcar_todas_listas_de_orden(self, orden_id, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE orden_comandas
                SET estado=?, fecha_listo=?
                WHERE orden_id=? AND estado=?
                """,
                (ESTADO_COMANDA_LISTO, fecha, orden_id, ESTADO_COMANDA_EN_COCINA),
            )
            sincronizar_estado_orden_cursor(cursor, orden_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reimprimir_ultima_comanda_de_orden(self, orden_id, token, fecha):
        """Marca la ultima comanda de la orden para reimpresion Y crea un
        print_job NUEVO (event_key distinto, mismo evento nunca se
        confunde con el original) en la MISMA transaccion. El job usa
        el acumulado de items ya enviados (no solo el ultimo lote) y las
        horas HISTORICAS originales de esa comanda, nunca la hora de la
        reimpresion."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, secuencia, fecha_creacion
                FROM orden_comandas
                WHERE orden_id=?
                ORDER BY secuencia DESC, id DESC
                LIMIT 1
                """,
                (orden_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                return False

            comanda_id, secuencia, fecha_agregado = row
            cursor.execute(
                """
                UPDATE orden_comandas
                SET reimpresion_token=?
                WHERE id=?
                """,
                (token, comanda_id),
            )
            _crear_print_job_reimpresion_en_cursor(
                cursor,
                orden_id=orden_id,
                comanda_id=comanda_id,
                secuencia=secuencia,
                fecha_agregado=fecha_agregado,
                token=token,
                fecha_evento=fecha,
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reimprimir_comanda(self, comanda_id, token, fecha):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT orden_id, secuencia, fecha_creacion FROM orden_comandas WHERE id=?",
                (comanda_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                return False
            orden_id, secuencia, fecha_agregado = row

            cursor.execute(
                """
                UPDATE orden_comandas
                SET reimpresion_token=?
                WHERE id=?
                """,
                (token, comanda_id),
            )
            afectadas = cursor.rowcount
            if afectadas > 0:
                _crear_print_job_reimpresion_en_cursor(
                    cursor,
                    orden_id=orden_id,
                    comanda_id=comanda_id,
                    secuencia=secuencia,
                    fecha_agregado=fecha_agregado,
                    token=token,
                    fecha_evento=fecha,
                )
            conn.commit()
            return afectadas > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def crear_reimpresion_legacy_job(self, orden_id, token, fecha):
        """Caso legacy (mision seccion 1, listar_ordenes_legacy_cocina_sin_comanda):
        una orden con reimpresion_token puesto directamente en `ordenes`
        porque nunca tuvo fila en orden_comandas (de antes de que
        existiera ese tracking). Usa TODOS los items de la orden (no hay
        nocion de lotes) y, a falta de fecha_creacion historica de
        comanda, usa `ordenes.fecha_hora` como mejor aproximacion
        disponible de "cuando se envio" - documentado: es la unica
        fecha que existe para este caso legacy."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT o.numero_orden, o.tipo, o.referencia, o.cliente,
                       COALESCE(o.observacion, ''), o.estado, o.fecha_hora, u.nombre
                FROM ordenes o
                LEFT JOIN usuarios u ON o.usuario_id = u.id
                WHERE o.id=?
                LIMIT 1
                """,
                (orden_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                return False
            numero_orden, tipo, referencia, cliente, observacion, estado_orden, fecha_hora, usuario = row

            items_crudos = _items_crudos_de_orden_completa(cursor, orden_id)
            payload = {
                "id": orden_id,
                "comanda_id": None,
                "numero": numero_orden,
                "secuencia": 0,
                "tipo": tipo,
                "cliente": cliente,
                "referencia": referencia,
                "usuario": usuario,
                "estado": estado_orden,
                "estado_comanda": "legacy",
                "observacion": observacion,
                "reimpresion_token": token,
                "items_crudos": items_crudos,
                "hora_pedido": fecha_hora,
                "hora_agregado": fecha_hora,
            }
            crear_job_en_cursor(
                cursor,
                event_key=f"{orden_id}-{token}",
                job_type=TIPO_JOB_COMANDA,
                required_role=ROL_COCINA,
                payload=payload,
                fecha=fecha,
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def listar_comandas_cocina(self):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT c.id, c.orden_id, o.numero_orden, c.secuencia, o.tipo, o.referencia,
                       o.fecha_hora, u.nombre, COALESCE(o.observacion, ''),
                       c.estado, c.reimpresion_token, c.origen, o.cliente, o.estado
                FROM orden_comandas c
                JOIN ordenes o ON o.id = c.orden_id
                LEFT JOIN usuarios u ON o.usuario_id = u.id
                WHERE (
                    c.estado = ?
                    AND o.cierre_id IS NULL
                    AND o.estado IN ('en cocina', 'listo')
                )
                   OR (
                    c.reimpresion_token IS NOT NULL
                    AND o.cierre_id IS NULL
                    AND o.estado IN ('en cocina', 'listo', 'cerrada')
                   )
                ORDER BY o.numero_orden ASC, c.secuencia ASC, c.id ASC
                """,
                (ESTADO_COMANDA_EN_COCINA,),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def listar_ordenes_legacy_cocina_sin_comanda(self):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT o.id, o.numero_orden, o.tipo, o.referencia, o.fecha_hora, u.nombre,
                       COALESCE(o.observacion, ''), o.reimpresion_token, o.cliente, o.estado
                FROM ordenes o
                LEFT JOIN usuarios u ON o.usuario_id = u.id
                WHERE (
                    o.estado = 'en cocina'
                    OR (
                        o.reimpresion_token IS NOT NULL
                        AND o.cierre_id IS NULL
                        AND o.estado IN ('en cocina', 'listo', 'cerrada')
                    )
                )
                  AND NOT EXISTS (
                    SELECT 1 FROM orden_comandas c WHERE c.orden_id = o.id
                  )
                ORDER BY o.numero_orden ASC, o.fecha_hora ASC
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def listar_pedidos_despacho(self):
        """Pedidos que Monica todavia debe atender/armar en Despacho.

        CORRECCION (mision "correccion semantica de Despacho"):
        FACTURADA, COBRADA y CERRADA (financiero) NO son LISTA PARA
        RETIRAR. La UNICA condicion que retira una orden de esta lista
        es listo_despacho_at IS NOT NULL -- nunca estado='cerrada',
        nunca facturar, nunca cobro. Una orden que ya entro a cocina, se
        factura y se cobra sigue aqui hasta que Monica pulse LISTO PARA
        RETIRAR/DELIVERY. Ese boton NUNCA significa "el cliente ya lo
        recibio" -- solo que Monica termino de armarlo y alguien puede
        retirarlo (mesonero, cliente de Pick Up, o el conductor de
        Delivery).

        La UNICA excepcion es cierre_id (archivo de jornada): auditado
        cerrar_jornada() (web_app.py) rechaza archivar mientras exista
        CUALQUIER orden no-cerrada (estado != 'cerrada'), asi que
        cierre_id solo se asigna, una vez al dia, a ordenes que un
        supervisor ya cerro deliberadamente como parte del cierre
        contable del dia -- no es un estado financiero de la orden
        (como cobrar) ni significa "anulada", pero representa que ese
        dia de operacion ya se dio por terminado. Sin este limite,
        agregar listo_despacho_at a una base de datos en produccion con
        historial (ordenes de dias/meses anteriores, todas con
        listo_despacho_at NULL por ser una columna nueva) resucitaria de
        golpe todo ese historial en la pantalla de Monica. Ordenes del
        dia en curso (cierre_id IS NULL) siguen visibles pase lo que
        pase con facturar/cobro/estado, exactamente como pide la
        correccion.

        Un renglon por ORDEN (no por lote de cocina) -- a diferencia de
        listar_comandas_cocina(), que es por-comanda. Mas antigua
        primero, usando SIEMPRE la hora historica de envio a cocina
        (secuencia 0), nunca 'ahora'. El indicador EN COCINA/LISTO se
        calcula de orden_comandas.estado directamente (nunca de
        ordenes.estado, que cobrar() sobreescribe a 'cerrada' y por
        tanto deja de reflejar si la cocina ya termino)."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT o.id, o.numero_orden, o.tipo, o.referencia, o.cliente,
                       o.estado, COALESCE(c0.fecha_creacion, o.fecha_hora) AS hora_envio,
                       COALESCE(o.observacion, ''),
                       COALESCE(
                           (SELECT CASE
                               WHEN COUNT(*) = SUM(CASE WHEN c.estado = 'listo' THEN 1 ELSE 0 END)
                               THEN 1 ELSE 0
                            END
                            FROM orden_comandas c
                            WHERE c.orden_id = o.id),
                           0
                       ) AS todas_comandas_listas
                FROM ordenes o
                LEFT JOIN orden_comandas c0 ON c0.orden_id = o.id AND c0.secuencia = 0
                WHERE o.cierre_id IS NULL
                  AND o.listo_despacho_at IS NULL
                  AND (
                    EXISTS (SELECT 1 FROM orden_comandas c WHERE c.orden_id = o.id)
                    OR o.estado IN ('en cocina', 'listo')
                  )
                ORDER BY hora_envio ASC, o.id ASC
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def marcar_listo_para_retirar(self, orden_id, usuario, fecha):
        """Idempotente: si la orden ya tenia listo_despacho_at, no
        cambia nada y devuelve False (dos clicks / dos usuarios no
        producen dos eventos). NO toca facturar/estado/cierre_id/pagos
        -- LISTO PARA RETIRAR es un concepto operativo de Despacho, no
        financiero, y tampoco significa "el cliente ya lo recibio" (ver
        mision "correccion semantica de Despacho": no mezclar con
        cobrado/cerrado/pagado/entregado-al-cliente)."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE ordenes
                SET listo_despacho_at=?, listo_despacho_por=?
                WHERE id=? AND cierre_id IS NULL AND listo_despacho_at IS NULL
                """,
                (fecha, usuario, orden_id),
            )
            afectadas = cursor.rowcount
            conn.commit()
            return afectadas > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def obtener_items_comanda(self, comanda_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oi.producto, COALESCE(oi.indicacion, '')
                FROM orden_comanda_items ci
                JOIN orden_items oi ON oi.id = ci.orden_item_id
                WHERE ci.comanda_id=?
                ORDER BY ci.id ASC
                """,
                (comanda_id,),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def obtener_items_enviados_de_orden(self, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oi.producto, COALESCE(oi.indicacion, '')
                FROM orden_comanda_items ci
                JOIN orden_comandas c ON c.id = ci.comanda_id
                JOIN orden_items oi ON oi.id = ci.orden_item_id
                WHERE c.orden_id=?
                ORDER BY c.secuencia ASC, ci.id ASC
                """,
                (orden_id,),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def obtener_items_orden(self, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT producto, COALESCE(indicacion, '')
                FROM orden_items
                WHERE orden_id=?
                ORDER BY id ASC
                """,
                (orden_id,),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def limpiar_tokens_reimpresion(self, comanda_ids):
        if not comanda_ids:
            return
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in comanda_ids)
            cursor.execute(
                f"""
                UPDATE orden_comandas
                SET reimpresion_token=NULL
                WHERE id IN ({placeholders})
                """,
                comanda_ids,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def limpiar_tokens_reimpresion_legacy(self, orden_ids):
        if not orden_ids:
            return
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in orden_ids)
            cursor.execute(
                f"""
                UPDATE ordenes
                SET reimpresion_token=NULL
                WHERE id IN ({placeholders})
                """,
                orden_ids,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _numero_si_hace_falta(self, cursor, orden_id):
        cursor.execute(
            """
            SELECT numero_orden
            FROM ordenes
            WHERE id=? AND cierre_id IS NULL
            LIMIT 1
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise OrdenComandaNoExiste("Orden no encontrada.")
        return self._numero_orden_provider() if row[0] is None else row[0]


def crear_comanda_en_cursor(
    cursor,
    last_id_getter,
    *,
    orden_id,
    origen,
    self_order_request_id,
    orden_item_ids,
    fecha,
    numero_orden_reserva,
):
    if not orden_item_ids:
        raise OrdenComandaSinItems("No hay items para comanda.")

    cursor.execute(
        """
        SELECT o.numero_orden, o.tipo, o.referencia, o.cliente,
               COALESCE(o.observacion, ''), o.estado, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=? AND o.cierre_id IS NULL
        LIMIT 1
        """,
        (orden_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise OrdenComandaNoExiste("Orden no encontrada.")
    numero_orden_actual, tipo, referencia, cliente, observacion, estado_orden, usuario_nombre = row

    numero_orden = numero_orden_actual if numero_orden_actual is not None else numero_orden_reserva
    cursor.execute(
        """
        UPDATE ordenes
        SET numero_orden=?
        WHERE id=? AND numero_orden IS NULL
        """,
        (numero_orden, orden_id),
    )

    secuencia = _reservar_secuencia_comanda(cursor, orden_id)

    cursor.execute(
        """
        INSERT INTO orden_comandas (
            orden_id, secuencia, origen, self_order_request_id, estado,
            fecha_creacion, fecha_listo, reimpresion_token
        )
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        (
            orden_id,
            secuencia,
            origen,
            self_order_request_id,
            ESTADO_COMANDA_EN_COCINA,
            fecha,
        ),
    )
    comanda_id = last_id_getter(cursor, "orden_comandas")

    for item_id in orden_item_ids:
        cursor.execute(
            """
            INSERT INTO orden_comanda_items (comanda_id, orden_item_id)
            VALUES (?, ?)
            """,
            (comanda_id, item_id),
        )

    sincronizar_estado_orden_cursor(cursor, orden_id)

    hora_pedido = fecha if secuencia == 0 else _hora_pedido_de_orden(cursor, orden_id)
    payload = {
        "id": orden_id,
        "comanda_id": comanda_id,
        "numero": int(numero_orden),
        "secuencia": secuencia,
        "tipo": tipo,
        "cliente": cliente,
        "referencia": referencia,
        "usuario": usuario_nombre,
        "estado": estado_orden,
        "estado_comanda": ESTADO_COMANDA_EN_COCINA,
        "observacion": observacion,
        "reimpresion_token": None,
        "items_crudos": _items_crudos_por_ids(cursor, orden_item_ids),
        "hora_pedido": hora_pedido,
        "hora_agregado": fecha,
    }
    crear_job_en_cursor(
        cursor,
        event_key=f"comanda-{comanda_id}-base",
        job_type=TIPO_JOB_COMANDA,
        required_role=ROL_COCINA,
        payload=payload,
        fecha=fecha,
    )

    # La alerta de servicio es un EFECTO ADICIONAL (mision Despacho,
    # seccion "bebidas": nunca debe sustituir ni condicionar la comanda
    # normal). Se aisla en su propio SAVEPOINT a proposito: un fallo aqui
    # (dato inesperado, condicion de carrera, lo que sea) NUNCA debe
    # poder deshacer la comanda/print_job de cocina que YA se creo
    # arriba -- perder la alerta es tolerable, perder el plato no.
    #
    # Un try/except de Python por si solo NO basta en PostgreSQL: si el
    # INSERT de la alerta falla, la transaccion queda "aborted" y CUALQUIER
    # sentencia posterior en el mismo commit() (incluida la que ya crearia
    # la comanda/print_job) se pierde de forma silenciosa (Postgres
    # convierte un COMMIT sobre una transaccion abortada en un ROLLBACK).
    # SAVEPOINT + ROLLBACK TO SAVEPOINT es sintaxis SQL estandar soportada
    # por sqlite3 y psycopg2 por igual, y aisla el fallo sin tocar el
    # resto de la transaccion en curso.
    cursor.execute("SAVEPOINT alerta_servicio")
    try:
        _evaluar_alerta_servicio(
            cursor,
            orden_id=orden_id,
            numero_orden=int(numero_orden),
            referencia=referencia,
            tipo_orden=tipo,
            secuencia=secuencia,
            comanda_id=comanda_id,
            items_crudos=payload["items_crudos"],
            fecha=fecha,
        )
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT alerta_servicio")
        print(
            f"ADVERTENCIA: no se pudo evaluar/crear alerta de servicio "
            f"para comanda {comanda_id} (orden {orden_id}): {exc}"
        )
    else:
        cursor.execute("RELEASE SAVEPOINT alerta_servicio")

    return ResultadoComanda(
        comanda_id=comanda_id,
        orden_id=orden_id,
        numero_orden=int(numero_orden),
        secuencia=secuencia,
        estado=ESTADO_COMANDA_EN_COCINA,
    )


def _evaluar_alerta_servicio(
    cursor,
    *,
    orden_id,
    numero_orden,
    referencia,
    tipo_orden,
    secuencia,
    comanda_id,
    items_crudos,
    fecha,
):
    """Crea (si corresponde) UNA alerta de servicio para Mesa cuando este
    lote es incremental (secuencia>0) y trae items clasificados para
    atencion de despacho (categorias.requiere_atencion_despacho=1). Se
    llama desde el MISMO hook que ya comparten el flujo manual
    (/enviar_cocina) y self-ordering, asi ambos caminos producen
    exactamente la misma clase de alerta sin logica duplicada.

    No es un error si no se genera alerta: la mayoria de los lotes
    incrementales (comida agregada, o Pick Up/Delivery) simplemente no
    califican."""
    if not debe_evaluar_alerta(tipo_orden, secuencia):
        return

    nombres_alerta = [
        producto
        for producto, _indicacion in items_crudos
        if _categoria_requiere_despacho(cursor, producto)
    ]
    if not nombres_alerta:
        return

    crear_alerta_en_cursor(
        cursor,
        event_key=f"alerta-comanda-{comanda_id}",
        orden_id=orden_id,
        tipo=TIPO_BEBIDA_ADICIONAL,
        payload={
            "numero": numero_orden,
            "referencia": referencia,
            "items": agrupar_items_alerta(nombres_alerta),
        },
        fecha=fecha,
    )


def _categoria_requiere_despacho(cursor, nombre_producto_crudo):
    """True si `nombre_producto_crudo` (tal como quedo guardado en
    orden_items.producto, puede traer prefijo 'Nx ') corresponde HOY a
    un producto activo cuya categoria esta marcada
    requiere_atencion_despacho=1. Un producto que ya no existe o que
    cambio de nombre (p.ej. vino dentro de un combo, cuyo texto no es un
    nombre de producto exacto) simplemente no clasifica -- no se asume
    nada por texto/substring."""
    _cantidad, nombre = separar_cantidad(nombre_producto_crudo)
    if not nombre:
        return False
    cursor.execute(
        """
        SELECT COALESCE(c.requiere_atencion_despacho, 0)
        FROM productos p
        JOIN categorias c ON c.id = p.categoria_id
        WHERE p.nombre = ?
        LIMIT 1
        """,
        (nombre,),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def _hora_pedido_de_orden(cursor, orden_id):
    cursor.execute(
        """
        SELECT fecha_creacion FROM orden_comandas
        WHERE orden_id=? AND secuencia=0
        LIMIT 1
        """,
        (orden_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _items_crudos_por_ids(cursor, orden_item_ids):
    """Items (producto, indicacion) CRUDOS -- sin agrupar/formatear -- en
    el mismo orden que `orden_item_ids`. El formateo para el papel
    (agrupar_items_comanda) se aplica luego, en el momento del claim,
    en web_app.py (ver print_queue.py de infraestructura para el porque
    no se hace aqui)."""
    if not orden_item_ids:
        return []
    placeholders = ",".join("?" for _ in orden_item_ids)
    cursor.execute(
        f"""
        SELECT id, producto, COALESCE(indicacion, '')
        FROM orden_items
        WHERE id IN ({placeholders})
        """,
        orden_item_ids,
    )
    filas = {row[0]: [row[1], row[2]] for row in cursor.fetchall()}
    return [filas[item_id] for item_id in orden_item_ids if item_id in filas]


def _items_crudos_acumulados_de_orden(cursor, orden_id):
    cursor.execute(
        """
        SELECT oi.producto, COALESCE(oi.indicacion, '')
        FROM orden_comanda_items ci
        JOIN orden_comandas c ON c.id = ci.comanda_id
        JOIN orden_items oi ON oi.id = ci.orden_item_id
        WHERE c.orden_id=?
        ORDER BY c.secuencia ASC, ci.id ASC
        """,
        (orden_id,),
    )
    return [[p, i] for p, i in cursor.fetchall()]


def _items_crudos_de_orden_completa(cursor, orden_id):
    cursor.execute(
        """
        SELECT producto, COALESCE(indicacion, '')
        FROM orden_items
        WHERE orden_id=?
        ORDER BY id ASC
        """,
        (orden_id,),
    )
    return [[p, i] for p, i in cursor.fetchall()]


def _crear_print_job_reimpresion_en_cursor(
    cursor, *, orden_id, comanda_id, secuencia, fecha_agregado, token, fecha_evento
):
    """Job de reimpresion: mismo evento nunca se confunde con el
    original (event_key distinto), usa el acumulado de items YA
    enviados (no solo el ultimo lote, igual que el comportamiento actual
    de /ordenes_cocina), y conserva las horas HISTORICAS de la comanda
    original -- nunca la hora en que se pidio la reimpresion."""
    cursor.execute(
        """
        SELECT o.numero_orden, o.tipo, o.referencia, o.cliente,
               COALESCE(o.observacion, ''), o.estado, u.nombre
        FROM ordenes o
        LEFT JOIN usuarios u ON o.usuario_id = u.id
        WHERE o.id=?
        LIMIT 1
        """,
        (orden_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise OrdenComandaNoExiste("Orden no encontrada.")
    numero_orden, tipo, referencia, cliente, observacion, estado_orden, usuario_nombre = row

    hora_pedido = fecha_agregado if secuencia == 0 else _hora_pedido_de_orden(cursor, orden_id)
    payload = {
        "id": orden_id,
        "comanda_id": comanda_id,
        "numero": numero_orden,
        "secuencia": secuencia,
        "tipo": tipo,
        "cliente": cliente,
        "referencia": referencia,
        "usuario": usuario_nombre,
        "estado": estado_orden,
        "estado_comanda": ESTADO_COMANDA_EN_COCINA,
        "observacion": observacion,
        "reimpresion_token": token,
        "items_crudos": _items_crudos_acumulados_de_orden(cursor, orden_id),
        "hora_pedido": hora_pedido,
        "hora_agregado": fecha_agregado,
    }
    crear_job_en_cursor(
        cursor,
        event_key=f"comanda-{comanda_id}-{token}",
        job_type=TIPO_JOB_COMANDA,
        required_role=ROL_COCINA,
        payload=payload,
        fecha=fecha_evento,
    )


def sincronizar_estado_orden_cursor(cursor, orden_id):
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN estado=? THEN 1 ELSE 0 END),
            COUNT(*)
        FROM orden_comandas
        WHERE orden_id=?
        """,
        (ESTADO_COMANDA_EN_COCINA, orden_id),
    )
    en_cocina, total = cursor.fetchone()
    en_cocina = int(en_cocina or 0)
    total = int(total or 0)
    if total == 0:
        return

    nuevo_estado = "en cocina" if en_cocina else "listo"
    cursor.execute(
        """
        UPDATE ordenes
        SET estado=?
        WHERE id=? AND cierre_id IS NULL AND estado != 'cerrada'
        """,
        (nuevo_estado, orden_id),
    )


def _ids_items_sin_comanda(cursor, orden_id):
    cursor.execute(
        """
        SELECT oi.id
        FROM orden_items oi
        LEFT JOIN orden_comanda_items ci ON ci.orden_item_id = oi.id
        WHERE oi.orden_id=? AND ci.id IS NULL
        ORDER BY oi.id ASC
        """,
        (orden_id,),
    )
    return [row[0] for row in cursor.fetchall()]


def _reservar_secuencia_comanda(cursor, orden_id):
    cursor.execute(
        """
        UPDATE ordenes
        SET proxima_secuencia_comanda = COALESCE(proxima_secuencia_comanda, 0) + 1
        WHERE id=?
        RETURNING proxima_secuencia_comanda
        """,
        (orden_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise OrdenComandaNoExiste("Orden no encontrada.")
    return int(row[0]) - 1
