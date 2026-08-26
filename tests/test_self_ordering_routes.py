import importlib
import os
import tempfile
import unittest


TEST_DB = tempfile.NamedTemporaryFile(prefix="neko_self_ordering_routes_", suffix=".db", delete=False)
TEST_DB.close()

os.environ["APP_ENV"] = "test"
os.environ["TEST_SQLITE_PATH"] = TEST_DB.name

web_app = importlib.import_module("web_app")


class SelfOrderingRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(TEST_DB.name)
        except OSError:
            pass

    def setUp(self):
        web_app.init_db()
        self.client = web_app.app.test_client()
        self._clear_data()
        self._login()

    def _conn(self):
        return web_app.get_connection()

    def _clear_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in (
            "self_order_request_items",
            "self_order_requests",
            "self_order_links",
            "orden_items",
            "ordenes",
            "cierres_caja",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _login(self, rol="mesonera"):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 999
            sess["usuario_nombre"] = "Test"
            sess["usuario"] = "Test"
            sess["usuario_rol"] = rol

    def _create_order(self, estado="abierta", cierre_id=None):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (
                numero_orden, fecha_hora, fecha, tipo, referencia, cliente,
                estado, usuario_id, cierre_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "2026-08-26 10:00:00",
                "2026-08-26",
                "Mesa",
                "Mesa 1",
                "Cliente",
                estado,
                None,
                cierre_id,
            ),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _create_link(self, orden_id, token="token-mesa", canal="mesa", estado="activo", fecha_expiracion=None):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO self_order_links (
                orden_id, token, canal, estado, fecha_creacion, fecha_expiracion
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (orden_id, token, canal, estado, "2026-08-26 10:00:00", fecha_expiracion),
        )
        link_id = web_app.obtener_ultimo_id(cursor, "self_order_links")
        conn.commit()
        conn.close()
        return link_id

    def _counts(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orden_items")
        items = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM self_order_requests")
        requests = cursor.fetchone()[0]
        conn.close()
        return items, requests

    def _link_row(self, link_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT orden_id, token, canal, estado FROM self_order_links WHERE id=?", (link_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def test_open_order_creates_table_link(self):
        orden_id = self._create_order()

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["creado"])
        self.assertEqual(payload["link"]["canal"], "mesa")
        self.assertEqual(payload["link"]["estado"], "activo")
        self.assertTrue(payload["link"]["token"])

    def test_second_call_reuses_active_link(self):
        orden_id = self._create_order()
        first = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()

        second_response = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        second = second_response.get_json()

        self.assertEqual(second_response.status_code, 200)
        self.assertFalse(second["creado"])
        self.assertEqual(second["link"]["id"], first["link"]["id"])
        self.assertEqual(second["link"]["token"], first["link"]["token"])

    def test_missing_order_is_rejected(self):
        response = self.client.post("/orden/9999/self-ordering/link")

        self.assertEqual(response.status_code, 404)

    def test_closed_order_is_rejected(self):
        orden_id = self._create_order(estado="cerrada")

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")

        self.assertEqual(response.status_code, 409)

    def test_archived_order_is_rejected(self):
        orden_id = self._create_order(estado="abierta", cierre_id=1)

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")

        self.assertEqual(response.status_code, 409)

    def test_revokes_order_link(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link/{link['id']}/revocar")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["revocado"])
        self.assertEqual(self._link_row(link["id"])[3], "revocado")

    def test_revocation_cannot_affect_link_from_other_order(self):
        first_order = self._create_order()
        second_order = self._create_order()
        other_link_id = self._create_link(second_order, token="otro-token")

        response = self.client.post(f"/orden/{first_order}/self-ordering/link/{other_link_id}/revocar")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._link_row(other_link_id)[3], "activo")

    def test_revocation_cannot_affect_non_table_link_from_same_order(self):
        orden_id = self._create_order()
        delivery_link_id = self._create_link(orden_id, token="delivery-token", canal="delivery")

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link/{delivery_link_id}/revocar")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "Link no encontrado para esta orden.")
        self.assertEqual(self._link_row(delivery_link_id)[2], "delivery")
        self.assertEqual(self._link_row(delivery_link_id)[3], "activo")

    def test_after_revoking_new_creation_generates_distinct_token(self):
        orden_id = self._create_order()
        first = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        self.client.post(f"/orden/{orden_id}/self-ordering/link/{first['id']}/revocar")

        second = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        self.assertNotEqual(second["id"], first["id"])
        self.assertNotEqual(second["token"], first["token"])

    def test_expired_link_creates_new_link(self):
        orden_id = self._create_order()
        expired_id = self._create_link(
            orden_id,
            token="token-expirado",
            fecha_expiracion="2020-01-01 00:00:00",
        )

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["creado"])
        self.assertNotEqual(payload["link"]["id"], expired_id)
        self.assertNotEqual(payload["link"]["token"], "token-expirado")

    def test_operations_do_not_create_order_items_or_requests(self):
        orden_id = self._create_order()

        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        self.client.post(f"/orden/{orden_id}/self-ordering/link/{link['id']}/revocar")

        self.assertEqual(self._counts(), (0, 0))

    def test_mutation_routes_do_not_accept_get(self):
        orden_id = self._create_order()
        link_id = self._create_link(orden_id)

        create_response = self.client.get(f"/orden/{orden_id}/self-ordering/link")
        revoke_response = self.client.get(f"/orden/{orden_id}/self-ordering/link/{link_id}/revocar")

        self.assertEqual(create_response.status_code, 405)
        self.assertEqual(revoke_response.status_code, 405)

    def test_internal_authentication_is_required(self):
        anon_client = web_app.app.test_client()
        orden_id = self._create_order()

        response = anon_client.post(f"/orden/{orden_id}/self-ordering/link")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_authenticated_user_without_order_permissions_is_rejected(self):
        orden_id = self._create_order()
        link_id = self._create_link(orden_id)
        self._login(rol="cocina")

        create_response = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        revoke_response = self.client.post(f"/orden/{orden_id}/self-ordering/link/{link_id}/revocar")

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(revoke_response.status_code, 403)
        self.assertEqual(self._link_row(link_id)[3], "activo")


if __name__ == "__main__":
    unittest.main()
