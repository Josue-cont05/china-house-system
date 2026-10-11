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

    def listar_imagenes_productos(self):
        """{producto_id: imagen_url} solo para productos con imagen.
        Consulta aparte (y no una 5a columna en listar_catalogo_activo)
        para no cambiar la forma de las tuplas que ya consumen otros."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, imagen_url
                FROM productos
                WHERE imagen_url IS NOT NULL AND imagen_url <> ''
                """
            )
            return {fila[0]: fila[1] for fila in cursor.fetchall()}
        finally:
            conn.close()

    def obtener_imagen_producto(self, producto_id):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT imagen_url FROM productos WHERE id=?", (producto_id,))
            fila = cursor.fetchone()
            return fila[0] if fila and fila[0] else None
        finally:
            conn.close()

    def actualizar_imagen_producto(self, producto_id, imagen_url):
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE productos SET imagen_url=? WHERE id=?",
                (imagen_url, producto_id),
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
