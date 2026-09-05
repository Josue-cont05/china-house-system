import os
import tempfile
import unittest

from app.infrastructure.database.sales.catalog import SqlSalesCatalogRepository
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_sales_catalog_repository_{os.getpid()}.db"
)


class SalesCatalogRepositoryTest(unittest.TestCase):
    """Uses its own private SQLite file (via web_app.CONFIG["SQLITE_PATH"])
    instead of the shared test DB, so it never deletes state that other
    test modules (e.g. test_sales_snapshot) still need for the rest of the run."""

    @classmethod
    def setUpClass(cls):
        cls._original_sqlite_path = web_app.CONFIG["SQLITE_PATH"]
        web_app.CONFIG["SQLITE_PATH"] = _PRIVATE_DB_PATH
        try:
            web_app.init_db()
        except Exception:
            web_app.CONFIG["SQLITE_PATH"] = cls._original_sqlite_path
            raise

    @classmethod
    def tearDownClass(cls):
        web_app.CONFIG["SQLITE_PATH"] = cls._original_sqlite_path
        try:
            os.unlink(_PRIVATE_DB_PATH)
        except OSError:
            pass

    def setUp(self):
        web_app.init_db()
        self._clear_data()
        self.repository = SqlSalesCatalogRepository(web_app.get_connection)

    def _conn(self):
        return web_app.get_connection()

    def _clear_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in ("productos", "categorias"):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _create_category(self, nombre, activo=1):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categorias (nombre, activo) VALUES (?, ?)", (nombre, activo))
        categoria_id = web_app.obtener_ultimo_id(cursor, "categorias")
        conn.commit()
        conn.close()
        return categoria_id

    def _create_product(self, nombre, precio, categoria_id=None, activo=1):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id, activo) VALUES (?, ?, ?, ?)",
            (nombre, precio, categoria_id, activo),
        )
        producto_id = web_app.obtener_ultimo_id(cursor, "productos")
        conn.commit()
        conn.close()
        return producto_id

    def test_listar_catalogo_activo_returns_id_nombre_precio_and_categoria(self):
        categoria_id = self._create_category("Bebidas")
        producto_id = self._create_product("Frescolita", 1.5, categoria_id)

        productos = self.repository.listar_catalogo_activo()

        self.assertEqual(productos, [(producto_id, "Frescolita", 1.5, "Bebidas")])

    def test_listar_catalogo_activo_excludes_inactive_products(self):
        categoria_id = self._create_category("Bebidas")
        self._create_product("Activo", 1.5, categoria_id, activo=1)
        self._create_product("Inactivo", 1.5, categoria_id, activo=0)

        nombres = [p[1] for p in self.repository.listar_catalogo_activo()]

        self.assertIn("Activo", nombres)
        self.assertNotIn("Inactivo", nombres)

    def test_listar_catalogo_activo_excludes_products_in_inactive_category(self):
        categoria_activa = self._create_category("Bebidas", activo=1)
        categoria_inactiva = self._create_category("Descontinuados", activo=0)
        self._create_product("Producto Categoria Activa", 2.0, categoria_activa)
        self._create_product("Producto Categoria Inactiva", 2.0, categoria_inactiva)

        nombres = [p[1] for p in self.repository.listar_catalogo_activo()]

        self.assertIn("Producto Categoria Activa", nombres)
        self.assertNotIn("Producto Categoria Inactiva", nombres)

    def test_listar_catalogo_activo_treats_null_activo_as_active(self):
        categoria_id = self._create_category("Bebidas")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id, activo) VALUES (?, ?, ?, NULL)",
            ("Sin Flag Activo", 3.0, categoria_id),
        )
        conn.commit()
        conn.close()

        nombres = [p[1] for p in self.repository.listar_catalogo_activo()]

        self.assertIn("Sin Flag Activo", nombres)

    def test_listar_catalogo_activo_includes_product_without_category(self):
        producto_id = self._create_product("Sin Categoria", 4.0, categoria_id=None)

        productos = self.repository.listar_catalogo_activo()

        self.assertEqual(productos, [(producto_id, "Sin Categoria", 4.0, None)])

    def test_listar_catalogo_activo_returns_empty_when_no_products(self):
        self.assertEqual(self.repository.listar_catalogo_activo(), [])


if __name__ == "__main__":
    unittest.main()
