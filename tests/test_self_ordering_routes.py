import unittest


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

    def _category_section(self, html_text, section_index):
        marker = f'id="categoria-{section_index}"'
        start = html_text.index(marker)
        section_start = html_text.rfind("<section", 0, start)
        section_end = html_text.index("</section>", start)
        return html_text[section_start:section_end]

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


if __name__ == "__main__":
    unittest.main()
