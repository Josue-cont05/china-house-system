import importlib
import os
import tempfile
import unittest


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
            "pagos",
            "orden_items",
            "ordenes",
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

    def _charge(self, orden_id, metodo1, monto1, metodo2="", monto2="", descuento=0):
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

    def test_recharge_updates_snapshot_and_replaces_payments(self):
        orden_id = self._create_order()
        self.assertEqual(self._charge(orden_id, "usd", 10).status_code, 302)

        with self.client.session_transaction() as sess:
            sess["emergencias_activas"] = [str(orden_id)]

        self.assertEqual(self._charge(orden_id, "bs_pago_movil", 1800, descuento=200).status_code, 302)
        snapshot, pagos = self._snapshot(orden_id)
        self.assertEqual(snapshot[2:7], (200.0, 10.0, 200.0, 9.0, 1800.0))
        self.assertEqual([(p[0], p[1]) for p in pagos], [("bs_pago_movil", 1800.0)])

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


if __name__ == "__main__":
    unittest.main()
