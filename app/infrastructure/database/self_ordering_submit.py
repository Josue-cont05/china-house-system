from app.application.self_ordering.submit import (
    OrdenItemPreparado,
    RequestItemPreparado,
    ResultadoSubmitSelfOrdering,
)
from app.infrastructure.database.kitchen_comandas import crear_comanda_en_cursor


class SubmitSelfOrderingAtomicoError(RuntimeError):
    pass


class SqlSelfOrderingSubmitRepository:
    def __init__(self, connection_factory, last_id_getter, numero_orden_provider):
        self._connection_factory = connection_factory
        self._last_id_getter = last_id_getter
        self._numero_orden_provider = numero_orden_provider

    def buscar_por_token(self, token):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, orden_id, token, canal, estado, fecha_creacion, fecha_expiracion, mesa_clave
                FROM self_order_links
                WHERE token=?
                LIMIT 1
                """,
                (token,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            from app.infrastructure.database.self_ordering_links import _row_to_link

            return _row_to_link(row)
        finally:
            conn.close()

    def obtener_estado_orden(self, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=? LIMIT 1", (orden_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    def obtener_producto_catalogo(self, producto_id, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT p.nombre, p.precio, COALESCE(c.nombre, ''),
                       COALESCE(p.activo, 1), COALESCE(c.activo, 1),
                       COALESCE(o.delivery_usd, 0)
                FROM productos p
                LEFT JOIN categorias c ON p.categoria_id = c.id
                LEFT JOIN ordenes o ON o.id = ?
                WHERE p.id=?
                LIMIT 1
                """,
                (orden_id, producto_id),
            )
            return cursor.fetchone()
        finally:
            conn.close()

    def guardar_submit_atomico(
        self,
        *,
        token,
        link_id,
        orden_id,
        canal,
        submission_id,
        fecha,
        request_items: tuple[RequestItemPreparado, ...],
        orden_items: tuple[OrdenItemPreparado, ...],
    ):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            existente = self._buscar_request_existente(cursor, link_id, submission_id)
            if existente is not None:
                conn.rollback()
                return existente

            self._revalidar_destino(cursor, token, link_id, orden_id)
            numero_orden_reserva = self._numero_si_hace_falta(cursor, orden_id)
            cursor.execute(
                """
                INSERT INTO self_order_requests (
                    self_order_link_id, orden_id, canal, estado, fecha_creacion,
                    fecha_resolucion, usuario_resolucion_id, notas, client_submission_id
                )
                VALUES (?, ?, ?, 'aceptada', ?, ?, NULL, ?, ?)
                """,
                (
                    link_id,
                    orden_id,
                    canal,
                    fecha,
                    fecha,
                    "Aceptada por validacion servidor.",
                    submission_id,
                ),
            )
            request_id = self._last_id_getter(cursor, "self_order_requests")

            for item in request_items:
                cursor.execute(
                    """
                    INSERT INTO self_order_request_items (
                        request_id, producto_id, producto_nombre_snapshot,
                        precio_unitario_snapshot, cantidad, indicacion,
                        configuracion_json, subtotal_usd
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        item.producto_id,
                        item.producto_nombre_snapshot,
                        item.precio_unitario_snapshot,
                        item.cantidad,
                        item.indicacion,
                        item.configuracion_json,
                        item.subtotal_usd,
                    ),
                )

            orden_item_ids = []
            for item in orden_items:
                cursor.execute(
                    """
                    INSERT INTO orden_items (orden_id, producto, precio, indicacion)
                    VALUES (?, ?, ?, ?)
                    """,
                    (orden_id, item.producto, item.precio, item.indicacion),
                )
                orden_item_ids.append(self._last_id_getter(cursor, "orden_items"))

            try:
                comanda = crear_comanda_en_cursor(
                    cursor,
                    self._last_id_getter,
                    orden_id=orden_id,
                    origen="self_ordering",
                    self_order_request_id=request_id,
                    orden_item_ids=orden_item_ids,
                    fecha=fecha,
                    numero_orden_reserva=numero_orden_reserva,
                )
            except Exception as exc:
                raise SubmitSelfOrderingAtomicoError("No se pudo enviar la comanda a cocina.") from exc

            conn.commit()
            return ResultadoSubmitSelfOrdering(
                request_id=request_id,
                estado="aceptada",
                total_usd=round(sum(item.subtotal_usd for item in request_items), 2),
                items=request_items,
                idempotente=False,
                comanda_id=comanda.comanda_id,
                comanda_secuencia=comanda.secuencia,
                numero_orden=comanda.numero_orden,
            )
        except Exception:
            conn.rollback()
            existente = self._buscar_request_existente_nueva_conexion(link_id, submission_id)
            if existente is not None:
                return existente
            raise
        finally:
            conn.close()

    def _buscar_request_existente(self, cursor, link_id, submission_id):
        cursor.execute(
            """
            SELECT id, estado
            FROM self_order_requests
            WHERE self_order_link_id=? AND client_submission_id=?
            LIMIT 1
            """,
            (link_id, submission_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._resultado_request_existente(cursor, row[0], row[1])

    def _buscar_request_existente_nueva_conexion(self, link_id, submission_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            return self._buscar_request_existente(cursor, link_id, submission_id)
        finally:
            conn.close()

    def _resultado_request_existente(self, cursor, request_id, estado):
        cursor.execute(
            """
            SELECT producto_id, producto_nombre_snapshot, precio_unitario_snapshot,
                   cantidad, COALESCE(indicacion, ''), COALESCE(configuracion_json, ''),
                   subtotal_usd
            FROM self_order_request_items
            WHERE request_id=?
            ORDER BY id
            """,
            (request_id,),
        )
        items = tuple(
            RequestItemPreparado(
                producto_id=row[0],
                producto_nombre_snapshot=row[1],
                precio_unitario_snapshot=float(row[2] or 0),
                cantidad=int(row[3] or 0),
                indicacion=row[4],
                configuracion_json=row[5],
                subtotal_usd=float(row[6] or 0),
            )
            for row in cursor.fetchall()
        )
        return ResultadoSubmitSelfOrdering(
            request_id=request_id,
            estado=estado,
            total_usd=round(sum(item.subtotal_usd for item in items), 2),
            items=items,
            idempotente=True,
            **self._datos_comanda_request(cursor, request_id),
        )

    def _revalidar_destino(self, cursor, token, link_id, orden_id):
        cursor.execute(
            """
            SELECT orden_id, canal, estado
            FROM self_order_links
            WHERE id=? AND token=?
            LIMIT 1
            """,
            (link_id, token),
        )
        link = cursor.fetchone()
        if link is None or link[0] != orden_id or link[1] != "mesa" or link[2] != "activo":
            raise SubmitSelfOrderingAtomicoError("Enlace no disponible.")

        cursor.execute("SELECT estado, cierre_id FROM ordenes WHERE id=? LIMIT 1", (orden_id,))
        orden = cursor.fetchone()
        if orden is None or orden[0] == "cerrada" or orden[1] is not None:
            raise SubmitSelfOrderingAtomicoError("Mesa no habilitada.")

    def _numero_si_hace_falta(self, cursor, orden_id):
        cursor.execute(
            """
            SELECT numero_orden
            FROM ordenes
            WHERE id=?
            LIMIT 1
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise SubmitSelfOrderingAtomicoError("Mesa no habilitada.")
        return self._numero_orden_provider() if row[0] is None else row[0]

    def _datos_comanda_request(self, cursor, request_id):
        cursor.execute(
            """
            SELECT id, secuencia, (
                SELECT numero_orden FROM ordenes WHERE id=orden_comandas.orden_id
            )
            FROM orden_comandas
            WHERE self_order_request_id=?
            ORDER BY id
            LIMIT 1
            """,
            (request_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return {"comanda_id": None, "comanda_secuencia": None, "numero_orden": None}
        return {"comanda_id": row[0], "comanda_secuencia": row[1], "numero_orden": row[2]}
