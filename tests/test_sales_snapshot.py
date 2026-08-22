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
            "cuentas_por_cobrar_movimientos",
            "cuentas_por_cobrar",
            "pagos",
            "orden_items",
            "ordenes",
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

    def _columns(self, table):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1]: row for row in cursor.fetchall()}
        conn.close()
        return columns

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

    def _create_receivable(self, orden_id, cliente_id, monto=8.0):
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
        conn.commit()
        conn.close()
        return cuenta_id

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
