import os
import tempfile
import unittest

from app.infrastructure.database.sales.orders import SqlSalesOrderRepository
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_sales_order_repository_{os.getpid()}.db"
)


class SalesOrderRepositoryTest(unittest.TestCase):
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
        self.repository = SqlSalesOrderRepository(web_app.get_connection)

    def _conn(self):
        return web_app.get_connection()

    def _clear_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in ("orden_items", "ordenes", "productos", "categorias", "usuarios"):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _create_user(self, nombre="Mesonera Test"):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)",
            (nombre, "1234", "mesonera"),
        )
        usuario_id = web_app.obtener_ultimo_id(cursor, "usuarios")
        conn.commit()
        conn.close()
        return usuario_id

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

    def _create_order(
        self,
        usuario_id=None,
        estado="abierta",
        observacion=None,
        descuento=None,
        cierre_id=None,
        delivery_usd=None,
        delivery_repartidor_id=None,
        referencia="Mesa 1",
        cliente="Cliente Test",
        tipo="Mesa",
    ):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (
                numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado,
                usuario_id, observacion, descuento, cierre_id, delivery_usd, delivery_repartidor_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                "2026-08-30 12:00:00",
                "2026-08-30",
                tipo,
                referencia,
                cliente,
                estado,
                usuario_id,
                observacion,
                descuento,
                cierre_id,
                delivery_usd,
                delivery_repartidor_id,
            ),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _add_item(self, orden_id, producto, precio, indicacion=None):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, ?)",
            (orden_id, producto, precio, indicacion),
        )
        item_id = web_app.obtener_ultimo_id(cursor, "orden_items")
        conn.commit()
        conn.close()
        return item_id

    def test_obtener_cabecera_returns_none_for_missing_order(self):
        self.assertIsNone(self.repository.obtener_cabecera(999999))

    def test_obtener_cabecera_returns_exact_shape_consumed_by_web_app(self):
        usuario_id = self._create_user("Emmanuel")
        orden_id = self._create_order(
            usuario_id=usuario_id,
            estado="en cocina",
            observacion="Sin cebolla",
            descuento=5,
            delivery_usd=3.5,
            delivery_repartidor_id=42,
            referencia="Mesa 2",
            cliente="Juan",
            tipo="Mesa",
        )

        cabecera = self.repository.obtener_cabecera(orden_id)

        self.assertEqual(
            cabecera,
            (
                orden_id,
                7,
                "2026-08-30 12:00:00",
                "Mesa",
                "Mesa 2",
                "Juan",
                "en cocina",
                "Sin cebolla",
                5,
                "Emmanuel",
                None,
                3.5,
                42,
            ),
        )

    def test_obtener_cabecera_reflects_cierre_id_when_order_is_archived(self):
        orden_id = self._create_order(cierre_id=99)

        cabecera = self.repository.obtener_cabecera(orden_id)

        self.assertEqual(cabecera[10], 99)

    def test_obtener_cabecera_user_name_is_none_when_usuario_id_does_not_match(self):
        orden_id = self._create_order(usuario_id=999999)

        cabecera = self.repository.obtener_cabecera(orden_id)

        self.assertIsNone(cabecera[9])

    def test_obtener_items_returns_empty_list_for_order_without_items(self):
        orden_id = self._create_order()

        self.assertEqual(self.repository.obtener_items(orden_id), [])

    def test_obtener_items_preserves_insertion_order(self):
        orden_id = self._create_order()
        self._add_item(orden_id, "Producto A", 10.0, "")
        self._add_item(orden_id, "Producto B", 5.0, "")
        self._add_item(orden_id, "Producto C", 2.0, "")

        items = self.repository.obtener_items(orden_id)

        self.assertEqual([item[0] for item in items], ["Producto A", "Producto B", "Producto C"])

    def test_obtener_items_only_returns_items_of_requested_order(self):
        orden_uno = self._create_order()
        orden_dos = self._create_order()
        self._add_item(orden_uno, "Producto Uno", 10.0, "")
        self._add_item(orden_dos, "Producto Dos", 20.0, "")

        items = self.repository.obtener_items(orden_uno)

        self.assertEqual([item[0] for item in items], ["Producto Uno"])

    def test_obtener_items_shape_includes_id_precio_indicacion_and_categoria(self):
        categoria_id = self._create_category("Bebidas")
        self._create_product("Refresco", 2.0, categoria_id)
        orden_id = self._create_order()
        item_id = self._add_item(orden_id, "Refresco", 2.0, "Bien frio")

        items = self.repository.obtener_items(orden_id)

        self.assertEqual(items, [("Refresco", 2.0, item_id, "Bien frio", "Bebidas")])

    def test_obtener_items_normalizes_null_indicacion_to_empty_string(self):
        orden_id = self._create_order()
        self._add_item(orden_id, "Producto Sin Nota", 4.0, None)

        items = self.repository.obtener_items(orden_id)

        self.assertEqual(items[0][3], "")

    def test_obtener_items_categoria_matches_product_name_case_insensitively(self):
        categoria_id = self._create_category("Solo para ti")
        self._create_product("Pollo Agridulce", 8.0, categoria_id)
        orden_id = self._create_order()
        self._add_item(orden_id, "pollo agridulce", 8.0, "")

        items = self.repository.obtener_items(orden_id)

        self.assertEqual(items[0][4], "Solo para ti")

    def test_obtener_items_categoria_is_none_when_no_product_matches(self):
        orden_id = self._create_order()
        self._add_item(orden_id, "Producto Descontinuado", 3.0, "")

        items = self.repository.obtener_items(orden_id)

        self.assertIsNone(items[0][4])

    def test_obtener_items_categoria_prefers_active_product_when_names_collide(self):
        categoria_inactiva = self._create_category("Extras")
        categoria_activa = self._create_category("Bebidas")
        self._create_product("Te Frio", 3.0, categoria_inactiva, activo=0)
        self._create_product("Te Frio", 3.0, categoria_activa, activo=1)
        orden_id = self._create_order()
        self._add_item(orden_id, "Te Frio", 3.0, "")

        items = self.repository.obtener_items(orden_id)

        self.assertEqual(items[0][4], "Bebidas")


if __name__ == "__main__":
    unittest.main()
