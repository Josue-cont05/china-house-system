class SqlSalesCatalogRepository:
    def __init__(self, connection_factory):
        self._connection_factory = connection_factory

    def listar_catalogo_activo(self):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT p.id, p.nombre, p.precio, c.nombre
                FROM productos p
                LEFT JOIN categorias c ON p.categoria_id = c.id
                WHERE COALESCE(p.activo, 1) = 1
                  AND COALESCE(c.activo, 1) = 1
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()
