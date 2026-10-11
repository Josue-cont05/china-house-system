from app.infrastructure.database.product_images import (
    eliminar_imagen_producto,
    listar_versiones_imagenes,
    url_imagen_producto,
)


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
        """{producto_id: url} solo para productos con imagen. Prioridad:
        1) imagen guardada en BD (miniatura servida por /producto/<id>/imagen),
        2) imagen_url manual. Sin imagen -> no aparece (placeholder en la UI).
        Nunca lee bytes: solo version de producto_imagenes. Consulta aparte
        (y no una 5a columna en listar_catalogo_activo) para no cambiar la
        forma de las tuplas que ya consumen otros."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            urls = {}
            cursor.execute(
                """
                SELECT id, imagen_url
                FROM productos
                WHERE imagen_url IS NOT NULL AND imagen_url <> ''
                """
            )
            for producto_id, imagen_url in cursor.fetchall():
                urls[producto_id] = imagen_url
            for producto_id, version in listar_versiones_imagenes(cursor).items():
                urls[producto_id] = url_imagen_producto(producto_id, version, miniatura=True)
            return urls
        finally:
            conn.close()

    def listar_productos_admin_detalle(self):
        """Listado de /menu: (id, nombre, precio, categoria, activo, imagen_url),
        ordenado por categoria y nombre. Sin bytes de imagen."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT p.id, p.nombre, p.precio, c.nombre, COALESCE(p.activo, 1), p.imagen_url
                FROM productos p
                LEFT JOIN categorias c ON p.categoria_id = c.id
                ORDER BY COALESCE(c.nombre, ''), p.nombre
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def alternar_activo_producto(self, producto_id, activo):
        """Activar/desactivar (no borra): un producto inactivo sale del POS
        pero conserva historico, imagen y grupos de opciones."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE productos SET activo=? WHERE id=?",
                (1 if activo else 0, producto_id),
            )
            conn.commit()
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
            # Sin FK declaradas: limpiar lo que colgaba del producto borrado.
            eliminar_imagen_producto(cursor, producto_id)
            cursor.execute("DELETE FROM producto_grupos_modificadores WHERE producto_id=?", (producto_id,))
            conn.commit()
        finally:
            conn.close()
