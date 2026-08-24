import importlib
import os
import tempfile
import unittest
from unittest import mock


TEST_DB = tempfile.NamedTemporaryFile(prefix="neko_snapshot_", suffix=".db", delete=False)
TEST_DB.close()

os.environ["APP_ENV"] = "test"
os.environ["TEST_SQLITE_PATH"] = TEST_DB.name

web_app = importlib.import_module("web_app")


class SalesSnapshotTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(TEST_DB.name)
        except OSError:
            pass

    def setUp(self):
        self.app = web_app.app
        self.client = self.app.test_client()
        self._clear_operational_data()
        self._set_tasa(200)
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = self._master_user_id()
            sess["usuario_nombre"] = "Emmanuel"
            sess["usuario"] = "Emmanuel"
            sess["usuario_rol"] = "master"

    def _conn(self):
        return web_app.get_connection()

    def _clear_operational_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in (
            "delivery_movimientos",
            "cuentas_por_cobrar_movimientos",
            "cuentas_por_cobrar",
            "pagos",
            "orden_items",
            "ordenes",
            "repartidores",
            "clientes",
            "cierre_detalle",
            "cierres_caja",
            "movimientos_inventario",
            "auditoria_emergencias",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _master_user_id(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE rol='master' ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row[0]

    def _set_tasa(self, value):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE tasa SET valor=?", (value,))
        conn.commit()
        conn.close()

    def _create_order(self, price=10.0, estado="abierta"):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (
                numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "2026-08-20 12:00:00", "2026-08-20", "mesa", "A1", "Test", estado, self._master_user_id()),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, ?)",
            (orden_id, "Producto prueba", price, ""),
        )
        conn.commit()
        conn.close()
        return orden_id

    def _charge(
        self,
        orden_id,
        metodo1,
        monto1,
        metodo2="",
        monto2="",
        descuento=0,
        modo_cobro="pagado",
        cliente_id="",
    ):
        return self.client.post(
            f"/cobrar/{orden_id}",
            data={
                "modo_cobro": modo_cobro,
                "cliente_id": str(cliente_id),
                "metodo1": metodo1,
                "monto1": str(monto1),
                "ref1": "ref1",
                "metodo2": metodo2,
                "monto2": str(monto2),
                "ref2": "ref2",
                "descuento": str(descuento),
            },
            follow_redirects=False,
        )

    def _charge_legacy_payload(
        self, orden_id, metodo1, monto1, metodo2="", monto2="", descuento=0
    ):
        return self.client.post(
            f"/cobrar/{orden_id}",
            data={
                "metodo1": metodo1,
                "monto1": str(monto1),
                "ref1": "ref1",
                "metodo2": metodo2,
                "monto2": str(monto2),
                "ref2": "ref2",
                "descuento": str(descuento),
            },
            follow_redirects=False,
        )

    def _snapshot(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT estado, fecha_cobro, tasa_cobro, subtotal_usd,
                   descuento_bs_snapshot, total_usd, total_bs, descuento
            FROM ordenes
            WHERE id=?
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            "SELECT metodo, monto, referencia, fecha FROM pagos WHERE orden_id=? ORDER BY id",
            (orden_id,),
        )
        pagos = cursor.fetchall()
        conn.close()
        return row, pagos

    def _financial_snapshot(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT estado, fecha_venta, fecha_cobro, tasa_cobro, subtotal_usd,
                   descuento_bs_snapshot, total_usd, total_bs,
                   venta_restaurante_usd, delivery_usd, total_cliente_usd,
                   delivery_repartidor_id, inventario_descontado
            FROM ordenes
            WHERE id=?
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def _delivery_movements(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT repartidor_id, tipo, monto_usd, usuario_id, observacion
            FROM delivery_movimientos
            WHERE orden_id=?
            ORDER BY id
            """,
            (orden_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _order_cxc_state(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT fecha_venta, fecha_cobro, cliente_id, cliente,
                   tasa_cobro, subtotal_usd, descuento_bs_snapshot, total_usd, total_bs
            FROM ordenes
            WHERE id=?
            """,
            (orden_id,),
        )
        orden = cursor.fetchone()
        cursor.execute(
            """
            SELECT cx.id, cx.cliente_id, cx.cliente_nombre_snapshot,
                   cx.moneda_saldo, cx.monto_original_deuda, cx.saldo_pendiente,
                   cx.estado, m.tipo, m.monto_saldo, m.fecha
            FROM cuentas_por_cobrar cx
            JOIN cuentas_por_cobrar_movimientos m ON m.cuenta_id = cx.id
            WHERE cx.orden_id=?
            ORDER BY m.id
            """,
            (orden_id,),
        )
        movimientos = cursor.fetchall()
        conn.close()
        return orden, movimientos

    def _inventory_discounted(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT inventario_descontado FROM ordenes WHERE id=?", (orden_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0]

    def _columns(self, table):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1]: row for row in cursor.fetchall()}
        conn.close()
        return columns

    def _table_names(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in cursor.fetchall()}
        conn.close()
        return names

    def _insert_repartidor(self, nombre="Juan Delivery", activo=1):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO repartidores (nombre, telefono, notas, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nombre, "0412-3333333", "Repartidor de prueba", activo, "2026-08-23 10:00:00"),
        )
        repartidor_id = web_app.obtener_ultimo_id(cursor, "repartidores")
        conn.commit()
        conn.close()
        return repartidor_id

    def _insert_delivery_movimiento(
        self,
        repartidor_id,
        tipo="cargo",
        monto=3.0,
        orden_id=None,
        movimiento_revertido_id=None,
    ):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO delivery_movimientos (
                orden_id, repartidor_id, tipo, monto_usd, fecha,
                usuario_id, referencia, observacion, movimiento_revertido_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                orden_id,
                repartidor_id,
                tipo,
                monto,
                "2026-08-23 10:05:00",
                self._master_user_id(),
                "delivery-test",
                "Movimiento de prueba",
                movimiento_revertido_id,
            ),
        )
        movimiento_id = web_app.obtener_ultimo_id(cursor, "delivery_movimientos")
        conn.commit()
        conn.close()
        return movimiento_id

    def _delivery_product_id(self, nombre="Delivery 3"):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM productos WHERE nombre=? ORDER BY id LIMIT 1", (nombre,))
        row = cursor.fetchone()
        conn.close()
        return row[0]

    def _delivery_state(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT delivery_usd, delivery_repartidor_id
            FROM ordenes
            WHERE id=?
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        cursor.execute("SELECT producto, precio FROM orden_items WHERE orden_id=? ORDER BY id", (orden_id,))
        items = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM delivery_movimientos")
        delivery_movimientos = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM movimientos_inventario")
        inventario_movimientos = cursor.fetchone()[0]
        conn.close()
        return row, items, delivery_movimientos, inventario_movimientos

    def _set_delivery(self, orden_id, monto, repartidor_id=""):
        return self.client.post(
            f"/orden/{orden_id}/delivery",
            data={
                "delivery_usd": str(monto),
                "delivery_repartidor_id": str(repartidor_id),
            },
            follow_redirects=False,
        )

    def _create_order_with_delivery(self, price=20.0, delivery=3.0, repartidor_id=None):
        if repartidor_id is None:
            repartidor_id = self._insert_repartidor("Repartidor Cobro", activo=1)
        orden_id = self._create_order(price=price)
        response = self._set_delivery(orden_id, delivery, repartidor_id)
        self.assertEqual(response.status_code, 302)
        return orden_id, repartidor_id

    def test_delivery_schema_tables_columns_and_nullable_order_fields(self):
        self.assertIn("repartidores", self._table_names())
        self.assertIn("delivery_movimientos", self._table_names())

        orden_columns = self._columns("ordenes")
        for column in (
            "venta_restaurante_usd",
            "delivery_usd",
            "total_cliente_usd",
            "delivery_repartidor_id",
        ):
            with self.subTest(column=column):
                self.assertIn(column, orden_columns)
                self.assertEqual(orden_columns[column][3], 0)
                self.assertIsNone(orden_columns[column][4])

        repartidor_columns = self._columns("repartidores")
        self.assertEqual(repartidor_columns["nombre"][2].upper(), "TEXT")
        self.assertEqual(repartidor_columns["nombre"][3], 1)
        self.assertEqual(repartidor_columns["activo"][4], "1")
        for column in ("id", "telefono", "notas", "fecha_creacion"):
            self.assertIn(column, repartidor_columns)

        movimiento_columns = self._columns("delivery_movimientos")
        for column in (
            "id",
            "orden_id",
            "repartidor_id",
            "tipo",
            "monto_usd",
            "fecha",
            "usuario_id",
            "referencia",
            "observacion",
            "movimiento_revertido_id",
        ):
            self.assertIn(column, movimiento_columns)
        self.assertEqual(movimiento_columns["repartidor_id"][3], 1)
        self.assertEqual(movimiento_columns["tipo"][3], 1)
        self.assertEqual(movimiento_columns["monto_usd"][3], 1)

    def test_delivery_schema_idempotence_preserves_data_and_columns(self):
        repartidor_id = self._insert_repartidor("Idempotente")
        self._insert_delivery_movimiento(repartidor_id, "cargo", 3.0)

        before_orden_columns = list(self._columns("ordenes"))
        before_tables = self._table_names()
        web_app.init_db()
        web_app.init_db()
        after_orden_columns = list(self._columns("ordenes"))
        after_tables = self._table_names()

        self.assertEqual(before_orden_columns, after_orden_columns)
        self.assertEqual(before_tables, after_tables)
        self.assertEqual(len(after_orden_columns), len(set(after_orden_columns)))

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, activo FROM repartidores WHERE id=?", (repartidor_id,))
        repartidor = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM delivery_movimientos WHERE repartidor_id=?", (repartidor_id,))
        movimientos = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(repartidor, ("Idempotente", 1))
        self.assertEqual(movimientos, 1)

    def test_repartidores_require_name_and_preserve_active_state(self):
        activo_id = self._insert_repartidor("Activo", activo=1)
        inactivo_id = self._insert_repartidor("Inactivo", activo=0)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT activo FROM repartidores WHERE id=?", (activo_id,))
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("SELECT activo FROM repartidores WHERE id=?", (inactivo_id,))
        self.assertEqual(cursor.fetchone()[0], 0)
        with self.assertRaises(Exception):
            cursor.execute(
                "INSERT INTO repartidores (nombre, activo, fecha_creacion) VALUES (?, ?, ?)",
                (None, 1, "2026-08-23 10:00:00"),
            )
        conn.rollback()
        conn.close()

    def test_delivery_movimientos_signed_deltas_types_and_annulment_reference(self):
        repartidor_id = self._insert_repartidor("Movimientos")
        cargo_id = self._insert_delivery_movimiento(repartidor_id, "cargo", 3.0)
        self._insert_delivery_movimiento(repartidor_id, "pago", -3.0)
        self._insert_delivery_movimiento(repartidor_id, "ajuste", 2.0)
        self._insert_delivery_movimiento(repartidor_id, "ajuste", -1.0)
        self._insert_delivery_movimiento(
            repartidor_id,
            "anulacion",
            -3.0,
            movimiento_revertido_id=cargo_id,
        )

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ROUND(COALESCE(SUM(monto_usd), 0), 2)
            FROM delivery_movimientos
            WHERE repartidor_id=?
            """,
            (repartidor_id,),
        )
        self.assertEqual(cursor.fetchone()[0], -2.0)
        cursor.execute(
            """
            SELECT tipo, monto_usd, movimiento_revertido_id
            FROM delivery_movimientos
            WHERE tipo='anulacion'
            """
        )
        self.assertEqual(cursor.fetchone(), ("anulacion", -3.0, cargo_id))
        with self.assertRaises(Exception):
            cursor.execute(
                """
                INSERT INTO delivery_movimientos (repartidor_id, tipo, monto_usd)
                VALUES (?, ?, ?)
                """,
                (repartidor_id, "invalido", 1.0),
            )
        conn.rollback()
        conn.close()

    def test_legacy_order_delivery_fields_remain_unknown_null(self):
        orden_id = self._create_order(price=20.0, estado="cerrada")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT venta_restaurante_usd, delivery_usd, total_cliente_usd,
                   delivery_repartidor_id
            FROM ordenes
            WHERE id=?
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row, (None, None, None, None))

    def test_delivery_phase_one_does_not_change_existing_checkout_and_cxc_snapshots(self):
        cliente_id = self._create_client("Cliente Regresion Delivery")
        pagado = self._create_order(price=10.0)
        parcial = self._create_order(price=20.0)
        credito = self._create_order(price=15.0)

        self.assertEqual(self._charge(pagado, "usd", 10).status_code, 302)
        self.assertEqual(
            self._charge(parcial, "usd", 12, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )
        self.assertEqual(
            self._charge(credito, "", 0, modo_cobro="credito", cliente_id=cliente_id).status_code,
            302,
        )

        snapshot_pagado, pagos_pagado = self._snapshot(pagado)
        self.assertEqual(snapshot_pagado[2:7], (200.0, 10.0, 0.0, 10.0, 2000.0))
        self.assertEqual([(p[0], p[1]) for p in pagos_pagado], [("usd", 10.0)])
        self.assertEqual(self._cuenta_por_orden(parcial)[1:3], (8.0, "pendiente"))
        self.assertEqual(self._cuenta_por_orden(credito)[1:3], (15.0, "pendiente"))

        cxc_admin = self.client.get("/cuentas_por_cobrar")
        self.assertEqual(cxc_admin.status_code, 200)
        self.assertIn(b"Cliente Regresion Delivery", cxc_admin.data)

    def test_repartidores_admin_lists_creates_edits_and_toggles_without_delete(self):
        response = self.client.get("/repartidores")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Nuevo repartidor", response.data)

        response = self.client.post(
            "/repartidores/nuevo",
            data={"nombre": "Juan Moto", "telefono": "0412", "notas": "Zona centro"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM repartidores WHERE nombre='Juan Moto'")
        repartidor_id = cursor.fetchone()[0]
        conn.close()

        response = self.client.get("/repartidores")
        self.assertIn(b"Juan Moto", response.data)
        self.assertIn(b"0412", response.data)

        response = self.client.post(
            f"/repartidores/{repartidor_id}/editar",
            data={"nombre": "Juan Editado", "telefono": "0414", "notas": "Actualizado"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(f"/repartidores/{repartidor_id}/activar", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, telefono, notas, activo FROM repartidores WHERE id=?", (repartidor_id,))
        self.assertEqual(cursor.fetchone(), ("Juan Editado", "0414", "Actualizado", 0))
        conn.close()

    def test_repartidores_reject_empty_name_and_inactive_not_selectable_for_new_delivery(self):
        response = self.client.post("/repartidores/nuevo", data={"nombre": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertIn("nombre del repartidor es obligatorio".encode(), response.data)

        activo_id = self._insert_repartidor("Repartidor Activo", activo=1)
        inactivo_id = self._insert_repartidor("Repartidor Inactivo", activo=0)
        orden_id = self._create_order(price=10.0)

        page = self.client.get(f"/orden/{orden_id}")
        self.assertIn(b"Repartidor Activo", page.data)
        self.assertNotIn(b"Repartidor Inactivo", page.data)
        self.assertEqual(self._set_delivery(orden_id, 3, activo_id).status_code, 302)
        self.assertEqual(self._set_delivery(self._create_order(price=10.0), 3, inactivo_id).status_code, 400)

    def test_repartidor_deactivation_preserves_order_history(self):
        repartidor_id = self._insert_repartidor("Historial Delivery", activo=1)
        orden_id = self._create_order(price=10.0)
        self.assertEqual(self._set_delivery(orden_id, 3, repartidor_id).status_code, 302)
        self.assertEqual(self.client.post(f"/repartidores/{repartidor_id}/activar").status_code, 302)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT activo FROM repartidores WHERE id=?", (repartidor_id,))
        self.assertEqual(cursor.fetchone()[0], 0)
        cursor.execute("SELECT delivery_repartidor_id FROM ordenes WHERE id=?", (orden_id,))
        self.assertEqual(cursor.fetchone()[0], repartidor_id)
        conn.close()

    def test_quick_repartidor_api_creates_active_repartidor(self):
        response = self.client.post("/api/repartidores", json={"nombre": "Rapido", "telefono": "0416"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["repartidor"]["nombre"], "Rapido")

        listado = self.client.get("/api/repartidores").get_json()["repartidores"]
        self.assertIn("Rapido", [rep["nombre"] for rep in listado])

    def test_delivery_admin_route_requires_master_and_renders_summary(self):
        response = self.client.get("/delivery")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Delivery generado".encode(), response.data)
        self.assertIn("Cantidad de servicios".encode(), response.data)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)",
            ("Mesonera Delivery", "0000", "mesonera"),
        )
        usuario_id = web_app.obtener_ultimo_id(cursor, "usuarios")
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["usuario_id"] = usuario_id
            sess["usuario_nombre"] = "Mesonera Delivery"
            sess["usuario"] = "Mesonera Delivery"
            sess["usuario_rol"] = "mesonera"

        self.assertEqual(self.client.get("/delivery").status_code, 403)

    def test_delivery_admin_summary_and_multiple_repartidores(self):
        juan_id = self._insert_repartidor("Juan", activo=1)
        pedro_id = self._insert_repartidor("Pedro", activo=1)

        for monto in (3, 2):
            self._insert_delivery_movimiento(juan_id, "cargo", monto, orden_id=self._create_order())
        self._insert_delivery_movimiento(juan_id, "pago", -4)
        for monto in (3, 4):
            self._insert_delivery_movimiento(pedro_id, "cargo", monto, orden_id=self._create_order())
        self._insert_delivery_movimiento(pedro_id, "pago", -2)

        conn = self._conn()
        cursor = conn.cursor()
        resumen = web_app.resumen_delivery_admin(cursor)
        repartidores = {
            row[1]: {
                "servicios": row[3],
                "generado": row[4],
                "pagado": row[5],
                "pendiente": row[6],
            }
            for row in web_app.resumen_delivery_por_repartidor(cursor)
        }
        conn.close()

        self.assertEqual(resumen, {"generado": 12.0, "pagado": 6.0, "pendiente": 6.0, "servicios": 4})
        self.assertEqual(repartidores["Juan"], {"servicios": 2, "generado": 5.0, "pagado": 4.0, "pendiente": 1.0})
        self.assertEqual(repartidores["Pedro"], {"servicios": 2, "generado": 7.0, "pagado": 2.0, "pendiente": 5.0})

        response = self.client.get("/delivery")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Juan", response.data)
        self.assertIn(b"Pedro", response.data)
        self.assertIn(b"$ 12.00", response.data)
        self.assertIn(b"$ 6.00", response.data)

    def test_delivery_admin_shows_inactive_repartidor_with_movements(self):
        inactivo_id = self._insert_repartidor("Repartidor Inactivo", activo=0)
        self._insert_delivery_movimiento(inactivo_id, "cargo", 5, orden_id=self._create_order())

        response = self.client.get("/delivery")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Repartidor Inactivo", response.data)
        self.assertIn(b"Inactivo", response.data)
        self.assertIn(b"$ 5.00", response.data)

    def test_order_without_delivery_shows_zero_visual_delivery(self):
        orden_id = self._create_order(price=20.0)
        response = self.client.get(f"/orden/{orden_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Delivery: $0.00", response.data)
        self.assertIn(b"Total cliente: $20.00", response.data)

    def test_delivery_save_validations_and_updates_without_touching_items_movements_or_inventory(self):
        repartidor_id = self._insert_repartidor("Valido Delivery", activo=1)
        orden_id = self._create_order(price=20.0)
        before = self._delivery_state(orden_id)

        self.assertEqual(self._set_delivery(orden_id, 3, repartidor_id).status_code, 302)
        state, items, delivery_movimientos, inventario_movimientos = self._delivery_state(orden_id)
        self.assertEqual(state, (3.0, repartidor_id))
        self.assertEqual(items, before[1])
        self.assertEqual(delivery_movimientos, 0)
        self.assertEqual(inventario_movimientos, 0)

        response = self.client.get(f"/orden/{orden_id}")
        self.assertIn(b"Consumo Neko Wok: $20.00", response.data)
        self.assertIn(b"Delivery: $3.00", response.data)
        self.assertIn(b"Total cliente: $23.00", response.data)

        self.assertEqual(self._set_delivery(orden_id, 2, repartidor_id).status_code, 302)
        self.assertEqual(self._delivery_state(orden_id)[0], (2.0, repartidor_id))
        self.assertEqual(self._set_delivery(orden_id, 0, "").status_code, 302)
        self.assertEqual(self._delivery_state(orden_id)[0], (0.0, None))

    def test_delivery_rejects_negative_invalid_and_inactive_repartidor(self):
        repartidor_id = self._insert_repartidor("Activo Validacion", activo=1)
        inactivo_id = self._insert_repartidor("Inactivo Validacion", activo=0)

        for monto, repartidor, mensaje in (
            (-1, repartidor_id, b"maximo 2 decimales"),
            (3, 999999, b"repartidor activo"),
            (3, inactivo_id, b"repartidor activo"),
            ("1.999", repartidor_id, b"maximo 2 decimales"),
        ):
            with self.subTest(monto=monto, repartidor=repartidor):
                orden_id = self._create_order(price=10.0)
                response = self._set_delivery(orden_id, monto, repartidor)
                self.assertEqual(response.status_code, 400)
                self.assertIn(mensaje, response.data)
                self.assertEqual(self._delivery_state(orden_id)[0], (None, None))

    def test_delivery_allows_pending_repartidor_then_later_assignment_without_touching_items(self):
        repartidor_id = self._insert_repartidor("Asignacion Diferida", activo=1)
        orden_id = self._create_order(price=20.0)
        before = self._delivery_state(orden_id)

        response = self._set_delivery(orden_id, 3, "")
        self.assertEqual(response.status_code, 302)
        state, items, delivery_movimientos, inventario_movimientos = self._delivery_state(orden_id)
        self.assertEqual(state, (3.0, None))
        self.assertEqual(items, before[1])
        self.assertEqual(delivery_movimientos, 0)
        self.assertEqual(inventario_movimientos, 0)

        page = self.client.get(f"/orden/{orden_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Repartidor: Pendiente de asignar", page.data)
        self.assertIn(b"Delivery: $3.00", page.data)

        response = self._set_delivery(orden_id, 3, repartidor_id)
        self.assertEqual(response.status_code, 302)
        state, items, delivery_movimientos, inventario_movimientos = self._delivery_state(orden_id)
        self.assertEqual(state, (3.0, repartidor_id))
        self.assertEqual(items, before[1])
        self.assertEqual(delivery_movimientos, 0)
        self.assertEqual(inventario_movimientos, 0)

    def test_delivery_pending_repartidor_blocks_checkout_without_financial_writes_then_charges_after_assignment(self):
        repartidor_id = self._insert_repartidor("Cobro Asignado", activo=1)
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._set_delivery(orden_id, 3, "").status_code, 302)
        snapshot_before = self._financial_snapshot(orden_id)

        response = self._charge(orden_id, "usd", 23)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Debes asignar un repartidor antes de cobrar esta orden.", response.data)
        self.assertEqual(self._financial_snapshot(orden_id), snapshot_before)
        self.assertEqual(self._snapshot(orden_id)[1], [])
        self.assertEqual(self._cuenta_por_orden(orden_id), None)
        self.assertEqual(self._delivery_movements(orden_id), [])

        self.assertEqual(self._set_delivery(orden_id, 3, repartidor_id).status_code, 302)
        response = self._charge(orden_id, "usd", 23)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._financial_snapshot(orden_id)[8:12], (20.0, 3.0, 23.0, repartidor_id))
        self.assertEqual(self._delivery_movements(orden_id)[0][0:3], (repartidor_id, "cargo", 3.0))

    def test_delivery_zero_does_not_require_repartidor_and_clears_assignment(self):
        repartidor_id = self._insert_repartidor("Delivery Cero", activo=1)
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._set_delivery(orden_id, 3, repartidor_id).status_code, 302)
        self.assertEqual(self._set_delivery(orden_id, 0, "").status_code, 302)
        self.assertEqual(self._delivery_state(orden_id)[0], (0.0, None))
        self.assertEqual(self._charge(orden_id, "usd", 20).status_code, 302)
        self.assertEqual(self._delivery_movements(orden_id), [])

    def test_delivery_legacy_products_are_preserved_hidden_and_blocked_for_new_adds(self):
        delivery_id = self._delivery_product_id("Delivery 3")
        self.assertIsNotNone(delivery_id)

        orden_id = self._create_order(price=20.0)
        page = self.client.get(f"/orden/{orden_id}")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"Delivery 3", page.data)

        response = self.client.get(f"/agregar/{orden_id}/{delivery_id}")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"delivery ahora se registra", response.data)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, '')",
            (orden_id, "Delivery 3", 3.0),
        )
        conn.commit()
        conn.close()

        page = self.client.get(f"/orden/{orden_id}")
        self.assertIn(b"Delivery 3", page.data)
        self.assertIn("sistema anterior".encode(), page.data)

    def test_open_order_with_legacy_delivery_is_not_auto_converted_and_blocks_explicit_delivery(self):
        repartidor_id = self._insert_repartidor("Bloqueo Legacy", activo=1)
        orden_id = self._create_order(price=20.0)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, '')",
            (orden_id, "Delivery 3", 3.0),
        )
        conn.commit()
        conn.close()

        response = self._set_delivery(orden_id, 3, repartidor_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("sistema anterior".encode(), response.data)

        state, items, delivery_movimientos, _ = self._delivery_state(orden_id)
        self.assertEqual(state, (None, None))
        self.assertIn(("Delivery 3", 3.0), items)
        self.assertEqual(delivery_movimientos, 0)

    def test_visual_delivery_totals_helper_excludes_legacy_from_restaurant_consumption(self):
        items = [
            ("Producto prueba", 20.0, 1, "", None),
            ("Delivery 3", 3.0, 2, "", "Delivery"),
        ]
        totales = web_app.calcular_totales_visuales_delivery(items, 0)
        self.assertEqual(totales["venta_restaurante_usd"], 20.0)
        self.assertEqual(totales["delivery_legacy_usd"], 3.0)
        self.assertEqual(totales["total_cliente_usd"], 23.0)

    def test_delivery_phase_two_does_not_alter_checkout_snapshot(self):
        repartidor_id = self._insert_repartidor("Sin Cobro Afectado", activo=1)
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._set_delivery(orden_id, 3, repartidor_id).status_code, 302)

        response = self._charge(orden_id, "usd", 20)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pago insuficiente", response.data)

    def test_delivery_phase_three_sale_without_delivery_still_works(self):
        orden_id = self._create_order(price=10.0)
        response = self._charge(orden_id, "usd", 10)
        self.assertEqual(response.status_code, 302)
        snapshot = self._financial_snapshot(orden_id)
        self.assertEqual(snapshot[8:11], (10.0, 0.0, 10.0))
        self.assertEqual(self._delivery_movements(orden_id), [])

    def test_delivery_paid_usd_requires_total_client_and_creates_single_cargo(self):
        orden_id, repartidor_id = self._create_order_with_delivery(price=20.0, delivery=3.0)

        insufficient = self._charge(orden_id, "usd", 20)
        self.assertEqual(insufficient.status_code, 200)
        self.assertIn(b"Pago insuficiente", insufficient.data)
        self.assertEqual(self._delivery_movements(orden_id), [])

        response = self._charge(orden_id, "usd", 23)
        self.assertEqual(response.status_code, 302)
        snapshot, pagos = self._snapshot(orden_id)
        financial = self._financial_snapshot(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 20.0, 0.0, 20.0, 4000.0))
        self.assertEqual(financial[8:12], (20.0, 3.0, 23.0, repartidor_id))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 23.0)])
        self.assertEqual(self._cuenta_por_orden(orden_id), None)
        self.assertEqual(self._delivery_movements(orden_id), [(repartidor_id, "cargo", 3.0, self._master_user_id(), "Cargo delivery generado al cerrar la orden")])

    def test_delivery_paid_bs_and_mixed_payments_validate_total_client(self):
        orden_bs, repartidor_bs = self._create_order_with_delivery(price=20.0, delivery=3.0)
        self.assertEqual(self._charge(orden_bs, "bs_pago_movil", 4600).status_code, 302)
        self.assertEqual(self._financial_snapshot(orden_bs)[8:11], (20.0, 3.0, 23.0))
        self.assertEqual(self._delivery_movements(orden_bs)[0][0:3], (repartidor_bs, "cargo", 3.0))

        orden_mixta, repartidor_mixto = self._create_order_with_delivery(price=20.0, delivery=3.0)
        self.assertEqual(self._charge(orden_mixta, "usd", 10, "bs_pago_movil", 2600).status_code, 302)
        _, pagos = self._snapshot(orden_mixta)
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 10.0), ("bs_pago_movil", 2600.0)])
        self.assertEqual(self._financial_snapshot(orden_mixta)[8:11], (20.0, 3.0, 23.0))
        self.assertEqual(self._delivery_movements(orden_mixta)[0][0:3], (repartidor_mixto, "cargo", 3.0))

    def test_delivery_discount_applies_only_to_restaurant_consumption(self):
        orden_id, repartidor_id = self._create_order_with_delivery(price=20.0, delivery=3.0)
        response = self._charge(orden_id, "usd", 21, descuento=400)
        self.assertEqual(response.status_code, 302)
        financial = self._financial_snapshot(orden_id)
        self.assertEqual(financial[4:8], (20.0, 400.0, 18.0, 3600.0))
        self.assertEqual(financial[8:11], (18.0, 3.0, 21.0))
        self.assertEqual(self._delivery_movements(orden_id)[0][0:3], (repartidor_id, "cargo", 3.0))

    def test_delivery_partial_creates_cxc_for_client_balance_and_delivery_cargo(self):
        cliente_id = self._create_client("Cliente Delivery Parcial")
        orden_id, repartidor_id = self._create_order_with_delivery(price=20.0, delivery=3.0)
        response = self._charge(orden_id, "usd", 15, modo_cobro="parcial", cliente_id=cliente_id)
        self.assertEqual(response.status_code, 302)
        financial = self._financial_snapshot(orden_id)
        self.assertIsNotNone(financial[2])
        self.assertEqual(financial[8:11], (20.0, 3.0, 23.0))
        self.assertEqual(self._cuenta_por_orden(orden_id)[1:4], (8.0, "pendiente", 8.0))
        cuenta_id = self._cuenta_por_orden(orden_id)[0]
        self.assertEqual(self._movimientos_cuenta(cuenta_id)[0][0:2], ("cargo", 8.0))
        self.assertEqual(self._delivery_movements(orden_id)[0][0:3], (repartidor_id, "cargo", 3.0))
        _, pagos = self._snapshot(orden_id)
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 15.0)])

    def test_delivery_partial_mixed_payment_uses_total_client_balance(self):
        cliente_id = self._create_client("Cliente Delivery Parcial Mixto")
        orden_id, _ = self._create_order_with_delivery(price=20.0, delivery=3.0)
        response = self._charge(
            orden_id,
            "usd",
            5,
            "bs_pago_movil",
            2000,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._cuenta_por_orden(orden_id)[1:3], (8.0, "pendiente"))

    def test_delivery_credit_creates_full_cxc_delivery_cargo_no_payments_and_inventory(self):
        cliente_id = self._create_client("Cliente Delivery Credito")
        orden_id, repartidor_id = self._create_order_with_delivery(price=20.0, delivery=3.0)
        response = self._charge(orden_id, "", 0, modo_cobro="credito", cliente_id=cliente_id)
        self.assertEqual(response.status_code, 302)
        financial = self._financial_snapshot(orden_id)
        self.assertIsNotNone(financial[1])
        self.assertIsNone(financial[2])
        self.assertEqual(financial[8:11], (20.0, 3.0, 23.0))
        self.assertEqual(financial[12], 1)
        self.assertEqual(self._snapshot(orden_id)[1], [])
        self.assertEqual(self._cuenta_por_orden(orden_id)[1:3], (23.0, "pendiente"))
        cuenta_id = self._cuenta_por_orden(orden_id)[0]
        self.assertEqual(self._movimientos_cuenta(cuenta_id)[0][0:2], ("cargo", 23.0))
        self.assertEqual(self._delivery_movements(orden_id)[0][0:3], (repartidor_id, "cargo", 3.0))

    def test_delivery_checkout_revalidates_repartidor_and_writes_nothing_on_failure(self):
        casos = (
            ("", b"Debes asignar un repartidor antes de cobrar esta orden."),
            (999999, b"repartidor activo"),
            (self._insert_repartidor("Inactivo Cobro", activo=0), b"repartidor activo"),
        )
        for repartidor_id, mensaje in casos:
            with self.subTest(repartidor_id=repartidor_id):
                orden_id = self._create_order(price=20.0)
                conn = self._conn()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE ordenes SET delivery_usd=3, delivery_repartidor_id=? WHERE id=?",
                    (repartidor_id or None, orden_id),
                )
                conn.commit()
                conn.close()
                response = self._charge(orden_id, "usd", 23)
                self.assertEqual(response.status_code, 400)
                self.assertIn(mensaje, response.data)
                self.assertEqual(self._financial_snapshot(orden_id)[0], "abierta")
                self.assertEqual(self._snapshot(orden_id)[1], [])
                self.assertEqual(self._cuenta_por_orden(orden_id), None)
                self.assertEqual(self._delivery_movements(orden_id), [])

    def test_delivery_atomicity_rolls_back_on_delivery_cargo_cxc_movement_and_inventory_failures(self):
        scenarios = (
            ("web_app.insertar_cargo_delivery", "pagado"),
            ("web_app.crear_cuenta_por_cobrar_inicial", "parcial"),
            ("web_app.insertar_movimiento_cxc_inicial", "parcial"),
            ("web_app.descontar_inventario_por_orden", "pagado"),
        )
        for patch_target, modo in scenarios:
            with self.subTest(patch_target=patch_target):
                cliente_id = self._create_client(f"Cliente Atomic {patch_target}")
                orden_id, _ = self._create_order_with_delivery(price=20.0, delivery=3.0)
                kwargs = {"modo_cobro": modo}
                if modo == "parcial":
                    kwargs["cliente_id"] = cliente_id
                    monto = 15
                else:
                    monto = 23
                with mock.patch(patch_target, side_effect=RuntimeError("fallo atomico")):
                    response = self._charge(orden_id, "usd", monto, **kwargs)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(self._financial_snapshot(orden_id)[0], "abierta")
                self.assertEqual(self._snapshot(orden_id)[1], [])
                self.assertEqual(self._cuenta_por_orden(orden_id), None)
                self.assertEqual(self._delivery_movements(orden_id), [])
                self.assertIn(self._inventory_discounted(orden_id), (None, 0))
                self._clear_operational_data()
                self._set_tasa(200)

    def test_delivery_recobro_blocks_when_delivery_movements_exist_and_preserves_state(self):
        orden_id, repartidor_id = self._create_order_with_delivery(price=20.0, delivery=3.0)
        self.assertEqual(self._charge(orden_id, "usd", 23).status_code, 302)
        snapshot_before = self._financial_snapshot(orden_id)
        movimientos_before = self._delivery_movements(orden_id)
        self.assertEqual(movimientos_before[0][0:3], (repartidor_id, "cargo", 3.0))

        self.assertEqual(self.client.post(f"/activar_edicion_emergencia/{orden_id}", data={"clave": "0102"}).status_code, 302)
        response = self._charge(orden_id, "usd", 23)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"movimientos de delivery", response.data)
        self.assertEqual(self._financial_snapshot(orden_id), snapshot_before)
        self.assertEqual(self._delivery_movements(orden_id), movimientos_before)

    def test_delivery_recobro_without_delivery_keeps_existing_cxc_protection(self):
        orden_id = self._create_order(price=10.0)
        self.assertEqual(self._charge(orden_id, "usd", 10).status_code, 302)
        self.assertEqual(self.client.post(f"/activar_edicion_emergencia/{orden_id}", data={"clave": "0102"}).status_code, 302)
        self.assertEqual(self._charge(orden_id, "usd", 10).status_code, 302)

        cliente_id = self._create_client("Cliente CxC Delivery Proteccion")
        orden_cxc, _ = self._create_order_with_delivery(price=20.0, delivery=3.0)
        self.assertEqual(self._charge(orden_cxc, "usd", 15, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
        self.assertEqual(self.client.post(f"/activar_edicion_emergencia/{orden_cxc}", data={"clave": "0102"}).status_code, 302)
        response = self._charge(orden_cxc, "usd", 23)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cuenta por cobrar asociada", response.data)

    def test_delivery_legacy_order_charges_with_legacy_behavior_without_backfill_or_delivery_cargo(self):
        delivery_id = self._delivery_product_id("Delivery 3")
        orden_id = self._create_order(price=20.0)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, '')",
            (orden_id, "Delivery 3", 3.0),
        )
        conn.commit()
        conn.close()

        page = self.client.get(f"/orden/{orden_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Delivery 3", page.data)
        self.assertEqual(self.client.get(f"/agregar/{orden_id}/{delivery_id}").status_code, 400)

        response = self._charge(orden_id, "usd", 23)
        self.assertEqual(response.status_code, 302)
        financial = self._financial_snapshot(orden_id)
        self.assertEqual(financial[4:8], (23.0, 0.0, 23.0, 4600.0))
        self.assertEqual(financial[8:11], (None, None, None))
        self.assertEqual(self._delivery_movements(orden_id), [])

    def _create_client(self, nombre="Ferreteria El Vecino"):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clientes (nombre, telefono, documento, notas, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (nombre, "0412-0000000", "J-00000000-0", "Cliente de prueba", "2026-08-21 10:00:00"),
        )
        cliente_id = web_app.obtener_ultimo_id(cursor, "clientes")
        conn.commit()
        conn.close()
        return cliente_id

    def _create_inactive_client(self, nombre="Cliente Inactivo"):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clientes (nombre, telefono, documento, notas, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (nombre, "0412-1111111", "V-00000000", "Cliente inactivo", "2026-08-21 10:00:00"),
        )
        cliente_id = web_app.obtener_ultimo_id(cursor, "clientes")
        conn.commit()
        conn.close()
        return cliente_id

    def _create_receivable(self, orden_id, cliente_id, monto=8.0, incluir_movimiento=False):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar (
                orden_id, cliente_id, cliente_nombre_snapshot, moneda_saldo,
                monto_original_deuda, saldo_pendiente, fecha_generacion,
                estado, usuario_id, observacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                orden_id,
                cliente_id,
                "Ferreteria El Vecino",
                "USD",
                monto,
                monto,
                "2026-08-21 10:05:00",
                "pendiente",
                self._master_user_id(),
                "Cuenta de prueba",
            ),
        )
        cuenta_id = web_app.obtener_ultimo_id(cursor, "cuentas_por_cobrar")
        if incluir_movimiento:
            cursor.execute(
                """
                INSERT INTO cuentas_por_cobrar_movimientos (
                    cuenta_id, tipo, monto_saldo, fecha, usuario_id, observacion
                )
                VALUES (?, 'cargo', ?, ?, ?, ?)
                """,
                (
                    cuenta_id,
                    monto,
                    "2026-08-21 10:05:00",
                    self._master_user_id(),
                    "Cargo inicial generado al cobrar la orden",
                ),
            )
        conn.commit()
        conn.close()
        return cuenta_id

    def _cuenta_por_orden(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, saldo_pendiente, estado, monto_original_deuda
            FROM cuentas_por_cobrar
            WHERE orden_id=?
            """,
            (orden_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def _movimientos_cuenta(self, cuenta_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT tipo, monto_saldo, moneda_pago, monto_pago, tasa_movimiento,
                   metodo_pago, referencia, usuario_id, observacion
            FROM cuentas_por_cobrar_movimientos
            WHERE cuenta_id=?
            ORDER BY id
            """,
            (cuenta_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _abonar(self, cuenta_id, metodo="usd", monto=1, referencia="abono-ref", observacion="Abono prueba"):
        return self.client.post(
            f"/cuentas_por_cobrar/{cuenta_id}/abono",
            data={
                "metodo_pago": metodo,
                "monto": str(monto),
                "referencia": referencia,
                "observacion": observacion,
            },
            follow_redirects=False,
        )

    def test_usd_full_payment_snapshot(self):
        orden_id = self._create_order()
        response = self._charge(orden_id, "usd", 10)
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[0], "cerrada")
        self.assertIsNotNone(snapshot[1])
        self.assertEqual(snapshot[2:], (200.0, 10.0, 0.0, 10.0, 2000.0, 0.0))
        self.assertEqual(len(pagos), 1)
        self.assertEqual(pagos[0][0], "usd")
        self.assertEqual(pagos[0][1], 10.0)
        self.assertEqual(pagos[0][3], snapshot[1])
        orden, movimientos = self._order_cxc_state(orden_id)
        self.assertIsNotNone(orden[0])
        self.assertEqual(orden[0], snapshot[1])
        self.assertEqual(movimientos, [])

    def test_bs_full_payment_snapshot(self):
        orden_id = self._create_order()
        response = self._charge(orden_id, "bs_pago_movil", 2000)
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 10.0, 0.0, 10.0, 2000.0))
        self.assertEqual(pagos[0][0], "bs_pago_movil")
        self.assertEqual(pagos[0][1], 2000.0)

    def test_mixed_payment_snapshot_and_two_payments(self):
        orden_id = self._create_order()
        response = self._charge(orden_id, "usd", 4, "bs_pago_movil", 1200)
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 10.0, 0.0, 10.0, 2000.0))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 4.0), ("bs_pago_movil", 1200.0)])
        self.assertEqual(pagos[0][3], snapshot[1])
        self.assertEqual(pagos[1][3], snapshot[1])

    def test_legacy_payload_without_modo_cobro_defaults_to_paid(self):
        orden_id = self._create_order(price=20.0)
        response = self._charge_legacy_payload(orden_id, "usd", 5, "bs_pago_movil", 3000)
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        orden, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "cerrada")
        self.assertEqual(snapshot[2:7], (200.0, 20.0, 0.0, 20.0, 4000.0))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 5.0), ("bs_pago_movil", 3000.0)])
        self.assertEqual(orden[0], snapshot[1])
        self.assertEqual(orden[1], snapshot[1])
        self.assertEqual(movimientos, [])

    def test_invalid_modo_cobro_returns_400_without_writes(self):
        orden_id = self._create_order(price=20.0)
        response = self._charge(orden_id, "usd", 20, modo_cobro="cualquier_cosa")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Modo de cobro invalido", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_checkout_page_renders_paid_mode_by_default(self):
        orden_id = self._create_order(price=20.0)
        response = self.client.get(f"/cobrar/{orden_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="modo_cobro"', response.data)
        self.assertIn(b'value="pagado"', response.data)
        self.assertIn(b'data-modo="pagado"', response.data)
        self.assertIn(b'data-modo="parcial"', response.data)
        self.assertIn(b'data-modo="credito"', response.data)
        self.assertIn(b"Cr&eacute;dito", response.data)
        self.assertIn(b"tel&eacute;fono", response.data)
        self.assertIn(b"cliente_id", response.data)
        self.assertIn(b"Cliente seleccionado", response.data)
        self.assertIn(b"clienteResultados", response.data)
        self.assertNotIn(b"Cr\xc3\x83", response.data)
        self.assertNotIn(b"\xc3\x83\xc2", response.data)

    def test_checkout_page_shows_active_clients_for_selection(self):
        orden_id = self._create_order(price=20.0)
        self._create_client("Ferreteria El Vecino")
        self._create_inactive_client("Cliente No Visible")

        response = self.client.get(f"/cobrar/{orden_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ferreteria El Vecino".encode(), response.data)
        self.assertIn(b"0412-0000000", response.data)
        self.assertIn(b"J-00000000-0", response.data)
        self.assertNotIn("Cliente No Visible".encode(), response.data)

    def test_api_clientes_searches_name_phone_and_document_active_only(self):
        self._create_client("Ferreteria El Vecino")
        self._create_inactive_client("Ferreteria Inactiva")

        for query in ("Ferre", "0412-0000000", "J-00000000-0"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/clientes?q={query}")
                self.assertEqual(response.status_code, 200)
                nombres = [cliente["nombre"] for cliente in response.get_json()["clientes"]]
                self.assertIn("Ferreteria El Vecino", nombres)
                self.assertNotIn("Ferreteria Inactiva", nombres)

    def test_partial_and_credit_require_real_selected_client_id(self):
        orden_id = self._create_order(price=20.0)
        response = self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id="")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cliente valido", response.data)

        orden_credito = self._create_order(price=20.0)
        response = self._charge(orden_credito, "", 0, modo_cobro="credito", cliente_id="")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cliente valido", response.data)

    def test_new_client_from_api_can_be_used_immediately_for_credit(self):
        cliente = self.client.post("/api/clientes", json={"nombre": "Cliente Uso Inmediato"}).get_json()["cliente"]
        orden_id = self._create_order(price=20.0)
        response = self._charge(orden_id, "", 0, modo_cobro="credito", cliente_id=cliente["id"])
        self.assertEqual(response.status_code, 302)
        cuenta = self._cuenta_por_orden(orden_id)
        self.assertEqual(cuenta[1:3], (20.0, "pendiente"))

    def test_api_clientes_lists_active_clients(self):
        self._create_client("Cliente Activo API")
        self._create_inactive_client("Cliente Inactivo API")

        response = self.client.get("/api/clientes")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        nombres = [cliente["nombre"] for cliente in data["clientes"]]
        self.assertIn("Cliente Activo API", nombres)
        self.assertNotIn("Cliente Inactivo API", nombres)

    def test_api_clientes_creates_valid_client(self):
        response = self.client.post(
            "/api/clientes",
            json={
                "nombre": "Cliente Nuevo Cobro",
                "telefono": "0412-2222222",
                "documento": "J-22222222-2",
                "notas": "Creado desde cobro",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["cliente"]["nombre"], "Cliente Nuevo Cobro")

        listado = self.client.get("/api/clientes?q=nuevo").get_json()
        self.assertEqual([c["nombre"] for c in listado["clientes"]], ["Cliente Nuevo Cobro"])

    def test_api_clientes_rejects_empty_name(self):
        response = self.client.post("/api/clientes", json={"nombre": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    def test_inactive_client_cannot_be_used_for_new_receivable(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_inactive_client("Cliente Inactivo CxC")

        response = self._charge(
            orden_id,
            "usd",
            12,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cliente valido", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])

    def test_partial_usd_payment_creates_receivable_for_remaining_balance(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Credito")
        response = self._charge(
            orden_id,
            "usd",
            12,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        orden, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "cerrada")
        self.assertEqual(snapshot[2:7], (200.0, 20.0, 0.0, 20.0, 4000.0))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 12.0)])
        self.assertEqual(orden[0], snapshot[1])
        self.assertEqual(orden[1], snapshot[1])
        self.assertEqual(orden[2], cliente_id)
        self.assertEqual(orden[3], "Cliente Credito")
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0][1:9], (cliente_id, "Cliente Credito", "USD", 8.0, 8.0, "pendiente", "cargo", 8.0))
        self.assertEqual(movimientos[0][9], snapshot[1])

    def test_partial_bs_payment_creates_receivable_using_checkout_rate(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Bs")
        response = self._charge(
            orden_id,
            "bs_pago_movil",
            2400,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 302)

        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(movimientos[0][4], 8.0)
        self.assertEqual(movimientos[0][5], 8.0)
        self.assertEqual(movimientos[0][8], 8.0)

    def test_partial_mixed_payment_creates_receivable_from_unpaid_usd_balance(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Mixto")
        response = self._charge(
            orden_id,
            "usd",
            5,
            "bs_pago_movil",
            1400,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 5.0), ("bs_pago_movil", 1400.0)])
        self.assertEqual(pagos[0][3], snapshot[1])
        self.assertEqual(pagos[1][3], snapshot[1])
        self.assertEqual(movimientos[0][4], 8.0)
        self.assertEqual(movimientos[0][8], 8.0)

    def test_full_credit_creates_receivable_without_payments_or_fecha_cobro(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Full Credito")
        response = self._charge(
            orden_id,
            "",
            0,
            modo_cobro="credito",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 302)

        snapshot, pagos = self._snapshot(orden_id)
        orden, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "cerrada")
        self.assertIsNone(snapshot[1])
        self.assertEqual(snapshot[2:7], (200.0, 20.0, 0.0, 20.0, 4000.0))
        self.assertEqual(pagos, [])
        self.assertIsNotNone(orden[0])
        self.assertIsNone(orden[1])
        self.assertEqual(movimientos[0][4], 20.0)
        self.assertEqual(movimientos[0][8], 20.0)
        self.assertEqual(self._inventory_discounted(orden_id), 1)

    def test_partial_or_credit_requires_existing_client(self):
        for modo in ("parcial", "credito"):
            with self.subTest(modo=modo):
                self._clear_operational_data()
                self._set_tasa(200)
                orden_id = self._create_order(price=20.0)
                response = self._charge(
                    orden_id,
                    "usd" if modo == "parcial" else "",
                    5 if modo == "parcial" else 0,
                    modo_cobro=modo,
                    cliente_id=999999,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"cliente valido", response.data)

                snapshot, pagos = self._snapshot(orden_id)
                _, movimientos = self._order_cxc_state(orden_id)
                self.assertEqual(snapshot[0], "abierta")
                self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
                self.assertEqual(pagos, [])
                self.assertEqual(movimientos, [])
                self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_paid_mode_still_rejects_insufficient_payment_without_receivable(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Sin Credito")
        response = self._charge(orden_id, "usd", 5, cliente_id=cliente_id)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pago insuficiente", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])

    def test_partial_with_zero_payments_is_rejected_without_debt(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Parcial Cero")
        response = self._charge(
            orden_id,
            "",
            0,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cobro parcial requiere al menos un pago", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_partial_that_pays_full_total_is_rejected_without_debt(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Parcial Completo")
        response = self._charge(
            orden_id,
            "usd",
            20,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Usa modo pagado", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_credit_with_positive_payment_is_rejected_without_writes(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Credito Con Pago")
        response = self._charge(
            orden_id,
            "usd",
            5,
            modo_cobro="credito",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"credito completo no debe registrar pagos", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_discount_snapshot_uses_current_bs_discount_semantics(self):
        orden_id = self._create_order()
        response = self._charge(orden_id, "bs_pago_movil", 1800, descuento=200)
        self.assertEqual(response.status_code, 302)

        snapshot, _ = self._snapshot(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 10.0, 200.0, 9.0, 1800.0))
        self.assertEqual(snapshot[7], 200.0)

    def test_later_rate_change_does_not_change_previous_snapshot(self):
        first_id = self._create_order()
        self.assertEqual(self._charge(first_id, "usd", 10).status_code, 302)

        self.client.post("/cambiar_tasa", data={"tasa": "250"})
        first_snapshot, _ = self._snapshot(first_id)
        self.assertEqual(first_snapshot[2:7], (200.0, 10.0, 0.0, 10.0, 2000.0))

        second_id = self._create_order()
        self.assertEqual(self._charge(second_id, "usd", 10).status_code, 302)
        second_snapshot, _ = self._snapshot(second_id)
        self.assertEqual(second_snapshot[2:7], (250.0, 10.0, 0.0, 10.0, 2500.0))

    def test_invalid_simple_payment_does_not_close_or_snapshot(self):
        orden_id = self._create_order()
        response = self._charge(orden_id, "bs_pago_movil", 1000)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pago insuficiente", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])

    def test_invalid_mixed_payment_does_not_close_or_snapshot(self):
        orden_id = self._create_order()
        response = self._charge(orden_id, "usd", 4, "bs_pago_movil", 100)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pago insuficiente", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])

    def test_invalid_rate_does_not_close_or_snapshot(self):
        for tasa_invalida in (0, -1, None):
            with self.subTest(tasa=tasa_invalida):
                self._clear_operational_data()
                self._set_tasa(tasa_invalida)
                orden_id = self._create_order()

                response = self._charge(orden_id, "bs_pago_movil", 2000)
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"Tasa de cobro invalida", response.data)

                snapshot, pagos = self._snapshot(orden_id)
                self.assertEqual(snapshot[0], "abierta")
                self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
                self.assertEqual(pagos, [])

    def test_invalid_rate_does_not_allow_full_credit_snapshot(self):
        for tasa_invalida in (0, -1, None):
            with self.subTest(tasa=tasa_invalida):
                self._clear_operational_data()
                self._set_tasa(tasa_invalida)
                orden_id = self._create_order(price=20.0)
                cliente_id = self._create_client("Cliente Tasa Invalida")

                response = self._charge(
                    orden_id,
                    "",
                    0,
                    modo_cobro="credito",
                    cliente_id=cliente_id,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"Tasa de cobro invalida", response.data)

                snapshot, pagos = self._snapshot(orden_id)
                _, movimientos = self._order_cxc_state(orden_id)
                self.assertEqual(snapshot[0], "abierta")
                self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
                self.assertEqual(pagos, [])
                self.assertEqual(movimientos, [])

    def test_schema_initialization_is_idempotent_and_preserves_snapshot_columns(self):
        orden_id = self._create_order()
        web_app.init_db()
        web_app.init_db()

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(ordenes)")
        columns = [row[1] for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM ordenes WHERE id=?", (orden_id,))
        order_count = cursor.fetchone()[0]
        conn.close()

        for column in (
            "fecha_cobro",
            "tasa_cobro",
            "subtotal_usd",
            "descuento_bs_snapshot",
            "total_usd",
            "total_bs",
        ):
            self.assertEqual(columns.count(column), 1)
        self.assertEqual(order_count, 1)

    def test_accounts_receivable_tables_and_order_columns_exist(self):
        expected = {
            "clientes": {
                "id",
                "nombre",
                "telefono",
                "documento",
                "notas",
                "activo",
                "fecha_creacion",
            },
            "cuentas_por_cobrar": {
                "id",
                "orden_id",
                "cliente_id",
                "cliente_nombre_snapshot",
                "moneda_saldo",
                "monto_original_deuda",
                "saldo_pendiente",
                "fecha_generacion",
                "estado",
                "usuario_id",
                "observacion",
            },
            "cuentas_por_cobrar_movimientos": {
                "id",
                "cuenta_id",
                "tipo",
                "monto_saldo",
                "moneda_pago",
                "monto_pago",
                "tasa_movimiento",
                "metodo_pago",
                "referencia",
                "fecha",
                "usuario_id",
                "observacion",
                "movimiento_revertido_id",
                "referencia_externa_tipo",
                "referencia_externa_id",
            },
        }

        for table, columns in expected.items():
            self.assertTrue(columns.issubset(set(self._columns(table))))

        orden_columns = self._columns("ordenes")
        self.assertIn("cliente_id", orden_columns)
        self.assertIn("fecha_venta", orden_columns)
        self.assertEqual(self._columns("cuentas_por_cobrar")["cliente_nombre_snapshot"][3], 1)

    def test_accounts_receivable_schema_initialization_is_idempotent_and_preserves_data(self):
        orden_id = self._create_order()
        cliente_id = self._create_client()
        cuenta_id = self._create_receivable(orden_id, cliente_id)

        web_app.init_db()
        web_app.init_db()

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM clientes WHERE id=?", (cliente_id,))
        cliente = cursor.fetchone()
        cursor.execute("SELECT saldo_pendiente FROM cuentas_por_cobrar WHERE id=?", (cuenta_id,))
        cuenta = cursor.fetchone()
        orden_columns = self._columns("ordenes")
        conn.close()

        self.assertEqual(cliente[0], "Ferreteria El Vecino")
        self.assertEqual(cuenta[0], 8.0)
        self.assertEqual(list(orden_columns).count("cliente_id"), 1)
        self.assertEqual(list(orden_columns).count("fecha_venta"), 1)

    def test_can_create_client_receivable_and_movements(self):
        orden_id = self._create_order()
        cliente_id = self._create_client()
        cuenta_id = self._create_receivable(orden_id, cliente_id)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar_movimientos (
                cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
                tasa_movimiento, metodo_pago, referencia, fecha,
                usuario_id, observacion, movimiento_revertido_id,
                referencia_externa_tipo, referencia_externa_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cuenta_id,
                "cargo",
                8.0,
                "USD",
                8.0,
                None,
                None,
                "CARGO-1",
                "2026-08-21 10:05:00",
                self._master_user_id(),
                "Cargo inicial de prueba",
                None,
                None,
                None,
            ),
        )
        cargo_id = web_app.obtener_ultimo_id(cursor, "cuentas_por_cobrar_movimientos")
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar_movimientos (
                cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
                tasa_movimiento, metodo_pago, referencia, fecha,
                usuario_id, observacion, movimiento_revertido_id,
                referencia_externa_tipo, referencia_externa_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cuenta_id,
                "abono",
                -3.0,
                "USD",
                3.0,
                None,
                "usd",
                "ABONO-1",
                "2026-08-22 12:00:00",
                self._master_user_id(),
                "Abono de prueba",
                None,
                None,
                None,
            ),
        )
        abono_id = web_app.obtener_ultimo_id(cursor, "cuentas_por_cobrar_movimientos")
        cursor.execute(
            "SELECT SUM(monto_saldo) FROM cuentas_por_cobrar_movimientos WHERE cuenta_id=?",
            (cuenta_id,),
        )
        saldo_por_movimientos_tras_abono = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar_movimientos (
                cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
                tasa_movimiento, metodo_pago, referencia, fecha,
                usuario_id, observacion, movimiento_revertido_id,
                referencia_externa_tipo, referencia_externa_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cuenta_id,
                "reverso",
                3.0,
                None,
                None,
                None,
                None,
                "REV-1",
                "2026-08-22 12:05:00",
                self._master_user_id(),
                "Reverso de prueba",
                abono_id,
                None,
                None,
            ),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT c.nombre, cx.moneda_saldo, cx.saldo_pendiente,
                   SUM(m.monto_saldo), MAX(m.movimiento_revertido_id)
            FROM cuentas_por_cobrar cx
            JOIN clientes c ON c.id = cx.cliente_id
            JOIN cuentas_por_cobrar_movimientos m ON m.cuenta_id = cx.id
            WHERE cx.id=?
            GROUP BY c.nombre, cx.moneda_saldo, cx.saldo_pendiente
            """,
            (cuenta_id,),
        )
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(cargo_id)
        self.assertEqual(saldo_por_movimientos_tras_abono, 5.0)
        self.assertEqual(row, ("Ferreteria El Vecino", "USD", 8.0, 8.0, abono_id))

    def test_receivable_order_id_is_unique(self):
        orden_id = self._create_order()
        cliente_id = self._create_client()
        self._create_receivable(orden_id, cliente_id)

        conn = self._conn()
        cursor = conn.cursor()
        with self.assertRaises(Exception):
            cursor.execute(
                """
                INSERT INTO cuentas_por_cobrar (
                    orden_id, cliente_id, moneda_saldo, monto_original_deuda,
                    saldo_pendiente, fecha_generacion, estado
                )
                VALUES (?, ?, 'USD', 1, 1, '2026-08-21 11:00:00', 'pendiente')
                """,
                (orden_id, cliente_id),
            )
        conn.rollback()
        conn.close()

    def test_legacy_order_has_nullable_client_id_and_fecha_venta(self):
        orden_id = self._create_order()

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT cliente_id, fecha_venta FROM ordenes WHERE id=?", (orden_id,))
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row, (None, None))

    def test_recharge_updates_snapshot_and_replaces_payments(self):
        orden_id = self._create_order()
        self.assertEqual(self._charge(orden_id, "usd", 10).status_code, 302)

        with self.client.session_transaction() as sess:
            sess["emergencias_activas"] = [str(orden_id)]

        self.assertEqual(self._charge(orden_id, "bs_pago_movil", 1800, descuento=200).status_code, 302)
        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 10.0, 200.0, 9.0, 1800.0))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("bs_pago_movil", 1800.0)])

    def test_emergency_recharge_blocks_order_with_initial_receivable(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Recobro")
        self.assertEqual(
            self._charge(
                orden_id,
                "usd",
                12,
                modo_cobro="parcial",
                cliente_id=cliente_id,
            ).status_code,
            302,
        )
        snapshot_antes, pagos_antes = self._snapshot(orden_id)
        _, movimientos_antes = self._order_cxc_state(orden_id)

        with self.client.session_transaction() as sess:
            sess["emergencias_activas"] = [str(orden_id)]

        response = self._charge(
            orden_id,
            "usd",
            10,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cuenta por cobrar asociada", response.data)

        snapshot_despues, pagos_despues = self._snapshot(orden_id)
        _, movimientos_despues = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot_despues, snapshot_antes)
        self.assertEqual(pagos_despues, pagos_antes)
        self.assertEqual(movimientos_despues, movimientos_antes)

    def test_emergency_recharge_blocks_receivable_with_later_movements(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Con Abono")
        self.assertEqual(
            self._charge(
                orden_id,
                "usd",
                12,
                modo_cobro="parcial",
                cliente_id=cliente_id,
            ).status_code,
            302,
        )
        _, movimientos_antes = self._order_cxc_state(orden_id)
        cuenta_id = movimientos_antes[0][0]

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar_movimientos (
                cuenta_id, tipo, monto_saldo, moneda_pago, monto_pago,
                tasa_movimiento, metodo_pago, referencia, fecha,
                usuario_id, observacion, movimiento_revertido_id,
                referencia_externa_tipo, referencia_externa_id
            )
            VALUES (?, 'abono', -3, 'USD', 3, NULL, 'usd', 'ABONO-TEST',
                    '2026-08-21 13:00:00', ?, 'Abono posterior', NULL, NULL, NULL)
            """,
            (cuenta_id, self._master_user_id()),
        )
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["emergencias_activas"] = [str(orden_id)]

        response = self._charge(
            orden_id,
            "usd",
            10,
            modo_cobro="parcial",
            cliente_id=cliente_id,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cuenta por cobrar asociada", response.data)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos_despues = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 20.0, 0.0, 20.0, 4000.0))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("usd", 12.0)])
        self.assertEqual([(m[7], m[8]) for m in movimientos_despues], [("cargo", 8.0), ("abono", -3.0)])

    def test_receivable_account_creation_failure_rolls_back_checkout(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Rollback Cuenta")
        with mock.patch(
            "web_app.crear_cuenta_por_cobrar_inicial",
            side_effect=RuntimeError("fallo cuenta cxc"),
        ):
            response = self._charge(
                orden_id,
                "usd",
                12,
                modo_cobro="parcial",
                cliente_id=cliente_id,
            )
        self.assertEqual(response.status_code, 500)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_initial_receivable_movement_failure_rolls_back_checkout(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Rollback")
        with mock.patch(
            "web_app.insertar_movimiento_cxc_inicial",
            side_effect=RuntimeError("fallo movimiento cxc"),
        ):
            response = self._charge(
                orden_id,
                "usd",
                12,
                modo_cobro="parcial",
                cliente_id=cliente_id,
            )
        self.assertEqual(response.status_code, 500)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_inventory_failure_rolls_back_payments_snapshot_and_receivable(self):
        orden_id = self._create_order(price=20.0)
        cliente_id = self._create_client("Cliente Inventario")
        with mock.patch(
            "web_app.descontar_inventario_por_orden",
            side_effect=RuntimeError("fallo inventario"),
        ):
            response = self._charge(
                orden_id,
                "usd",
                12,
                modo_cobro="parcial",
                cliente_id=cliente_id,
            )
        self.assertEqual(response.status_code, 500)

        snapshot, pagos = self._snapshot(orden_id)
        _, movimientos = self._order_cxc_state(orden_id)
        self.assertEqual(snapshot[0], "abierta")
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))
        self.assertEqual(pagos, [])
        self.assertEqual(movimientos, [])
        self.assertIn(self._inventory_discounted(orden_id), (None, 0))

    def test_daily_close_preserves_snapshot(self):
        orden_id = self._create_order()
        self.assertEqual(self._charge(orden_id, "usd", 10).status_code, 302)
        before, _ = self._snapshot(orden_id)

        response = self.client.get("/cerrar_jornada", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        after, _ = self._snapshot(orden_id)
        self.assertEqual(after[1:7], before[1:7])

    def test_legacy_closed_order_without_snapshot_is_readable(self):
        orden_id = self._create_order(estado="cerrada")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE ordenes
            SET fecha_cobro=NULL,
                tasa_cobro=NULL,
                subtotal_usd=NULL,
                descuento_bs_snapshot=NULL,
                total_usd=NULL,
                total_bs=NULL
            WHERE id=?
            """,
            (orden_id,),
        )
        conn.commit()
        conn.close()

        response = self.client.get("/reportes?desde=2026-08-20&hasta=2026-08-20")
        self.assertEqual(response.status_code, 200)
        snapshot, _ = self._snapshot(orden_id)
        self.assertEqual(snapshot[1:7], (None, None, None, None, None, None))

    def test_admin_clients_list_shows_balances_and_search_filters(self):
        cliente_con_saldo = self._create_client("Ferreteria El Vecino")
        self._create_client("Cliente Sin Saldo")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id=cliente_con_saldo).status_code,
            302,
        )

        response = self.client.get("/cuentas_por_cobrar/clientes")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ferreteria El Vecino", response.data)
        self.assertIn(b"$ 8.00", response.data)
        self.assertIn(b"Cliente Sin Saldo", response.data)
        self.assertIn(b"Cartera de clientes", response.data)

        response = self.client.get("/cuentas_por_cobrar/clientes?q=vecino")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ferreteria El Vecino", response.data)
        self.assertNotIn(b"Cliente Sin Saldo", response.data)

        response = self.client.get("/cuentas_por_cobrar/clientes?filtro=con_saldo")
        self.assertIn(b"Ferreteria El Vecino", response.data)
        self.assertNotIn(b"Cliente Sin Saldo", response.data)

        response = self.client.get("/cuentas_por_cobrar/clientes?filtro=sin_saldo")
        self.assertNotIn(b"Ferreteria El Vecino", response.data)
        self.assertIn(b"Cliente Sin Saldo", response.data)

    def test_admin_client_create_rejects_empty_and_creates_valid_client(self):
        response = self.client.post("/cuentas_por_cobrar/clientes/nuevo", data={"nombre": "   "})
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/cuentas_por_cobrar/clientes/nuevo",
            data={
                "nombre": "Cliente Admin",
                "telefono": "0414-3333333",
                "documento": "V-33333333",
                "notas": "Alta administrativa",
                "activo": "1",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/cuentas_por_cobrar/clientes?q=admin")
        self.assertIn(b"Cliente Admin", response.data)
        self.assertIn(b"0414-3333333", response.data)

    def test_admin_clients_legacy_route_redirects_to_unified_section(self):
        response = self.client.get("/clientes", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/cuentas_por_cobrar/clientes")

    def test_admin_main_navigation_has_only_unified_cxc_entry(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/cuentas_por_cobrar"', response.data)
        self.assertIn("💰 Cuentas por cobrar".encode(), response.data)
        self.assertNotIn(b'href="/clientes"', response.data)

    def test_admin_client_edit_does_not_change_receivable_snapshot(self):
        cliente_id = self._create_client("Nombre Historico")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )

        response = self.client.post(
            f"/cuentas_por_cobrar/clientes/{cliente_id}/editar",
            data={
                "nombre": "Nombre Actualizado",
                "telefono": "0414-4444444",
                "documento": "V-44444444",
                "notas": "Editado",
                "activo": "1",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cliente_nombre_snapshot FROM cuentas_por_cobrar WHERE orden_id=?",
            (orden_id,),
        )
        snapshot = cursor.fetchone()[0]
        cursor.execute("SELECT nombre FROM clientes WHERE id=?", (cliente_id,))
        nombre_actual = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(snapshot, "Nombre Historico")
        self.assertEqual(nombre_actual, "Nombre Actualizado")

    def test_admin_client_deactivate_preserves_history_and_hides_from_checkout_selection(self):
        cliente_id = self._create_client("Cliente Desactivable")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )

        response = self.client.post(f"/cuentas_por_cobrar/clientes/{cliente_id}/activar", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        detalle = self.client.get(f"/cuentas_por_cobrar/clientes/{cliente_id}")
        self.assertEqual(detalle.status_code, 200)
        self.assertIn(b"Inactivo", detalle.data)
        self.assertIn(b"$ 8.00", detalle.data)

        nueva_orden = self._create_order(price=10.0)
        checkout = self.client.get(f"/cobrar/{nueva_orden}")
        self.assertEqual(checkout.status_code, 200)
        self.assertNotIn(b"Cliente Desactivable", checkout.data)

    def test_admin_client_detail_lists_associated_receivables(self):
        cliente_id = self._create_client("Cliente Detalle")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )

        response = self.client.get(f"/cuentas_por_cobrar/clientes/{cliente_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cliente Detalle", response.data)
        self.assertIn(b"Cuentas por cobrar", response.data)
        self.assertIn(b"$ 8.00", response.data)
        self.assertIn(b"#1", response.data)

    def test_admin_cxc_empty_list_is_readable(self):
        response = self.client.get("/cuentas_por_cobrar")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Resumen", response.data)
        self.assertIn(b"Cuentas", response.data)
        self.assertIn(b"Cartera de clientes", response.data)
        self.assertIn(b"$ 0.00", response.data)
        self.assertIn(b"No hay cuentas por cobrar", response.data)

        response = self.client.get("/cuentas_por_cobrar/cuentas")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No hay cuentas por cobrar", response.data)

    def test_admin_cxc_list_filters_and_searches_accounts(self):
        cliente_id = self._create_client("Cliente Pendiente")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )

        cliente_pagado = self._create_client("Cliente Pagado")
        orden_pagada = self._create_order(price=15.0)
        cuenta_pagada = self._create_receivable(orden_pagada, cliente_pagado, monto=0.0)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cuentas_por_cobrar SET estado='pagada', monto_original_deuda=15, saldo_pendiente=0 WHERE id=?",
            (cuenta_pagada,),
        )
        conn.commit()
        conn.close()

        response = self.client.get("/cuentas_por_cobrar")
        self.assertIn(b"Cliente Pendiente", response.data)
        self.assertNotIn(f'href="/cuentas_por_cobrar/clientes/{cliente_pagado}"'.encode(), response.data)

        response = self.client.get("/cuentas_por_cobrar?estado=pagada")
        self.assertIn(b"Cliente Pagado", response.data)
        self.assertNotIn(f'href="/cuentas_por_cobrar/clientes/{cliente_id}"'.encode(), response.data)

        response = self.client.get("/cuentas_por_cobrar?estado=todas&q=pendiente")
        self.assertIn(b"Cliente Pendiente", response.data)
        self.assertNotIn(f'href="/cuentas_por_cobrar/clientes/{cliente_pagado}"'.encode(), response.data)

    def test_admin_cxc_detail_shows_sale_debt_paid_initial_and_historical_rate(self):
        cliente_id = self._create_client("Cliente Tasa Historica")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 4, "bs_pago_movil", 1600, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )
        self._set_tasa(999)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cuentas_por_cobrar WHERE orden_id=?", (orden_id,))
        cuenta_id = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT saldo_pendiente,
                   (SELECT COALESCE(SUM(monto_saldo), 0)
                    FROM cuentas_por_cobrar_movimientos
                    WHERE cuenta_id=cuentas_por_cobrar.id)
            FROM cuentas_por_cobrar
            WHERE id=?
            """,
            (cuenta_id,),
        )
        saldo, suma_movimientos = cursor.fetchone()
        conn.close()
        self.assertEqual(round(saldo, 2), round(suma_movimientos, 2))

        response = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Valor de venta", response.data)
        self.assertIn(b"$ 20.00", response.data)
        self.assertIn(b"Cobrado al cerrar", response.data)
        self.assertIn(b"$ 12.00", response.data)
        self.assertIn(b"Deuda generada", response.data)
        self.assertIn(b"$ 8.00", response.data)
        self.assertIn(b"Tasa historica", response.data)
        self.assertIn(b"200.0", response.data)
        self.assertIn(b"Cliente Tasa Historica", response.data)
        self.assertIn(b"cargo", response.data)
        self.assertIn(b"Cargo inicial generado", response.data)
        self.assertIn(f"/orden/{orden_id}".encode(), response.data)

    def test_admin_cxc_movements_are_chronological_and_show_initial_charge(self):
        cliente_id = self._create_client("Cliente Movimientos")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(
            self._charge(orden_id, "usd", 12, modo_cobro="parcial", cliente_id=cliente_id).status_code,
            302,
        )
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cuentas_por_cobrar WHERE orden_id=?", (orden_id,))
        cuenta_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar_movimientos (
                cuenta_id, tipo, monto_saldo, fecha, usuario_id, observacion
            )
            VALUES (?, 'abono', -2, '2099-08-23 09:00:00', ?, 'Abono futuro de prueba')
            """,
            (cuenta_id, self._master_user_id()),
        )
        conn.commit()
        conn.close()

        response = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}")
        self.assertEqual(response.status_code, 200)
        data = response.data.decode()
        self.assertLess(data.index("Cargo inicial generado"), data.index("Abono futuro de prueba"))

    def test_admin_cxc_legacy_order_without_snapshot_does_not_break_lists(self):
        cliente_id = self._create_client("Cliente Legacy")
        orden_id = self._create_order(price=10.0, estado="cerrada")
        cuenta_id = self._create_receivable(orden_id, cliente_id, monto=10.0)

        response = self.client.get("/cuentas_por_cobrar?estado=todas&q=legacy")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cliente Legacy", response.data)

        response = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Valor de venta", response.data)

    def test_cxc_usd_partial_abono_reduces_balance_and_keeps_pending(self):
        cliente_id = self._create_client("Cliente Abono USD")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
        cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)

        response = self._abonar(cuenta_id, "usd", 4)
        self.assertEqual(response.status_code, 302)
        cuenta = self._cuenta_por_orden(orden_id)
        movimientos = self._movimientos_cuenta(cuenta_id)
        self.assertEqual(cuenta[1:3], (6.0, "pendiente"))
        self.assertEqual(movimientos[-1][0:6], ("abono", -4.0, "USD", 4.0, None, "usd"))

    def test_cxc_usd_full_abono_marks_paid(self):
        cliente_id = self._create_client("Cliente Pago Total USD")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
        cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)

        response = self._abonar(cuenta_id, "usd", 10)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._cuenta_por_orden(orden_id)[1:3], (0.0, "pagada"))

        detalle = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}")
        self.assertIn(b"Cuenta pagada", detalle.data)
        self.assertNotIn(b"Registrar abono</a>", detalle.data)

    def test_cxc_bs_abono_uses_current_rate_not_sale_rate(self):
        cliente_id = self._create_client("Cliente Abono Bs")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
        cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)
        self._set_tasa(250)

        response = self._abonar(cuenta_id, "bs_pago_movil", 1000, referencia="pm-1")
        self.assertEqual(response.status_code, 302)
        cuenta = self._cuenta_por_orden(orden_id)
        movimiento = self._movimientos_cuenta(cuenta_id)[-1]
        self.assertEqual(cuenta[1:3], (6.0, "pendiente"))
        self.assertEqual(movimiento[0:7], ("abono", -4.0, "BS", 1000.0, 250.0, "bs_pago_movil", "pm-1"))

    def test_cxc_bs_full_payment_marks_paid(self):
        cliente_id = self._create_client("Cliente Pago Total Bs")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
        cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)
        self._set_tasa(250)

        response = self._abonar(cuenta_id, "punto_venta", 2500)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._cuenta_por_orden(orden_id)[1:3], (0.0, "pagada"))

    def test_cxc_abono_rejects_overpayment_zero_negative_and_invalid_rate_without_writes(self):
        for monto, tasa, metodo, mensaje in (
            (11, 200, "usd", b"supera el saldo"),
            (0, 200, "usd", b"mayor a 0"),
            (-1, 200, "usd", b"mayor a 0"),
            (1000, 0, "bs_pago_movil", b"tasa de cambio valida"),
        ):
            with self.subTest(monto=monto, tasa=tasa, metodo=metodo):
                cliente_id = self._create_client(f"Cliente Val {monto} {metodo}")
                orden_id = self._create_order(price=20.0)
                self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
                cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)
                self._set_tasa(tasa)
                before = (self._cuenta_por_orden(orden_id), self._movimientos_cuenta(cuenta_id))

                response = self._abonar(cuenta_id, metodo, monto)
                self.assertEqual(response.status_code, 400)
                self.assertIn(mensaje, response.data)
                self.assertEqual(self._cuenta_por_orden(orden_id), before[0])
                self.assertEqual(self._movimientos_cuenta(cuenta_id), before[1])
                self._clear_operational_data()
                self._set_tasa(200)

    def test_cxc_abono_rejects_paid_annulled_and_inconsistent_accounts(self):
        for estado in ("pagada", "anulada"):
            with self.subTest(estado=estado):
                cliente_id = self._create_client(f"Cliente {estado}")
                orden_id = self._create_order(price=20.0)
                cuenta_id = self._create_receivable(orden_id, cliente_id, monto=10.0, incluir_movimiento=True)
                conn = self._conn()
                cursor = conn.cursor()
                cursor.execute("UPDATE cuentas_por_cobrar SET estado=? WHERE id=?", (estado, cuenta_id))
                conn.commit()
                conn.close()
                response = self._abonar(cuenta_id, "usd", 1)
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"cuentas pendientes", response.data)
                self._clear_operational_data()
                self._set_tasa(200)

        cliente_id = self._create_client("Cliente Inconsistente")
        orden_id = self._create_order(price=20.0)
        cuenta_id = self._create_receivable(orden_id, cliente_id, monto=10.0)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE cuentas_por_cobrar SET saldo_pendiente=9 WHERE id=?", (cuenta_id,))
        conn.commit()
        conn.close()
        response = self._abonar(cuenta_id, "usd", 1)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"inconsistencia", response.data)

    def test_cxc_abono_rolls_back_on_movement_or_balance_failure(self):
        for patch_target in ("web_app.insertar_movimiento_abono_cxc", "web_app.actualizar_saldo_cxc"):
            with self.subTest(patch_target=patch_target):
                cliente_id = self._create_client(f"Cliente Rollback {patch_target}")
                orden_id = self._create_order(price=20.0)
                self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
                cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)
                before = (self._cuenta_por_orden(orden_id), self._movimientos_cuenta(cuenta_id))
                with mock.patch(patch_target, side_effect=RuntimeError("fallo abono")):
                    response = self._abonar(cuenta_id, "usd", 4)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(self._cuenta_por_orden(orden_id), before[0])
                self.assertEqual(self._movimientos_cuenta(cuenta_id), before[1])
                self._clear_operational_data()
                self._set_tasa(200)

    def test_cxc_abono_preserves_consistency_user_client_summary_and_original_sale(self):
        cliente_id = self._create_client("Cliente Consistente")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._charge(orden_id, "", 0, modo_cobro="credito", cliente_id=cliente_id).status_code, 302)
        snapshot_before, pagos_before = self._snapshot(orden_id)
        cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)

        self.assertEqual(self._abonar(cuenta_id, "usd", 7).status_code, 302)
        self.assertEqual(self._abonar(cuenta_id, "usd", 13).status_code, 302)
        cuenta = self._cuenta_por_orden(orden_id)
        movimientos = self._movimientos_cuenta(cuenta_id)
        suma = round(sum(m[1] for m in movimientos), 2)
        self.assertEqual(cuenta[1:3], (0.0, "pagada"))
        self.assertEqual(suma, 0.0)
        self.assertEqual(movimientos[-1][7], self._master_user_id())
        self.assertEqual(self._snapshot(orden_id), (snapshot_before, pagos_before))

        cliente_detalle = self.client.get(f"/cuentas_por_cobrar/clientes/{cliente_id}")
        self.assertIn(b"Cuentas pagadas", cliente_detalle.data)
        self.assertIn(b"$ 0.00", cliente_detalle.data)
        resumen = self.client.get("/cuentas_por_cobrar")
        self.assertIn(b"Cuentas pagadas", resumen.data)

    def test_cxc_abono_detail_shows_actions_and_form(self):
        cliente_id = self._create_client("Cliente Form Abono")
        orden_id = self._create_order(price=20.0)
        self.assertEqual(self._charge(orden_id, "usd", 10, modo_cobro="parcial", cliente_id=cliente_id).status_code, 302)
        cuenta_id, _, _, _ = self._cuenta_por_orden(orden_id)

        detalle = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}")
        self.assertIn(b"Registrar abono", detalle.data)
        self.assertIn(b"Pagar saldo completo", detalle.data)

        form = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}/abono?completo=1")
        self.assertEqual(form.status_code, 200)
        self.assertIn(b"Metodo de pago", form.data)
        self.assertIn(b"Saldo pendiente", form.data)

    def test_admin_cxc_routes_require_master_role(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)",
            ("Mesonera Test", "0000", "mesonera"),
        )
        usuario_id = web_app.obtener_ultimo_id(cursor, "usuarios")
        conn.commit()
        conn.close()
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = usuario_id
            sess["usuario_nombre"] = "Mesonera Test"
            sess["usuario"] = "Mesonera Test"
            sess["usuario_rol"] = "mesonera"
        self.assertEqual(self.client.get("/clientes").status_code, 403)
        self.assertEqual(self.client.get("/cuentas_por_cobrar").status_code, 403)


if __name__ == "__main__":
    unittest.main()
