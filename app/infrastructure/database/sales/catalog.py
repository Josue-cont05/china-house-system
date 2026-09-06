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

    def listar_productos_admin(self):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT p.id, p.nombre, p.precio, c.nombre
                FROM productos p
                LEFT JOIN categorias c ON p.categoria_id = c.id
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def listar_categorias(self):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, nombre FROM categorias")
            return cursor.fetchall()
        finally:
            conn.close()

    def obtener_producto(self, producto_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT nombre, precio, categoria_id FROM productos WHERE id=?",
                (producto_id,),
            )
            return cursor.fetchone()
        finally:
            conn.close()

    def crear_producto(self, nombre, precio, categoria_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO productos (nombre, precio, categoria_id) VALUES (?, ?, ?)",
                (nombre, precio, categoria_id),
            )
            conn.commit()
        finally:
            conn.close()

    def actualizar_producto(self, producto_id, nombre, precio, categoria_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE productos SET nombre=?, precio=?, categoria_id=? WHERE id=?",
                (nombre, precio, categoria_id, producto_id),
            )
            conn.commit()
        finally:
            conn.close()

    def eliminar_producto(self, producto_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM productos WHERE id=?", (producto_id,))
            conn.commit()
        finally:
            conn.close()
