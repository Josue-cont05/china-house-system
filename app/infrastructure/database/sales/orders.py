class SqlSalesOrderRepository:
    def __init__(self, connection_factory):
        self._connection_factory = connection_factory

    def obtener_cabecera(self, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT o.id, o.numero_orden, o.fecha_hora, o.tipo, o.referencia, o.cliente,
                       o.estado, o.observacion, o.descuento, u.nombre, o.cierre_id,
                       o.delivery_usd, o.delivery_repartidor_id
                FROM ordenes o
                LEFT JOIN usuarios u ON o.usuario_id = u.id
                WHERE o.id=?
                """,
                (orden_id,),
            )
            return cursor.fetchone()
        finally:
            conn.close()

    def obtener_items(self, orden_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oi.producto, oi.precio, oi.id, COALESCE(oi.indicacion, ''),
                       (
                           SELECT c.nombre
                           FROM productos p
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
            return cursor.fetchall()
        finally:
            conn.close()
