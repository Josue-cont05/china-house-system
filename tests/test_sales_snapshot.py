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


if __name__ == "__main__":
    unittest.main()
