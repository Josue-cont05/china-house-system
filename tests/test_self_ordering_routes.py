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
        web_app.CONFIG["SELF_ORDER_PUBLIC_BASE_URL"] = ""
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

    def _login(self, rol="mesonera", base_url=None):
        kwargs = {"base_url": base_url} if base_url else {}
        with self.client.session_transaction(**kwargs) as sess:
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

    def _self_order_link_count(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM self_order_links")
        count = cursor.fetchone()[0]
        conn.close()
        return count

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
        self.assertIn(f"/self-order/{payload['link']['token']}", payload["link"]["public_url"])
        self.assertTrue(payload["link"]["qr_svg"].startswith("data:image/svg+xml;utf8,"))
        self.assertNotIn(b"api.qrserver", response.data)
        self.assertNotIn(b"chart.googleapis", response.data)

    def test_configured_public_base_url_determines_qr_url(self):
        web_app.CONFIG["SELF_ORDER_PUBLIC_BASE_URL"] = "https://pedidos.neko-wok.example"
        orden_id = self._create_order()

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["link"]["public_url"].startswith("https://pedidos.neko-wok.example/self-order/"))
        self.assertTrue(payload["link"]["qr_svg"].startswith("data:image/svg+xml;utf8,"))

    def test_configured_public_base_url_ignores_manipulated_host_header(self):
        web_app.CONFIG["SELF_ORDER_PUBLIC_BASE_URL"] = "https://self-order.neko.example"
        orden_id = self._create_order()
        self._login(base_url="http://evil.example/")

        response = self.client.post(
            f"/orden/{orden_id}/self-ordering/link",
            headers={"Host": "evil.example"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["link"]["public_url"].startswith("https://self-order.neko.example/self-order/"))
        self.assertNotIn("evil.example", payload["link"]["public_url"])

    def test_localhost_fallback_builds_public_url_without_config(self):
        orden_id = self._create_order()

        response = self.client.post(
            f"/orden/{orden_id}/self-ordering/link",
            headers={"Host": "localhost:5000"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["link"]["public_url"].startswith("http://localhost:5000/self-order/"))

    def test_non_local_host_without_public_base_url_fails_controlled(self):
        orden_id = self._create_order()
        self._login(base_url="http://pos.neko-wok.example/")

        response = self.client.post(
            f"/orden/{orden_id}/self-ordering/link",
            headers={"Host": "pos.neko-wok.example"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("SELF_ORDER_PUBLIC_BASE_URL", response.get_json()["error"])

    def test_deceptive_localhost_hosts_do_not_enable_local_fallback(self):
        for host in ("localhost.attacker.com", "127.0.0.1.attacker.com", "attacker-localhost.com"):
            with self.subTest(host=host):
                self._clear_data()
                orden_id = self._create_order()
                self._login(base_url=f"http://{host}/")

                response = self.client.post(
                    f"/orden/{orden_id}/self-ordering/link",
                    headers={"Host": host},
                )
                payload = response.get_json()

                self.assertEqual(response.status_code, 503)
                self.assertIn("SELF_ORDER_PUBLIC_BASE_URL", payload["error"])
                self.assertNotIn("public_url", payload)
                self.assertNotIn(host.encode("utf-8"), response.data)
                self.assertEqual(self._self_order_link_count(), 0)

    def test_invalid_public_base_url_fails_controlled_without_creating_link(self):
        web_app.CONFIG["SELF_ORDER_PUBLIC_BASE_URL"] = "no-es-url"
        orden_id = self._create_order()

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        payload = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertIn("SELF_ORDER_PUBLIC_BASE_URL no es una URL valida", payload["error"])
        self.assertNotIn(b"Traceback", response.data)
        self.assertEqual(self._self_order_link_count(), 0)

    def test_order_screen_does_not_500_when_public_base_url_missing_for_non_local_host(self):
        orden_id = self._create_order()
        self._create_link(orden_id)
        self._login(base_url="http://pos.neko-wok.example/")

        response = self.client.get(
            f"/orden/{orden_id}",
            headers={"Host": "pos.neko-wok.example"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"QR no disponible por configuracion", response.data)
        self.assertIn(b"SELF_ORDER_PUBLIC_BASE_URL", response.data)

    def test_long_https_public_url_generates_local_qr(self):
        web_app.CONFIG["SELF_ORDER_PUBLIC_BASE_URL"] = (
            "https://autoservicio.mesas.localidad-larga.sucursal-central.neko-wok.example"
        )
        orden_id = self._create_order()

        response = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(payload["link"]["public_url"].encode("utf-8")), 78)
        self.assertTrue(payload["link"]["qr_svg"].startswith("data:image/svg+xml;utf8,"))
        self.assertNotIn("api.qrserver", payload["link"]["qr_svg"])
        self.assertNotIn("chart.googleapis", payload["link"]["qr_svg"])

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

    def test_self_ordering_section_appears_for_open_order(self):
        orden_id = self._create_order()

        response = self.client.get(f"/orden/{orden_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Autoservicio / QR", response.data)
        self.assertIn(b"Generar QR de mesa", response.data)

    def test_self_ordering_section_is_hidden_for_closed_or_archived_order(self):
        closed_id = self._create_order(estado="cerrada")
        archived_id = self._create_order(estado="abierta", cierre_id=1)

        closed_response = self.client.get(f"/orden/{closed_id}")
        archived_response = self.client.get(f"/orden/{archived_id}")

        self.assertNotIn(b"Autoservicio / QR", closed_response.data)
        self.assertNotIn(b"Autoservicio / QR", archived_response.data)

    def test_order_screen_shows_active_qr_and_matching_link(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = self.client.get(f"/orden/{orden_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Autoservicio activo", response.data)
        self.assertIn(b"data:image/svg+xml;utf8,", response.data)
        self.assertIn(link["token"].encode("utf-8"), response.data)
        self.assertIn(f"/self-order/{link['token']}".encode("utf-8"), response.data)
        self.assertNotIn(b"api.qrserver", response.data)
        self.assertNotIn(b"chart.googleapis", response.data)

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

    def test_public_self_order_active_token_is_accessible_without_session(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        anon_client = web_app.app.test_client()

        response = anon_client.get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Este enlace de autoservicio esta activo", response.data)
        self.assertNotIn(b"orden_id", response.data)
        self.assertNotIn(b"Mesa 1", response.data)
        self.assertNotIn(b"Cliente", response.data)

    def test_public_self_order_missing_token_does_not_expose_internal_data(self):
        anon_client = web_app.app.test_client()

        response = anon_client.get("/self-order/no-existe")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Enlace no disponible", response.data)
        self.assertNotIn(b"orden_id", response.data)
        self.assertNotIn(b"Traceback", response.data)

    def test_public_self_order_revoked_token_is_blocked(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        self.client.post(f"/orden/{orden_id}/self-ordering/link/{link['id']}/revocar")
        anon_client = web_app.app.test_client()

        response = anon_client.get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Enlace no disponible", response.data)

    def test_public_self_order_expired_token_is_blocked(self):
        orden_id = self._create_order()
        self._create_link(
            orden_id,
            token="token-publico-expirado",
            fecha_expiracion="2020-01-01 00:00:00",
        )
        anon_client = web_app.app.test_client()

        response = anon_client.get("/self-order/token-publico-expirado")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Enlace no disponible", response.data)

    def test_public_endpoint_does_not_accept_post(self):
        anon_client = web_app.app.test_client()

        response = anon_client.post("/self-order/no-existe")

        self.assertEqual(response.status_code, 405)

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
