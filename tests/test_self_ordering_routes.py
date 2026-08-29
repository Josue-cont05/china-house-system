import re
import threading
import unittest
from unittest import mock

from app.domain.sales.item_descriptions import deserializar_indicacion
from app.application.self_ordering.catalog import construir_catalogo_self_ordering
from app.application.kitchen.comandas import texto_numero_comanda
from app.infrastructure.database.self_ordering_catalog import SqlSelfOrderingCatalogRepository

from tests.support_env import TEST_DB, cleanup_test_db, import_web_app

web_app = import_web_app()


class SelfOrderingRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cleanup_test_db()

    def setUp(self):
        web_app.init_db()
        web_app.asegurar_menu_neko_wok()
        web_app.desactivar_menu_china_house()
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
            "orden_comanda_items",
            "orden_comandas",
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

    def _create_order(self, estado="abierta", cierre_id=None, referencia="mesa:1"):
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
                referencia,
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

    def _create_link(
        self,
        orden_id,
        token="token-mesa",
        canal="mesa",
        estado="activo",
        fecha_expiracion=None,
        mesa_clave=None,
    ):
        conn = self._conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO self_order_links (
                    orden_id, token, canal, estado, fecha_creacion, fecha_expiracion, mesa_clave
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (orden_id, token, canal, estado, "2026-08-26 10:00:00", fecha_expiracion, mesa_clave),
            )
            link_id = web_app.obtener_ultimo_id(cursor, "self_order_links")
            conn.commit()
            return link_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _counts(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orden_items")
        items = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM self_order_requests")
        requests = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM self_order_request_items")
        request_items = cursor.fetchone()[0]
        conn.close()
        return items, requests, request_items

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
        cursor.execute("SELECT orden_id, token, canal, estado, mesa_clave FROM self_order_links WHERE id=?", (link_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def _update_order(self, orden_id, estado=None, cierre_id=None):
        conn = self._conn()
        cursor = conn.cursor()
        if estado is not None:
            cursor.execute("UPDATE ordenes SET estado=? WHERE id=?", (estado, orden_id))
        if cierre_id is not None:
            cursor.execute("UPDATE ordenes SET cierre_id=? WHERE id=?", (cierre_id, orden_id))
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

    def _create_product(self, nombre, precio, categoria_id, activo=1):
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

    def _public_catalog_html(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        response = web_app.app.test_client().get(f"/self-order/{link['token']}")
        self.assertEqual(response.status_code, 200)
        return response.data.decode("utf-8")

    def _catalog_product(self, nombre):
        catalogo = construir_catalogo_self_ordering(
            SqlSelfOrderingCatalogRepository(web_app.get_connection),
            web_app.reglas_catalogo_self_ordering(),
        )
        for categoria in catalogo.categorias:
            for producto in categoria.productos:
                if producto.nombre == nombre:
                    return producto
        self.fail(f"Producto no encontrado: {nombre}")

    def _category_section(self, html_text, section_index):
        marker = f'id="categoria-{section_index}"'
        start = html_text.index(marker)
        section_start = html_text.rfind("<section", 0, start)
        section_end = html_text.index("</section>", start)
        return html_text[section_start:section_end]

    def _product_modal_html(self, html_text, product_name):
        producto = self._catalog_product(product_name)
        marker = f'id="producto-modal-{producto.id}"'
        start = html_text.index(marker)
        modal_start = html_text.rfind('<div class="sheet"', 0, start)
        next_modal = html_text.find('<div class="sheet"', start + 1)
        end = next_modal if next_modal != -1 else html_text.index("<script>", start)
        return html_text[modal_start:end]

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

    def test_table_one_and_twelve_are_valid(self):
        for referencia in ("mesa:1", "mesa:12"):
            with self.subTest(referencia=referencia):
                self._clear_data()
                orden_id = self._create_order(referencia=referencia)

                response = self.client.post(f"/orden/{orden_id}/self-ordering/link")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["link"]["mesa_clave"], referencia)

    def test_invalid_table_references_are_rejected(self):
        for referencia in ("mesa:0", "mesa:13", "Mesa 3", "mesa:abc", "texto libre"):
            with self.subTest(referencia=referencia):
                self._clear_data()
                orden_id = self._create_order(referencia=referencia)

                response = self.client.post(f"/orden/{orden_id}/self-ordering/link")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self._self_order_link_count(), 0)

    def test_create_order_rejects_manipulated_table_reference(self):
        for referencia in ("mesa:0", "mesa:13", "Mesa 3", "abc"):
            with self.subTest(referencia=referencia):
                response = self.client.post(
                    "/crear_orden",
                    data={"tipo": "Mesa", "referencia_mesa": referencia, "cliente": "Cliente"},
                )

                self.assertEqual(response.status_code, 400)

    def test_create_order_accepts_table_one_and_twelve(self):
        for referencia in ("mesa:1", "mesa:12"):
            with self.subTest(referencia=referencia):
                self._clear_data()
                response = self.client.post(
                    "/crear_orden",
                    data={"tipo": "Mesa", "referencia_mesa": referencia, "cliente": "Cliente"},
                )

                self.assertEqual(response.status_code, 302)
                conn = self._conn()
                cursor = conn.cursor()
                cursor.execute("SELECT referencia FROM ordenes ORDER BY id DESC LIMIT 1")
                self.assertEqual(cursor.fetchone()[0], referencia)
                conn.close()

    def test_create_order_blocks_second_open_order_for_same_table(self):
        first = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:3", "cliente": "Primero"},
        )
        second = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:3", "cliente": "Segundo"},
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 409)
        self.assertIn(b"Mesa 3 ya tiene una orden abierta", second.data)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM ordenes WHERE tipo='Mesa' AND referencia='mesa:3' AND estado='abierta'"
        )
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_create_order_allows_different_table_while_one_is_open(self):
        first = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:3", "cliente": "Mesa 3"},
        )
        second = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:4", "cliente": "Mesa 4"},
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)

    def test_create_order_allows_same_table_after_previous_closed(self):
        first = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:3", "cliente": "Primero"},
        )
        first_order = int(first.headers["Location"].rsplit("/", 1)[1])
        self._update_order(first_order, estado="cerrada")

        second = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:3", "cliente": "Segundo"},
        )

        self.assertEqual(second.status_code, 302)

    def test_home_table_selector_contains_exactly_twelve_options(self):
        response = self.client.get("/")
        html_text = response.data.decode("utf-8")
        start = html_text.index('id="referenciaMesaOrden"')
        end = html_text.index("</select>", start)
        selector = html_text[start:end]

        for numero in range(1, 13):
            self.assertIn(f'<option value="mesa:{numero}">Mesa {numero}</option>', selector)
        self.assertEqual(selector.count("<option "), 12)
        self.assertNotIn("mesa:0", selector)
        self.assertNotIn("mesa:13", selector)

    def test_table_three_reuses_permanent_qr_for_future_order(self):
        first_order = self._create_order(referencia="mesa:3")
        first = self.client.post(f"/orden/{first_order}/self-ordering/link").get_json()["link"]
        self._update_order(first_order, estado="cerrada")

        closed_response = web_app.app.test_client().get(f"/self-order/{first['token']}")
        self.assertEqual(closed_response.status_code, 200)
        self.assertIn(b"Mesa no habilitada", closed_response.data)
        self.assertNotIn(b"Neko Combo", closed_response.data)

        second_order = self._create_order(referencia="mesa:3")
        second = self.client.post(f"/orden/{second_order}/self-ordering/link").get_json()["link"]

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["token"], first["token"])
        self.assertEqual(second["mesa_clave"], "mesa:3")
        active_response = web_app.app.test_client().get(f"/self-order/{second['token']}")
        self.assertEqual(active_response.status_code, 200)
        self.assertIn(b"Neko Wok", active_response.data)

    def test_create_order_reassociates_permanent_qr_before_any_internal_get(self):
        first_order = self._create_order(referencia="mesa:5")
        first = self.client.post(f"/orden/{first_order}/self-ordering/link").get_json()["link"]
        token = first["token"]
        self._update_order(first_order, estado="cerrada")

        closed_response = web_app.app.test_client().get(f"/self-order/{token}")
        self.assertEqual(closed_response.status_code, 200)
        self.assertIn(b"Mesa no habilitada", closed_response.data)

        second = self.client.post(
            "/crear_orden",
            data={"tipo": "Mesa", "referencia_mesa": "mesa:5", "cliente": "Segundo"},
        )
        second_order = int(second.headers["Location"].rsplit("/", 1)[1])

        row = self._link_row(first["id"])
        self.assertEqual(row[0], second_order)
        self.assertEqual(row[1], token)
        self.assertEqual(row[3], "activo")
        self.assertEqual(row[4], "mesa:5")
        active_response = web_app.app.test_client().get(f"/self-order/{token}")
        self.assertEqual(active_response.status_code, 200)
        self.assertIn(b"Neko Wok", active_response.data)
        self.assertNotIn(b"Mesa no habilitada", active_response.data)

    def test_order_screen_does_not_reassign_or_500_with_anomalous_duplicate_open_tables(self):
        first_order = self._create_order(referencia="mesa:5")
        first = self.client.post(f"/orden/{first_order}/self-ordering/link").get_json()["link"]
        second_order = self._create_order(referencia="mesa:5")

        response = self.client.get(f"/orden/{second_order}")

        self.assertEqual(response.status_code, 200)
        row = self._link_row(first["id"])
        self.assertEqual(row[0], first_order)
        self.assertEqual(row[1], first["token"])

    def test_public_endpoint_ignores_manipulated_order_id_parameter(self):
        mesa_3_order = self._create_order(referencia="mesa:3")
        other_order = self._create_order(referencia="mesa:4")
        link = self.client.post(f"/orden/{mesa_3_order}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(
            f"/self-order/{link['token']}?orden_id={other_order}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Neko Wok", response.data)
        self.assertNotIn(b"orden_id", response.data)
        self.assertNotIn(b"mesa:4", response.data)

    def test_different_tables_have_distinct_permanent_tokens(self):
        mesa_3 = self.client.post(
            f"/orden/{self._create_order(referencia='mesa:3')}/self-ordering/link"
        ).get_json()["link"]
        mesa_4 = self.client.post(
            f"/orden/{self._create_order(referencia='mesa:4')}/self-ordering/link"
        ).get_json()["link"]

        self.assertNotEqual(mesa_3["token"], mesa_4["token"])

    def test_cannot_have_two_active_permanent_qrs_for_same_table(self):
        self._create_link(
            self._create_order(referencia="mesa:5"),
            token="mesa-cinco",
            mesa_clave="mesa:5",
        )

        with self.assertRaises(Exception):
            self._create_link(
                self._create_order(referencia="mesa:5"),
                token="mesa-cinco-duplicado",
                mesa_clave="mesa:5",
            )

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
        self.assertIn(b"Inicializar QR permanente", response.data)

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
        self.assertIn(b"QR permanente: Activo", response.data)
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

        self.assertEqual(self._counts(), (0, 0, 0))

    def test_public_self_order_active_token_is_accessible_without_session(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        anon_client = web_app.app.test_client()

        response = anon_client.get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Neko Wok", response.data)
        self.assertIn(b"Autoservicio de mesa", response.data)
        self.assertNotIn(b"orden_id", response.data)
        self.assertNotIn(b"cierre_id", response.data)
        self.assertNotIn(b"usuario", response.data.lower())
        self.assertNotIn(b"Mesa 1", response.data)
        self.assertNotIn(b"Cliente", response.data)

    def test_public_catalog_blocks_table_link_when_order_is_closed_after_qr(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        self._update_order(orden_id, estado="cerrada")
        anon_client = web_app.app.test_client()

        response = anon_client.get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mesa no habilitada", response.data)
        self.assertNotIn(b"Neko Combo", response.data)

    def test_public_catalog_blocks_table_link_when_order_is_archived_after_qr(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        self._update_order(orden_id, cierre_id=123)
        anon_client = web_app.app.test_client()

        response = anon_client.get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mesa no habilitada", response.data)
        self.assertNotIn(b"Neko Combo", response.data)

    def test_public_self_order_missing_token_does_not_expose_internal_data(self):
        anon_client = web_app.app.test_client()

        response = anon_client.get("/self-order/no-existe")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Enlace no disponible", response.data)
        self.assertNotIn(b"orden_id", response.data)
        self.assertNotIn(b"Traceback", response.data)
        self.assertNotIn(b"Neko Combo", response.data)

    def test_public_self_order_revoked_token_is_blocked(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        self.client.post(f"/orden/{orden_id}/self-ordering/link/{link['id']}/revocar")
        anon_client = web_app.app.test_client()

        response = anon_client.get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Enlace no disponible", response.data)
        self.assertNotIn(b"Neko Combo", response.data)

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
        self.assertNotIn(b"Neko Combo", response.data)

    def test_public_catalog_shows_public_categories_in_order(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        expected = [
            "Combos personales",
            "Arroz chino",
            "Promociones",
            "Bebidas",
        ]
        positions = [response.data.index(text.encode("utf-8")) for text in expected]
        self.assertEqual(positions, sorted(positions))

    def test_public_catalog_groups_products_by_public_category(self):
        html_text = self._public_catalog_html()
        combos = self._category_section(html_text, 0)
        arroz = self._category_section(html_text, 1)
        promociones = self._category_section(html_text, 2)
        bebidas = self._category_section(html_text, 3)

        for producto in ("Neko Combo 1", "Neko Combo 2", "Neko Combo 3"):
            self.assertIn(producto, combos)
            self.assertNotIn(producto, arroz)
            self.assertNotIn(producto, promociones)
            self.assertNotIn(producto, bebidas)

        for producto in ("Neko Clan Triple", "Neko Dúo Triple"):
            self.assertIn(producto, arroz)
            self.assertNotIn(producto, combos)
            self.assertNotIn(producto, promociones)
            self.assertNotIn(producto, bebidas)

        for producto in ("Familiar", "Mega Familiar", "Wok para Dos"):
            self.assertIn(producto, promociones)
            self.assertNotIn(producto, combos)
            self.assertNotIn(producto, arroz)
            self.assertNotIn(producto, bebidas)

        for producto in ("Refresco 1 Lt", "Refresco 1.5 Lt", "Refresco 2 Lt"):
            self.assertIn(producto, bebidas)
            self.assertNotIn(producto, combos)
            self.assertNotIn(producto, arroz)
            self.assertNotIn(producto, promociones)

    def test_public_catalog_shows_simple_product_card_with_server_price(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Neko Clan Triple".encode("utf-8"), response.data)
        self.assertIn(b"$13.00", response.data)
        self.assertIn(b"Seleccionar", response.data)

    def test_public_catalog_shows_soda_flavors(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Refresco 1 Lt", response.data)
        self.assertIn(b"Elige 1 sabor", response.data)
        self.assertIn(b"Coca Cola", response.data)
        self.assertIn(b"Frescolita", response.data)

    def test_public_catalog_uses_real_soda_flavor_source(self):
        original = web_app.SABORES_REFRESCO
        web_app.SABORES_REFRESCO = ["Sabor Auditoria"]
        try:
            orden_id = self._create_order()
            link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

            response = web_app.app.test_client().get(f"/self-order/{link['token']}")
        finally:
            web_app.SABORES_REFRESCO = original

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sabor Auditoria", response.data)
        self.assertNotIn(b"Pepsi", response.data)

    def test_public_catalog_shows_combo_options(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Neko Combo 1", response.data)
        self.assertIn(b"Ver opciones", response.data)
        self.assertIn(b"Arroz chino con 1 acompanante y bebida.", response.data)
        self.assertIn(b"Elige 1 acompanante", response.data)
        self.assertIn(b"Elige 1 bebida", response.data)
        self.assertIn(b"Pollo BBQ", response.data)

    def test_public_catalog_combo_with_multiple_companions_shows_exact_quantity(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Neko Combo 2", response.data)
        self.assertIn(b"Elige 2 acompanantes", response.data)

    def test_public_catalog_shows_promotion_options(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Familiar", response.data)
        self.assertIn(b"Promocion familiar con pollo, arroz y refresco.", response.data)
        self.assertIn(b"Elige 1 pollo", response.data)
        self.assertIn(b"Elige 1 arroz", response.data)
        self.assertIn(b"Elige 1 sabor", response.data)
        self.assertIn(b"Incluye: Refresco 1.5 Lt", response.data)
        self.assertIn(b"Coca Cola", response.data)
        self.assertIn(b"Frescolita", response.data)
        self.assertNotIn(b"<span class='chip'>Refresco 1.5 Lt</span>", response.data)
        self.assertIn(b"Promo extra", response.data)
        self.assertIn(b"Extra", response.data)
        self.assertIn(b"Opcional", response.data)

    def test_catalog_contract_exposes_extra_lumpias_price_from_server_source(self):
        reglas = web_app.reglas_catalogo_self_ordering()

        self.assertEqual(reglas.promo_extra_lumpias_precio, web_app.PROMO_EXTRA_LUMPIAS_PRECIO)

        familiar = self._catalog_product("Familiar")
        extra = next(opcion for opcion in familiar.opciones if opcion.titulo == "Extra")

        self.assertEqual(extra.valores, (web_app.PROMO_EXTRA_LUMPIAS_NOMBRE,))
        self.assertEqual(
            extra.precios_adicionales_centavos[web_app.PROMO_EXTRA_LUMPIAS_NOMBRE],
            int(round(web_app.PROMO_EXTRA_LUMPIAS_PRECIO * 100)),
        )

    def test_public_catalog_product_cards_do_not_expand_option_chips(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        first_card_start = response.data.index(b'<button class="product-card"')
        first_card_end = response.data.index(b"</button>", first_card_start)
        first_card = response.data[first_card_start:first_card_end]
        self.assertNotIn(b"option-pill", first_card)
        self.assertNotIn(b"Pollo BBQ", first_card)
        self.assertIn(b"producto-modal-", response.data)

    def test_public_catalog_modal_single_selection_has_radio_behavior(self):
        html_text = self._public_catalog_html()

        self.assertIn('data-max="1" data-required="1" data-optional="false"', html_text)
        self.assertIn('data-max="1" data-required="0" data-optional="true"', html_text)
        self.assertIn("if (max === 1)", html_text)
        self.assertIn('const optional = group.dataset.optional === "true";', html_text)
        self.assertIn('if (optional) button.classList.remove("selected");', html_text)
        self.assertIn('if (previous) previous.classList.remove("selected");', html_text)

    def test_public_catalog_has_frontend_cart_without_immediate_submission_mutation(self):
        html_text = self._public_catalog_html()

        self.assertIn('id="cartBar"', html_text)
        self.assertIn('id="cartSheet"', html_text)
        self.assertIn('id="cartLines"', html_text)
        self.assertIn("Agregar al pedido", html_text)
        self.assertIn("Enviar solicitud", html_text)
        self.assertIn("data-add-to-cart", html_text)
        self.assertNotIn("Disponible proximamente</button>\n                <button", html_text)
        self.assertNotIn('method="post"', html_text.lower())
        self.assertNotIn("escapeText(", html_text)

    def test_public_catalog_exposes_extra_lumpias_surcharge_to_frontend(self):
        html_text = self._public_catalog_html()
        expected_cents = int(round(web_app.PROMO_EXTRA_LUMPIAS_PRECIO * 100))

        self.assertIn(f"data-option-extra-cents='{expected_cents}'", html_text)
        self.assertIn(f"+${web_app.PROMO_EXTRA_LUMPIAS_PRECIO:.2f}", html_text)
        self.assertIn("configExtraCents(config)", html_text)

    def test_public_catalog_cart_uses_product_id_without_exposing_order_id(self):
        html_text = self._public_catalog_html()

        self.assertIn('data-product-id="', html_text)
        self.assertIn("productId: productId", html_text)
        self.assertIn("basePriceCents", html_text)
        self.assertIn("unitPriceCents", html_text)
        self.assertNotIn("orden_id", html_text)
        self.assertNotIn("data-orden-id", html_text)

    def test_public_catalog_cart_validates_cardinality_before_add(self):
        html_text = self._public_catalog_html()

        self.assertIn("function configIsValid(config)", html_text)
        self.assertIn("return total === group.requeridas;", html_text)
        self.assertIn("if (total > group.maximas) return false;", html_text)
        self.assertIn("button.disabled = !configIsValid(config);", html_text)

    def test_public_catalog_cart_merges_only_same_product_configuration_and_note(self):
        html_text = self._public_catalog_html()

        self.assertIn("function configKey(config)", html_text)
        self.assertIn("valores: group.valores.slice().sort()", html_text)
        self.assertIn("function normalizeNote(note)", html_text)
        self.assertIn("function lineKey(productId, config, note)", html_text)
        self.assertIn("const key = lineKey(productId, config, indication);", html_text)
        self.assertIn("existing.quantity += 1;", html_text)
        self.assertIn("cart.push({", html_text)
        self.assertIn("titulo: group.titulo", html_text)

    def test_public_catalog_cart_key_separates_extra_and_merges_equal_configs(self):
        html_text = self._public_catalog_html()
        familiar = self._catalog_product("Familiar")
        product_id = familiar.id

        def config_key(config):
            normalized = [
                {
                    "titulo": group["titulo"],
                    "valores": sorted(group["valores"]),
                }
                for group in config
            ]
            normalized.sort(key=lambda group: group["titulo"])
            return str(normalized)

        def line_key(config, note=""):
            return f"{product_id}|{config_key(config)}|{note.strip()}"

        def add(cart, config, note=""):
            key = line_key(config, note)
            existing = next((item for item in cart if item["key"] == key), None)
            if existing:
                existing["quantity"] += 1
            else:
                cart.append({"key": key, "quantity": 1})

        without_extra = [
            {"titulo": "Pollos", "valores": ["Pollo BBQ"]},
            {"titulo": "Arroces", "valores": ["Triple"]},
            {"titulo": "Sabores", "valores": ["Coca Cola"]},
            {"titulo": "Extra", "valores": []},
        ]
        with_extra = [
            {"titulo": "Pollos", "valores": ["Pollo BBQ"]},
            {"titulo": "Arroces", "valores": ["Triple"]},
            {"titulo": "Sabores", "valores": ["Coca Cola"]},
            {"titulo": "Extra", "valores": [web_app.PROMO_EXTRA_LUMPIAS_NOMBRE]},
        ]

        self.assertNotEqual(line_key(without_extra), line_key(with_extra))

        cart = []
        add(cart, with_extra)
        add(cart, with_extra)
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]["quantity"], 2)

        cart = []
        add(cart, without_extra)
        add(cart, without_extra)
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]["quantity"], 2)

        cart = []
        add(cart, without_extra)
        add(cart, with_extra)
        self.assertEqual(len(cart), 2)
        self.assertIn("function configKey(config)", html_text)
        self.assertIn("const key = lineKey(productId, config, indication);", html_text)

    def test_public_catalog_cart_key_includes_normalized_customer_note(self):
        html_text = self._public_catalog_html()
        familiar = self._catalog_product("Familiar")
        product_id = familiar.id
        config = [
            {"titulo": "Pollos", "valores": ["Pollo BBQ"]},
            {"titulo": "Arroces", "valores": ["Triple"]},
            {"titulo": "Sabores", "valores": ["Coca Cola"]},
            {"titulo": "Extra", "valores": []},
        ]

        def config_key(config):
            normalized = [
                {
                    "titulo": group["titulo"],
                    "valores": sorted(group["valores"]),
                }
                for group in config
            ]
            normalized.sort(key=lambda group: group["titulo"])
            return str(normalized)

        def line_key(note):
            return f"{product_id}|{config_key(config)}|{note.strip()}"

        def add(cart, note):
            key = line_key(note)
            existing = next((item for item in cart if item["key"] == key), None)
            if existing:
                existing["quantity"] += 1
            else:
                cart.append({"key": key, "quantity": 1})

        cart = []
        add(cart, "sin cebolla")
        add(cart, "sin cebolla")
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]["quantity"], 2)

        cart = []
        add(cart, "sin cebolla")
        add(cart, "sin salsa")
        self.assertEqual(len(cart), 2)

        self.assertIn('data-customer-note maxlength="180"', html_text)
        self.assertIn("Nota para cocina (opcional)", html_text)
        self.assertIn('note.textContent = "Nota: " + item.indication;', html_text)
        self.assertIn("normalizeNote(note)", html_text)

    def test_public_catalog_note_field_is_not_collected_as_configuration_group(self):
        html_text = self._public_catalog_html()
        simple_modal = self._product_modal_html(html_text, "Neko Clan Triple")

        self.assertIn('class="customer-note-group"', simple_modal)
        self.assertIn("data-customer-note", simple_modal)
        self.assertNotIn('class="option-group">\n                <div class="option-title">\n                    <span>Nota para cocina', simple_modal)
        self.assertNotIn('data-title=""', simple_modal)
        self.assertNotIn("querySelectorAll(\".option-group\")", html_text)
        self.assertIn('querySelectorAll("[data-option-group]")', html_text)

    def test_public_catalog_simple_product_payload_contract_has_empty_configuration_and_note(self):
        html_text = self._public_catalog_html()
        simple_modal = self._product_modal_html(html_text, "Neko Clan Triple")

        self.assertEqual(simple_modal.count("data-option-group"), 0)
        self.assertIn("const indication = normalizeNote(noteInput ? noteInput.value : \"\");", html_text)
        self.assertIn("configuracion: item.config.map(function(group)", html_text)
        self.assertIn("indicacion: item.indication || \"\"", html_text)

    def test_public_catalog_configurable_modals_with_note_only_have_real_option_groups(self):
        html_text = self._public_catalog_html()
        cases = {
            "Familiar": ["Pollos", "Arroces", "Sabores", "Extra"],
            "Neko Combo 1": ["Acompanantes", "Bebidas"],
            "Refresco 1 Lt": ["Sabores"],
        }

        for product_name, expected_titles in cases.items():
            with self.subTest(product_name=product_name):
                modal = self._product_modal_html(html_text, product_name)
                titles = re.findall(r'data-title="([^"]*)"', modal)
                self.assertEqual(titles, expected_titles)
                self.assertNotIn("", titles)
                self.assertIn('class="customer-note-group"', modal)
                self.assertEqual(modal.count("data-option-group"), len(expected_titles))

    def test_public_catalog_cart_quantity_controls_and_total_are_present(self):
        html_text = self._public_catalog_html()

        self.assertIn("data-cart-minus", html_text)
        self.assertIn("data-cart-plus", html_text)
        self.assertIn("data-cart-remove", html_text)
        self.assertIn("cart[index].quantity -= 1;", html_text)
        self.assertIn("cart[index].quantity += 1;", html_text)
        self.assertIn("cart.splice(Number(remove.dataset.cartRemove), 1);", html_text)
        self.assertIn("function totalCents()", html_text)
        self.assertIn("unitPriceCents = basePriceCents + configExtraCents(config)", html_text)
        self.assertIn("item.unitPriceCents * item.quantity", html_text)
        self.assertIn('return "$" + (cents / 100).toFixed(2);', html_text)

    def test_public_catalog_promotion_quantities_match_builder_rules(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Wok para Dos", response.data)
        self.assertIn(b"Mega Familiar", response.data)
        self.assertIn(b"Elige 1 arroz", response.data)
        self.assertIn(b"Elige 1 sabor", response.data)
        self.assertIn(b"Elige 2 arroces", response.data)
        self.assertIn(b"Elige 2 sabores", response.data)

    def test_public_catalog_hides_delivery_legacy(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Delivery 1", response.data)
        self.assertNotIn(b"Delivery 3.5", response.data)

    def test_public_catalog_hides_inactive_product_or_category(self):
        hidden_category = self._create_category("Categoria Oculta", activo=0)
        visible_category = self._create_category("Categoria Visible Test", activo=1)
        self._create_product("Refresco Categoria Oculta", 9.99, hidden_category, activo=1)
        self._create_product("Refresco Inactivo Visible", 8.88, visible_category, activo=0)
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Refresco Categoria Oculta", response.data)
        self.assertNotIn(b"Refresco Inactivo Visible", response.data)

    def test_public_catalog_escapes_product_and_category_html(self):
        category_id = self._create_category("<script>alert('cat')</script>", activo=1)
        self._create_product("Refresco <img src=x onerror=alert(1)>", 1.23, category_id, activo=1)
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"&lt;script&gt;alert", response.data)
        self.assertIn(b"&lt;img src=x onerror=alert", response.data)
        self.assertNotIn(b"<script>alert('cat')</script>", response.data)
        self.assertNotIn(b"<img src=x onerror=alert(1)>", response.data)

    def test_order_screen_escapes_product_and_category_html(self):
        category_id = self._create_category("<script>alert('cat')</script>", activo=1)
        self._create_product("<img src=x onerror=alert(1)>", 1.23, category_id, activo=1)
        orden_id = self._create_order()

        response = self.client.get(f"/orden/{orden_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;script&gt;alert", response.data)
        self.assertIn(b"&lt;img src=x onerror=alert", response.data)
        self.assertNotIn(b"<script>alert('cat')</script>", response.data)
        self.assertNotIn(b"<img src=x onerror=alert(1)>", response.data)
        self.assertNotIn(b"<img src=x", response.data)

    def test_self_ordering_route_tests_use_isolated_database(self):
        self.assertEqual(web_app.CONFIG["SQLITE_PATH"], TEST_DB.name)
        self.assertNotEqual(web_app.CONFIG["SQLITE_PATH"], "china_house.db")

    def test_public_catalog_get_does_not_create_order_or_request_rows(self):
        orden_id = self._create_order()
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]

        response = web_app.app.test_client().get(f"/self-order/{link['token']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._counts(), (0, 0, 0))

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

    def _link_token_for_order(self, orden_id):
        return self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]["token"]

    def _producto_id(self, nombre):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM productos WHERE nombre=? ORDER BY id LIMIT 1", (nombre,))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row, nombre)
        return row[0]

    def _producto_neko_clan_pollo_camaron(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nombre, precio
            FROM productos
            WHERE nombre LIKE 'Neko Clan Pollo Camar%'
            ORDER BY id
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row, "Neko Clan Pollo Camaron")
        return row

    def _submit_payload(self, items, submission_id="submit-test-123"):
        return {"submission_id": submission_id, "items": items}

    def _simple_item_payload(self, nombre="Neko Clan Triple", cantidad=1, **extra):
        payload = {
            "producto_id": self._producto_id(nombre),
            "cantidad": cantidad,
            "configuracion": [],
            "indicacion": "",
        }
        payload.update(extra)
        return payload

    def _familiar_item_payload(self, cantidad=1, extra_lumpias=False, **extra):
        grupos = [
            {"titulo": "Pollos", "valores": ["Pollo BBQ"]},
            {"titulo": "Arroces", "valores": ["Triple"]},
            {"titulo": "Sabores", "valores": ["Coca Cola"]},
            {
                "titulo": "Extra",
                "valores": [web_app.PROMO_EXTRA_LUMPIAS_NOMBRE] if extra_lumpias else [],
            },
        ]
        payload = {
            "producto_id": self._producto_id("Familiar"),
            "cantidad": cantidad,
            "configuracion": grupos,
            "indicacion": "",
        }
        payload.update(extra)
        return payload

    def _combo_item_payload(self, cantidad=1, **extra):
        payload = {
            "producto_id": self._producto_id("Neko Combo 1"),
            "cantidad": cantidad,
            "configuracion": [
                {"titulo": "Acompanantes", "valores": ["Pollo BBQ"]},
                {"titulo": "Bebidas", "valores": ["Coca Cola"]},
            ],
            "indicacion": "",
        }
        payload.update(extra)
        return payload

    def _post_submit(self, token, payload):
        return web_app.app.test_client().post(f"/self-order/{token}/submit", json=payload)

    def _table_counts(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM self_order_requests")
        requests = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM self_order_request_items")
        request_items = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orden_items WHERE orden_id=?", (orden_id,))
        orden_items = cursor.fetchone()[0]
        conn.close()
        return requests, request_items, orden_items

    def _orden_items(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT producto, precio, COALESCE(indicacion, '') FROM orden_items WHERE orden_id=? ORDER BY id",
            (orden_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _request_item_rows(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT producto_nombre_snapshot, precio_unitario_snapshot, cantidad,
                   configuracion_json, subtotal_usd
            FROM self_order_request_items
            ORDER BY id
            """
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _comandas(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, orden_id, secuencia, origen, self_order_request_id, estado
            FROM orden_comandas
            WHERE orden_id=?
            ORDER BY secuencia, id
            """,
            (orden_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _comanda_items(self, comanda_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT oi.id, oi.producto, oi.precio, COALESCE(oi.indicacion, '')
            FROM orden_comanda_items ci
            JOIN orden_items oi ON oi.id = ci.orden_item_id
            WHERE ci.comanda_id=?
            ORDER BY ci.id
            """,
            (comanda_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _order_state(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT estado, numero_orden FROM ordenes WHERE id=?", (orden_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def _insert_order_item(self, orden_id, producto="Neko Clan Triple", precio=13.0):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, '')",
            (orden_id, producto, precio),
        )
        item_id = web_app.obtener_ultimo_id(cursor, "orden_items")
        conn.commit()
        conn.close()
        return item_id

    def test_public_submit_valid_creates_accepted_request_snapshots_and_order_items(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload([self._simple_item_payload()]),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["estado"], "aceptada")
        self.assertEqual(payload["total_usd"], 13.0)
        self.assertEqual(self._table_counts(orden_id), (1, 1, 1))
        self.assertEqual(len(self._comandas(orden_id)), 1)
        self.assertEqual(self._orden_items(orden_id)[0][:2], ("Neko Clan Triple", 13.0))
        snapshot = self._request_item_rows()[0]
        self.assertEqual(snapshot[0], "Neko Clan Triple")
        self.assertEqual(snapshot[1], 13.0)
        self.assertEqual(snapshot[2], 1)
        self.assertEqual(snapshot[4], 13.0)

    def test_public_submit_accepts_real_simple_neko_clan_product_with_empty_configuration(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        producto_id, nombre, precio = self._producto_neko_clan_pollo_camaron()
        producto_catalogo = self._catalog_product(nombre)

        self.assertEqual(producto_catalogo.categoria_publica, "Arroz chino")
        self.assertEqual(producto_catalogo.tipo_configuracion, "simple")
        self.assertEqual(producto_catalogo.opciones, ())

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    {
                        "producto_id": producto_id,
                        "cantidad": 1,
                        "configuracion": [],
                        "indicacion": "",
                    }
                ],
                "debug-neko-clan-1",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["estado"], "aceptada")
        self.assertEqual(response.get_json()["total_usd"], precio)
        self.assertEqual(self._table_counts(orden_id), (1, 1, 1))
        self.assertEqual(self._orden_items(orden_id)[0][:2], (nombre, precio))
        snapshot = self._request_item_rows()[0]
        self.assertEqual(snapshot[0], nombre)
        self.assertEqual(snapshot[1], precio)
        self.assertEqual(snapshot[2], 1)

    def test_public_submit_rejects_invented_configuration_for_real_simple_neko_clan_product(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        producto_id, _, _ = self._producto_neko_clan_pollo_camaron()

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    {
                        "producto_id": producto_id,
                        "cantidad": 1,
                        "configuracion": [{"titulo": "Pollos", "valores": ["Pollo BBQ"]}],
                        "indicacion": "",
                    }
                ],
                "debug-neko-clan-invented",
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Configuracion invalida.")
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_still_rejects_empty_configuration_for_configurable_product(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    {
                        "producto_id": self._producto_id("Familiar"),
                        "cantidad": 1,
                        "configuracion": [],
                        "indicacion": "",
                    }
                ],
                "debug-configurable-empty",
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Configuracion invalida.")
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_two_valid_products_share_one_batch(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    self._simple_item_payload("Neko Clan Triple"),
                    self._simple_item_payload("Refresco 1 Lt", configuracion=[
                        {"titulo": "Sabores", "valores": ["Coca Cola"]}
                    ]),
                ]
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._table_counts(orden_id), (1, 2, 2))

    def test_public_submit_quantity_two_matches_two_order_item_units(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload([self._simple_item_payload(cantidad=2)]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._table_counts(orden_id), (1, 1, 2))
        self.assertEqual([row[0] for row in self._orden_items(orden_id)], ["Neko Clan Triple", "Neko Clan Triple"])
        self.assertEqual(self._request_item_rows()[0][2], 2)

    def test_public_submit_ignores_manipulated_price_and_subtotal(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        item = self._simple_item_payload(precio=1, subtotal=1, precio_base=1)

        response = self._post_submit(token, self._submit_payload([item]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total_usd"], 13.0)
        self.assertEqual(self._orden_items(orden_id)[0][1], 13.0)
        self.assertEqual(self._request_item_rows()[0][1], 13.0)

    def test_public_submit_extra_lumpias_uses_server_price(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload([self._familiar_item_payload(extra_lumpias=True)]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total_usd"], 23.0)
        self.assertEqual(
            [(row[0], row[1]) for row in self._orden_items(orden_id)],
            [("Familiar", 20.0), (web_app.PROMO_EXTRA_LUMPIAS_NOMBRE, 3.0)],
        )
        self.assertEqual(self._request_item_rows()[0][4], 23.0)

    def test_public_submit_invalid_configuration_rolls_back_all_tables(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        invalid = self._familiar_item_payload()
        invalid["configuracion"] = [
            {"titulo": "Pollos", "valores": ["Pollo BBQ"]},
            {"titulo": "Arroces", "valores": ["Triple"]},
            {"titulo": "Sabores", "valores": ["Coca Cola"]},
            {"titulo": "Extra", "valores": ["Extra inventado"]},
        ]

        response = self._post_submit(token, self._submit_payload([invalid]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_second_invalid_item_rolls_back_first(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        invalid = self._simple_item_payload("Refresco 1 Lt", configuracion=[
            {"titulo": "Sabores", "valores": [""]}
        ])

        response = self._post_submit(
            token,
            self._submit_payload([self._simple_item_payload(), invalid]),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_same_submission_id_is_idempotent(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        payload = self._submit_payload([self._simple_item_payload()], submission_id="retry-12345")

        first = self._post_submit(token, payload)
        second = self._post_submit(token, payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.get_json()["idempotente"])
        self.assertTrue(second.get_json()["idempotente"])
        self.assertEqual(first.get_json()["request_id"], second.get_json()["request_id"])
        self.assertEqual(first.get_json()["comanda_id"], second.get_json()["comanda_id"])
        self.assertEqual(self._table_counts(orden_id), (1, 1, 1))
        self.assertEqual(len(self._comandas(orden_id)), 1)

    def test_public_submit_creates_kitchen_comanda_for_exact_batch_items(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    self._simple_item_payload("Neko Clan Triple"),
                    self._simple_item_payload(
                        "Refresco 1 Lt",
                        configuracion=[{"titulo": "Sabores", "valores": ["Coca Cola"]}],
                    ),
                ],
                "batch-kitchen-1",
            ),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        comandas = self._comandas(orden_id)
        self.assertEqual(len(comandas), 1)
        self.assertEqual(comandas[0][2:], (0, "self_ordering", payload["request_id"], "en_cocina"))
        self.assertEqual(payload["comanda_id"], comandas[0][0])
        self.assertEqual(payload["comanda_secuencia"], 0)
        self.assertEqual([row[1] for row in self._comanda_items(comandas[0][0])], ["Neko Clan Triple", "Refresco 1 Lt"])
        self.assertEqual(self._order_state(orden_id)[0], "en cocina")

    def test_comanda_number_text_uses_sequence_without_changing_order_number(self):
        self.assertEqual(texto_numero_comanda(7, 0), "Orden 7")
        self.assertEqual(texto_numero_comanda(7, 1), "Orden 7.1")

    def test_public_submit_new_batch_creates_next_comanda_sequence_only_for_new_items(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        first = self._post_submit(token, self._submit_payload([self._simple_item_payload()], "batch-one-1"))
        second = self._post_submit(token, self._submit_payload([self._simple_item_payload()], "batch-two-2"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        comandas = self._comandas(orden_id)
        self.assertEqual([row[2] for row in comandas], [0, 1])
        self.assertEqual([len(self._comanda_items(row[0])) for row in comandas], [1, 1])
        self.assertNotEqual(first.get_json()["comanda_id"], second.get_json()["comanda_id"])

    def test_concurrent_self_order_submissions_reserve_unique_consecutive_sequences(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        product_id = self._producto_id("Neko Clan Triple")
        barrier = threading.Barrier(10)
        results = []
        lock = threading.Lock()

        def submit(index):
            client = web_app.app.test_client()
            payload = self._submit_payload(
                [
                    {
                        "producto_id": product_id,
                        "cantidad": 1,
                        "configuracion": [],
                        "indicacion": "",
                    }
                ],
                f"thread-submit-{index:02d}",
            )
            try:
                barrier.wait(timeout=10)
                response = client.post(f"/self-order/{token}/submit", json=payload)
                with lock:
                    results.append((response.status_code, response.get_json(silent=True)))
            except Exception as exc:
                with lock:
                    results.append(("error", str(exc)))

        threads = [threading.Thread(target=submit, args=(index,)) for index in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(len(results), 10)
        self.assertTrue(all(status == 200 for status, _ in results), results)
        comandas = self._comandas(orden_id)
        self.assertEqual(len(comandas), 10)
        self.assertEqual([row[2] for row in comandas], list(range(10)))
        self.assertEqual(self._table_counts(orden_id), (10, 10, 10))

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM orden_items oi
            LEFT JOIN orden_comanda_items ci ON ci.orden_item_id = oi.id
            WHERE oi.orden_id=? AND ci.id IS NULL
            """,
            (orden_id,),
        )
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()

    def test_comanda_sequence_allocator_does_not_depend_on_max_sequence_at_insert_time(self):
        import inspect
        from app.infrastructure.database import kitchen_comandas

        source = inspect.getsource(kitchen_comandas.crear_comanda_en_cursor)

        self.assertNotIn("MAX(secuencia)", source)
        self.assertIn("_reservar_secuencia_comanda", source)

    def test_cocina_renders_self_order_batches_as_separate_comanda_cards(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        self._post_submit(token, self._submit_payload([self._simple_item_payload()], "screen-one-1"))
        self._post_submit(
            token,
            self._submit_payload(
                [
                    self._simple_item_payload(
                        "Refresco 1 Lt",
                        configuracion=[{"titulo": "Sabores", "valores": ["Coca Cola"]}],
                    )
                ],
                "screen-two-2",
            ),
        )
        self._login(rol="cocina")

        response = self.client.get("/cocina")
        html_text = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Orden 1", html_text)
        self.assertIn("Orden 1.1", html_text)
        self.assertIn("/comanda/", html_text)
        self.assertNotIn('href="/listo/', html_text)

    def test_ordenes_cocina_json_returns_each_comanda_with_only_its_items(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        self._post_submit(token, self._submit_payload([self._simple_item_payload()], "json-one-1"))
        self._post_submit(
            token,
            self._submit_payload(
                [
                    self._simple_item_payload(
                        "Refresco 1 Lt",
                        configuracion=[{"titulo": "Sabores", "valores": ["Coca Cola"]}],
                    )
                ],
                "json-two-2",
            ),
        )

        response = web_app.app.test_client().get("/ordenes_cocina")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload), 2)
        self.assertEqual([item["secuencia"] for item in payload], [0, 1])
        self.assertEqual(payload[0]["items"], ["1x Neko Clan Triple"])
        self.assertEqual(payload[1]["items"], ["1x Refresco 1 Lt (Sabor: Coca Cola)"])

    def test_marking_one_comanda_ready_keeps_order_in_kitchen_until_all_ready(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        self._post_submit(token, self._submit_payload([self._simple_item_payload()], "ready-one-1"))
        self._post_submit(token, self._submit_payload([self._simple_item_payload()], "ready-two-2"))
        comandas = self._comandas(orden_id)
        self._login(rol="cocina")

        first = self.client.post(f"/comanda/{comandas[0][0]}/listo")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(self._order_state(orden_id)[0], "en cocina")
        self.assertEqual([row[5] for row in self._comandas(orden_id)], ["listo", "en_cocina"])

        second = self.client.post(f"/comanda/{comandas[1][0]}/listo")
        self.assertEqual(second.status_code, 302)
        self.assertEqual(self._order_state(orden_id)[0], "listo")
        self.assertEqual([row[5] for row in self._comandas(orden_id)], ["listo", "listo"])

    def test_manual_send_to_kitchen_creates_comanda_for_unsent_items_only(self):
        orden_id = self._create_order()
        first_item = self._insert_order_item(orden_id, "Neko Clan Triple", 13.0)

        first = self.client.get(f"/enviar_cocina/{orden_id}")
        self.assertEqual(first.status_code, 302)
        first_comanda = self._comandas(orden_id)[0]
        self.assertEqual(first_comanda[2:], (0, "manual", None, "en_cocina"))
        self.assertEqual([row[0] for row in self._comanda_items(first_comanda[0])], [first_item])

        second_item = self._insert_order_item(orden_id, "Refresco 1 Lt", 2.0)
        second = self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(second.status_code, 302)
        comandas = self._comandas(orden_id)
        self.assertEqual([row[2] for row in comandas], [0, 1])
        self.assertEqual([row[0] for row in self._comanda_items(comandas[1][0])], [second_item])

    def test_mixed_manual_and_self_ordering_batches_share_one_sequence_by_item_id(self):
        orden_id = self._create_order()
        item_a = self._insert_order_item(orden_id, "Manual A", 1.0)
        item_b = self._insert_order_item(orden_id, "Manual B", 2.0)
        self.client.get(f"/enviar_cocina/{orden_id}")

        item_c = self._insert_order_item(orden_id, "Manual C", 3.0)
        self.client.get(f"/enviar_cocina/{orden_id}")

        token = self._link_token_for_order(orden_id)
        response = self._post_submit(token, self._submit_payload([self._simple_item_payload()], "mixed-self-1"))
        self.assertEqual(response.status_code, 200)
        self_order_item = self._comanda_items(response.get_json()["comanda_id"])[0][0]

        item_e = self._insert_order_item(orden_id, "Manual E", 5.0)
        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual([row[2] for row in comandas], [0, 1, 2, 3])
        self.assertEqual([row[0] for row in self._comanda_items(comandas[0][0])], [item_a, item_b])
        self.assertEqual([row[0] for row in self._comanda_items(comandas[1][0])], [item_c])
        self.assertEqual([row[0] for row in self._comanda_items(comandas[2][0])], [self_order_item])
        self.assertEqual([row[0] for row in self._comanda_items(comandas[3][0])], [item_e])

    def test_legacy_kitchen_order_without_comanda_still_appears_without_duplication(self):
        orden_id = self._create_order()
        self._insert_order_item(orden_id, "Legacy Item", 4.0)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE ordenes SET estado='en cocina', numero_orden=15 WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()
        self._login(rol="cocina")

        cocina_response = self.client.get("/cocina")
        cocina_html = cocina_response.data.decode("utf-8")
        json_response = web_app.app.test_client().get("/ordenes_cocina")
        payload = json_response.get_json()

        self.assertEqual(cocina_response.status_code, 200)
        self.assertIn("Orden #15", cocina_html)
        self.assertIn("Legacy Item", cocina_html)
        self.assertEqual(cocina_html.count("Legacy Item"), 1)
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(len(payload), 1)
        self.assertIsNone(payload[0]["comanda_id"])
        self.assertEqual(payload[0]["items"], ["1x Legacy Item"])

    def test_public_submit_rolls_back_everything_if_comanda_creation_fails(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        with mock.patch(
            "app.infrastructure.database.self_ordering_submit.crear_comanda_en_cursor",
            side_effect=RuntimeError("fallo comanda"),
        ):
            response = self._post_submit(
                token,
                self._submit_payload([self._simple_item_payload()], "rollback-comanda-1"),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))
        self.assertEqual(self._comandas(orden_id), [])
        self.assertEqual(self._order_state(orden_id)[0], "abierta")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(proxima_secuencia_comanda, 0) FROM ordenes WHERE id=?", (orden_id,))
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()

    def test_public_submit_new_submission_id_creates_new_batch(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        first = self._post_submit(token, self._submit_payload([self._simple_item_payload()], "first-12345"))
        second = self._post_submit(token, self._submit_payload([self._simple_item_payload()], "second-12345"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.get_json()["request_id"], second.get_json()["request_id"])
        self.assertEqual(self._table_counts(orden_id), (2, 2, 2))

    def test_public_submit_closed_order_is_blocked_without_mutation(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        self._update_order(orden_id, estado="cerrada")

        response = self._post_submit(token, self._submit_payload([self._simple_item_payload()]))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_browser_cannot_control_destination_order(self):
        mesa_3 = self._create_order(referencia="mesa:3")
        mesa_4 = self._create_order(referencia="mesa:4")
        token = self._link_token_for_order(mesa_3)
        item = self._simple_item_payload(orden_id=mesa_4)

        response = self._post_submit(token, self._submit_payload([item]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._table_counts(mesa_3), (1, 1, 1))
        self.assertEqual(len(self._orden_items(mesa_4)), 0)

    def test_public_submit_security_validation_rejects_bad_payloads(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        cases = [
            self._submit_payload([self._simple_item_payload(cantidad=0)], "qty-zero-1"),
            self._submit_payload([self._simple_item_payload(cantidad=-1)], "qty-neg-1"),
            self._submit_payload([self._simple_item_payload(cantidad=99)], "qty-big-1"),
            {"submission_id": "bad", "items": [self._simple_item_payload()]},
        ]

        for payload in cases:
            with self.subTest(payload=payload["submission_id"]):
                response = self._post_submit(token, payload)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_inactive_product_is_rejected(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        category_id = self._create_category("Bebidas Auditoria", activo=1)
        producto_id = self._create_product("Refresco Auditoria Inactivo", 2.0, category_id, activo=0)

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    {
                        "producto_id": producto_id,
                        "cantidad": 1,
                        "configuracion": [{"titulo": "Sabores", "valores": ["Coca Cola"]}],
                    }
                ]
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_invalid_token_is_rejected(self):
        response = self._post_submit(
            "token-inexistente",
            self._submit_payload([self._simple_item_payload()]),
        )

        self.assertEqual(response.status_code, 404)

    def test_public_submit_rejects_non_object_or_malformed_json_root(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        client = web_app.app.test_client()
        cases = [
            ("array", '["a", "b"]'),
            ("string", '"texto"'),
            ("number", "123"),
            ("boolean", "true"),
            ("null", "null"),
            ("malformed", '{"submission_id"'),
        ]

        for _, body in cases:
            response = client.post(
                f"/self-order/{token}/submit",
                data=body,
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"], "Payload invalido.")

        ok = self._post_submit(
            token,
            self._submit_payload([self._simple_item_payload()], "json-valid-123"),
        )
        self.assertEqual(ok.status_code, 200)

    def test_public_submit_rejects_single_select_over_cardinality_without_mutation(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)
        cases = [
            self._familiar_item_payload(
                configuracion=[
                    {"titulo": "Pollos", "valores": ["Pollo BBQ", "Pollo Agridulce"]},
                    {"titulo": "Arroces", "valores": ["Triple"]},
                    {"titulo": "Sabores", "valores": ["Coca Cola"]},
                    {"titulo": "Extra", "valores": []},
                ]
            ),
            self._combo_item_payload(
                configuracion=[
                    {"titulo": "Acompanantes", "valores": ["Pollo BBQ"]},
                    {"titulo": "Bebidas", "valores": ["Coca Cola", "Frescolita"]},
                ]
            ),
            self._simple_item_payload(
                "Refresco 1 Lt",
                configuracion=[{"titulo": "Sabores", "valores": ["Coca Cola", "Frescolita"]}],
            ),
        ]

        for index, item in enumerate(cases, start=1):
            response = self._post_submit(
                token,
                self._submit_payload([item], f"single-over-{index}"),
            )
            self.assertEqual(response.status_code, 400)

        self.assertEqual(self._table_counts(orden_id), (0, 0, 0))

    def test_public_submit_preserves_customer_note_for_simple_item(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [self._simple_item_payload(indicacion="sin cebolla por favor")],
                "note-simple-123",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._orden_items(orden_id)[0][2], "sin cebolla por favor")

    def test_public_submit_preserves_promotion_configuration_and_customer_note(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [self._familiar_item_payload(indicacion="sin cebolla por favor")],
                "note-promo-123",
            ),
        )

        self.assertEqual(response.status_code, 200)
        indicacion = self._orden_items(orden_id)[0][2]
        datos = deserializar_indicacion(indicacion)
        self.assertEqual(datos["tipo"], "promocion")
        self.assertEqual(datos["nota"], "sin cebolla por favor")
        self.assertEqual(datos["pollo"], "Pollo BBQ")

    def test_public_submit_preserves_combo_configuration_and_customer_note(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [self._combo_item_payload(indicacion="sin cebolla por favor")],
                "note-combo-123",
            ),
        )

        self.assertEqual(response.status_code, 200)
        indicacion = self._orden_items(orden_id)[0][2]
        datos = deserializar_indicacion(indicacion)
        self.assertEqual(datos["tipo"], "combo")
        self.assertEqual(datos["nota"], "sin cebolla por favor")
        self.assertEqual(datos["bebida"], "Coca Cola")

    def test_public_submit_preserves_soda_flavor_and_customer_note(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [
                    self._simple_item_payload(
                        "Refresco 1 Lt",
                        configuracion=[{"titulo": "Sabores", "valores": ["Coca Cola"]}],
                        indicacion="bien frio",
                    )
                ],
                "note-soda-123",
            ),
        )

        self.assertEqual(response.status_code, 200)
        indicacion = self._orden_items(orden_id)[0][2]
        self.assertIn("Sabor: Coca Cola", indicacion)
        self.assertIn("Nota: bien frio", indicacion)

    def test_public_submit_empty_note_keeps_current_structured_indication(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload([self._familiar_item_payload()], "note-empty-123"),
        )

        self.assertEqual(response.status_code, 200)
        datos = deserializar_indicacion(self._orden_items(orden_id)[0][2])
        self.assertEqual(datos["tipo"], "promocion")
        self.assertNotIn("nota", datos)

    def test_public_submit_html_note_is_stored_as_text_and_order_screen_escapes_it(self):
        orden_id = self._create_order()
        token = self._link_token_for_order(orden_id)

        response = self._post_submit(
            token,
            self._submit_payload(
                [self._simple_item_payload(indicacion="<script>alert(1)</script>")],
                "note-html-123",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._orden_items(orden_id)[0][2], "<script>alert(1)</script>")
        order_response = self.client.get(f"/orden/{orden_id}")
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", order_response.data)
        self.assertNotIn(b"<script>alert(1)</script>", order_response.data)

    def test_public_catalog_frontend_posts_intent_without_prices_or_order_id(self):
        html_text = self._public_catalog_html()

        self.assertIn('id="sendRequest"', html_text)
        self.assertIn('fetch(submitUrl', html_text)
        self.assertIn("crypto.randomUUID", html_text)
        self.assertIn("Pedido enviado correctamente", html_text)
        self.assertIn("producto_id: item.productId", html_text)
        self.assertIn("cantidad: item.quantity", html_text)
        self.assertIn("indicacion: item.indication || \"\"", html_text)
        self.assertNotIn("precio_unitario", html_text)
        self.assertNotIn("subtotal_usd", html_text)
        self.assertNotIn("orden_id", html_text)


if __name__ == "__main__":
    unittest.main()
