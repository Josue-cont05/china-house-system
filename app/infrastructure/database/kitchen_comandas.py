from app.application.kitchen.comandas import (
    ESTADO_COMANDA_EN_COCINA,
    ESTADO_COMANDA_LISTO,
    ORIGEN_COMANDA_MANUAL,
    ORIGEN_COMANDA_SELF_ORDERING,
    OrdenComandaNoExiste,
    OrdenComandaSinItems,
    ResultadoComanda,
)


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

    def reimprimir_ultima_comanda_de_orden(self, orden_id, token):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id
                FROM orden_comandas
                WHERE orden_id=?
                ORDER BY secuencia DESC, id DESC
                LIMIT 1
                """,
                (orden_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return False
            cursor.execute(
                """
                UPDATE orden_comandas
                SET reimpresion_token=?
                WHERE id=?
                """,
                (token, row[0]),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reimprimir_comanda(self, comanda_id, token):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE orden_comandas
                SET reimpresion_token=?
                WHERE id=?
                """,
                (token, comanda_id),
            )
            afectadas = cursor.rowcount
            conn.commit()
            return afectadas > 0
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
                WHERE c.estado = ?
                   OR (c.reimpresion_token IS NOT NULL AND o.estado IN ('en cocina', 'listo', 'cerrada'))
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
                    OR (o.reimpresion_token IS NOT NULL AND o.estado IN ('en cocina', 'listo', 'cerrada'))
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

    numero_orden = row[0] if row[0] is not None else numero_orden_reserva
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
    return ResultadoComanda(
        comanda_id=comanda_id,
        orden_id=orden_id,
        numero_orden=int(numero_orden),
        secuencia=secuencia,
        estado=ESTADO_COMANDA_EN_COCINA,
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
