from app.application.self_ordering.links import (
    NuevoSelfOrderLink,
    SelfOrderLink,
    TokenSelfOrderingDuplicado,
)


class SqlSelfOrderLinkRepository:
    def __init__(self, connection_factory, last_id_getter):
        self._connection_factory = connection_factory
        self._last_id_getter = last_id_getter

    def orden_existe(self, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM ordenes WHERE id=? LIMIT 1", (orden_id,))
            return cursor.fetchone() is not None
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

    def insertar_link(self, link):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO self_order_links (
                    orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    link.orden_id,
                    link.token,
                    link.canal,
                    link.estado,
                    link.fecha_creacion,
                    link.fecha_expiracion,
                ),
            )
            link_id = self._last_id_getter(cursor, "self_order_links")
            conn.commit()
            return SelfOrderLink(
                id=link_id,
                orden_id=link.orden_id,
                token=link.token,
                canal=link.canal,
                estado=link.estado,
                fecha_creacion=link.fecha_creacion,
                fecha_expiracion=link.fecha_expiracion,
            )
        except Exception as exc:
            conn.rollback()
            if _es_error_unicidad_token(exc):
                raise TokenSelfOrderingDuplicado("Token duplicado.") from exc
            raise
        finally:
            conn.close()

    def buscar_por_token(self, token):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
                FROM self_order_links
                WHERE token=?
                LIMIT 1
                """,
                (token,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return _row_to_link(row)
        finally:
            conn.close()

    def listar_links_por_orden_canal(self, orden_id, canal):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
                FROM self_order_links
                WHERE orden_id=? AND canal=? AND estado='activo'
                ORDER BY id DESC
                """,
                (orden_id, canal),
            )
            return [_row_to_link(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def buscar_por_id(self, link_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
                FROM self_order_links
                WHERE id=?
                LIMIT 1
                """,
                (link_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return _row_to_link(row)
        finally:
            conn.close()

    def revocar_token(self, token):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE self_order_links SET estado='revocado' WHERE token=?",
                (token,),
            )
            afectados = cursor.rowcount
            conn.commit()
            return afectados > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def revocar_link_mesa_de_orden(self, orden_id, link_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE self_order_links
                SET estado='revocado'
                WHERE id=? AND orden_id=? AND canal='mesa'
                """,
                (link_id, orden_id),
            )
            afectados = cursor.rowcount
            conn.commit()
            return afectados > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _row_to_link(row):
    return SelfOrderLink(
        id=row[0],
        orden_id=row[1],
        token=row[2],
        canal=row[3],
        estado=row[4],
        fecha_creacion=row[5],
        fecha_expiracion=row[6],
    )


def _es_error_unicidad_token(exc):
    mensaje = str(exc).lower()
    return (
        "unique" in mensaje
        or "duplicate key" in mensaje
        or "self_order_links_token" in mensaje
    )
