import sqlite3
import unittest

from tests.support_env import TEST_DB, cleanup_test_db, import_web_app


web_app = import_web_app()


class SelfOrderingSchemaTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cleanup_test_db()

    def setUp(self):
        web_app.init_db()
        self._clear_self_ordering_data()

    def _conn(self):
        return web_app.get_connection()

    def _clear_self_ordering_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in (
            "self_order_request_items",
            "self_order_requests",
            "self_order_links",
            "orden_items",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _table_names(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in cursor.fetchall()}
        conn.close()
        return names

    def _columns(self, table):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1]: row for row in cursor.fetchall()}
        conn.close()
        return columns

    def _create_link(self, token="token-1", canal="mesa", estado="activo"):
        conn = self._conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO self_order_links (
                    orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (None, token, canal, estado, "2026-08-25 10:00:00", "2026-08-25 11:00:00"),
            )
            link_id = web_app.obtener_ultimo_id(cursor, "self_order_links")
            conn.commit()
            return link_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_order(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (
                numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (None, "2026-08-25 10:00:00", "2026-08-25", "Mesa", "mesa:1", "Cliente", "abierta", None),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _create_request(self, link_id, canal="mesa", estado="pendiente", nombre="Cliente"):
        conn = self._conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO self_order_requests (
                    self_order_link_id, orden_id, canal, estado, fecha_creacion,
                    nombre_cliente, telefono_cliente, notas
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (link_id, None, canal, estado, "2026-08-25 10:05:00", nombre, "0412", "Sin cebolla"),
            )
            request_id = web_app.obtener_ultimo_id(cursor, "self_order_requests")
            conn.commit()
            return request_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _insert_request_item(self, request_id, producto_id, producto, precio, cantidad, indicacion):
        conn = self._conn()
        cursor = conn.cursor()
        try:
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
                    producto_id,
                    producto,
                    precio,
                    cantidad,
                    indicacion,
                    '{"tipo":"prueba"}',
                    round(precio * cantidad, 2),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _insert_request_item_without_quantity(self, request_id, producto_id, producto, precio):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO self_order_request_items (
                request_id, producto_id, producto_nombre_snapshot,
                precio_unitario_snapshot, indicacion, configuracion_json, subtotal_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, producto_id, producto, precio, "", '{"tipo":"default"}', precio),
        )
        item_id = web_app.obtener_ultimo_id(cursor, "self_order_request_items")
        conn.commit()
        conn.close()
        return item_id

    def test_creates_self_ordering_tables(self):
        self.assertTrue(
            {
                "self_order_links",
                "self_order_requests",
                "self_order_request_items",
            }.issubset(self._table_names())
        )

    def test_self_ordering_tables_have_expected_columns(self):
        self.assertEqual(
            set(self._columns("self_order_links")),
            {
                "id",
                "orden_id",
                "token",
                "canal",
                "estado",
                "fecha_creacion",
                "fecha_expiracion",
                "mesa_clave",
            },
        )
        self.assertEqual(
            set(self._columns("self_order_requests")),
            {
                "id",
                "self_order_link_id",
                "orden_id",
                "canal",
                "estado",
                "fecha_creacion",
                "fecha_resolucion",
                "usuario_resolucion_id",
                "nombre_cliente",
                "telefono_cliente",
                "notas",
                "client_submission_id",
            },
        )
        self.assertEqual(
            set(self._columns("self_order_request_items")),
            {
                "id",
                "request_id",
                "producto_id",
                "producto_nombre_snapshot",
                "precio_unitario_snapshot",
                "cantidad",
                "indicacion",
                "configuracion_json",
                "subtotal_usd",
            },
        )

    def test_self_order_link_token_is_unique(self):
        self._create_link(token="unico")

        with self.assertRaises(sqlite3.IntegrityError):
            self._create_link(token="unico")

    def test_self_order_link_can_reference_real_order(self):
        orden_id = self._create_order()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO self_order_links (
                orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (orden_id, "orden-real", "mesa", "activo", "2026-08-25 10:00:00", None),
        )
        conn.commit()
        cursor.execute("SELECT orden_id FROM self_order_links WHERE token=?", ("orden-real",))
        orden_id_guardado = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(orden_id_guardado, orden_id)

    def test_self_order_channels_are_validated(self):
        for canal in ("mesa", "pickup", "delivery", "whatsapp"):
            with self.subTest(canal=canal):
                self._create_link(token=f"link-{canal}", canal=canal)

        with self.assertRaises(sqlite3.IntegrityError):
            self._create_link(token="link-invalido", canal="mostrador")

    def test_self_order_states_are_validated(self):
        for estado in ("activo", "expirado", "revocado"):
            with self.subTest(estado=estado):
                self._create_link(token=f"estado-{estado}", estado=estado)

        link_id = self._create_link(token="requests-estados")
        for estado in ("pendiente", "aceptada", "rechazada", "cancelada"):
            with self.subTest(estado=estado):
                self._create_request(link_id, estado=estado, nombre=estado)

        with self.assertRaises(sqlite3.IntegrityError):
            self._create_link(token="link-estado-invalido", estado="pausado")
        with self.assertRaises(sqlite3.IntegrityError):
            self._create_request(link_id, estado="procesando")

    def test_pending_request_does_not_create_order_items(self):
        link_id = self._create_link()
        request_id = self._create_request(link_id, estado="pendiente")
        self._insert_request_item(request_id, 10, "Neko Combo 1", 5.30, 2, "Sabor: Coca Cola")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orden_items")
        orden_items_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM self_order_request_items WHERE request_id=?", (request_id,))
        request_items_count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(orden_items_count, 0)
        self.assertEqual(request_items_count, 1)

    def test_request_item_quantity_defaults_to_one_when_omitted(self):
        link_id = self._create_link()
        request_id = self._create_request(link_id)
        item_id = self._insert_request_item_without_quantity(request_id, 10, "Producto default", 4.5)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT cantidad FROM self_order_request_items WHERE id=?", (item_id,))
        cantidad = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(cantidad, 1)

    def test_request_item_rejects_zero_and_negative_quantity(self):
        link_id = self._create_link()
        request_id = self._create_request(link_id)

        for cantidad in (0, -1):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(sqlite3.IntegrityError):
                    self._insert_request_item(
                        request_id,
                        10,
                        "Producto invalido",
                        4.5,
                        cantidad,
                        "",
                    )

    def test_multiple_requests_can_point_to_same_link(self):
        link_id = self._create_link()
        first_id = self._create_request(link_id, nombre="Cliente 1")
        second_id = self._create_request(link_id, nombre="Cliente 2")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM self_order_requests WHERE self_order_link_id=? ORDER BY id",
            (link_id,),
        )
        request_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        self.assertEqual(request_ids, [first_id, second_id])

    def test_each_request_keeps_its_own_items(self):
        link_id = self._create_link()
        first_id = self._create_request(link_id, nombre="Cliente 1")
        second_id = self._create_request(link_id, nombre="Cliente 2")
        self._insert_request_item(first_id, 1, "Producto A", 4.0, 1, "Sin salsa")
        self._insert_request_item(second_id, 2, "Producto B", 6.5, 2, "Con picante")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT producto_nombre_snapshot, precio_unitario_snapshot, cantidad, indicacion, subtotal_usd
            FROM self_order_request_items
            WHERE request_id=?
            """,
            (first_id,),
        )
        first_items = cursor.fetchall()
        cursor.execute(
            """
            SELECT producto_nombre_snapshot, precio_unitario_snapshot, cantidad, indicacion, subtotal_usd
            FROM self_order_request_items
            WHERE request_id=?
            """,
            (second_id,),
        )
        second_items = cursor.fetchall()
        conn.close()

        self.assertEqual(first_items, [("Producto A", 4.0, 1, "Sin salsa", 4.0)])
        self.assertEqual(second_items, [("Producto B", 6.5, 2, "Con picante", 13.0)])

    def test_init_db_twice_preserves_self_ordering_structure_and_data(self):
        link_id = self._create_link(token="idempotente")
        self._create_request(link_id)
        columns_before = {
            table: set(self._columns(table))
            for table in (
                "self_order_links",
                "self_order_requests",
                "self_order_request_items",
            )
        }

        web_app.init_db()
        web_app.init_db()

        columns_after = {
            table: set(self._columns(table))
            for table in columns_before
        }
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM self_order_links WHERE token='idempotente'")
        links_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM self_order_requests WHERE self_order_link_id=?", (link_id,))
        requests_count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(columns_after, columns_before)
        self.assertEqual(links_count, 1)
        self.assertEqual(requests_count, 1)


if __name__ == "__main__":
    unittest.main()
