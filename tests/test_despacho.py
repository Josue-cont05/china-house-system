"""Tests de integracion (rutas Flask reales, via test_client) de la
pantalla DESPACHO y las alertas de servicio por bebidas adicionales
(mision "PANTALLA OPERATIVA DE DESPACHO PARA MONICA + ALERTAS DE
BEBIDAS ADICIONALES EN MESAS").

Cubre las dos familias de escenarios obligatorios de la mision:
- DESPACHO: visibilidad de pedidos activos/entregados, ENTREGADO
  idempotente con timestamp/usuario, facturar != entregar, orden de
  antiguedad, indicador EN COCINA/LISTO.
- BEBIDAS: una alerta se crea SOLO cuando una mesa ya enviada recibe
  despues productos clasificados para atencion de despacho; nunca en
  el envio inicial; nunca para Pick Up/Delivery; ATENDIDO no toca el
  estado de entrega de la orden.
"""

import os
import tempfile
import unittest
import unittest.mock

from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_despacho_{os.getpid()}.db"
)


class DespachoRoutesTest(unittest.TestCase):
    """Usa su propia base SQLite privada (no la compartida), igual
    patron que test_print_queue_routes.py."""

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
        self.client = web_app.app.test_client()
        self._clear_data()
        self._login()

    def _conn(self):
        return web_app.get_connection()

    def _clear_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in (
            "service_alerts",
            "print_jobs",
            "cierre_detalle",
            "cierres_caja",
            "pagos",
            "orden_comanda_items",
            "orden_comandas",
            "orden_items",
            "ordenes",
            "productos",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _login(self, rol="mesonera"):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 999
            sess["usuario_nombre"] = "Monica"
            sess["usuario"] = "Monica"
            sess["usuario_rol"] = rol

    def _crear_orden(self, tipo="Mesa", referencia="Mesa 4", estado="abierta", **campos):
        conn = self._conn()
        cursor = conn.cursor()
        columnas = dict(
            numero_orden=None, fecha_hora="2026-09-05 19:12:00", fecha="2026-09-05",
            tipo=tipo, referencia=referencia, cliente="Cliente", estado=estado,
            usuario_id=None,
        )
        columnas.update(campos)
        nombres = ",".join(columnas.keys())
        placeholders = ",".join("?" for _ in columnas)
        cursor.execute(
            f"INSERT INTO ordenes ({nombres}) VALUES ({placeholders})", tuple(columnas.values())
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _agregar_item(self, orden_id, producto="Arroz Frito", precio=5.0, indicacion=""):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, ?)",
            (orden_id, producto, precio, indicacion),
        )
        conn.commit()
        conn.close()

    def _categoria_id(self, nombre):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM categorias WHERE nombre=?", (nombre,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def _crear_producto(self, nombre, categoria_nombre, precio=1.0):
        categoria_id = self._categoria_id(categoria_nombre)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id, activo) VALUES (?, ?, ?, 1)",
            (nombre, precio, categoria_id),
        )
        conn.commit()
        conn.close()

    def _estado_orden(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT estado, listo_despacho_at, listo_despacho_por, facturar FROM ordenes WHERE id=?", (orden_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def _marcar_cobrada(self, orden_id):
        """Simula lo que hace /cobrar sobre ordenes.estado (lo unico
        relevante para estos tests): lo sobreescribe a 'cerrada' con una
        fecha_cobro, sin pasar por el formulario completo de pago."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ordenes SET estado='cerrada', fecha_cobro=? WHERE id=?",
            ("2026-09-05 19:30:00", orden_id),
        )
        conn.commit()
        conn.close()

    def _tiene_job_recibo(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM print_jobs WHERE event_key=? AND required_role LIKE 'RECIBO%'",
            (f"{orden_id}-base",),
        )
        n = cursor.fetchone()[0]
        conn.close()
        return n > 0

    def _alertas_pendientes(self):
        repo = web_app.SqlServiceAlertsRepository(web_app.get_connection)
        return repo.listar_pendientes()

    def _despacho_html(self):
        return self.client.get("/despacho").get_data(as_text=True)

    def _estado_json(self):
        return self.client.get("/api/despacho/estado").get_json()


class PermisosDespachoTest(DespachoRoutesTest):
    """/despacho debe exigir el mismo permiso que tomar ordenes (mision
    "DESPACHO para Monica"): un rol que no puede tomar ordenes (cocina,
    cocina_reportes) recibe 403, no el HTML de la pantalla. Regresion
    real encontrada en refactor/division-clases-completa: el
    before_request central (`proteger_sistema`) filtraba por el string
    plano "despacho", que nunca coincidio con el endpoint real de la
    ruta (`pantalla_despacho`), asi que /despacho quedaba abierto a
    cualquier rol autenticado."""

    def test_rol_cocina_no_puede_ver_despacho(self):
        self._login(rol="cocina")
        self.assertEqual(self.client.get("/despacho").status_code, 403)

    def test_rol_mesonera_puede_ver_despacho(self):
        self._login(rol="mesonera")
        self.assertEqual(self.client.get("/despacho").status_code, 200)


class VisibilidadPedidosTest(DespachoRoutesTest):
    def test_orden_recien_enviada_a_cocina_aparece_en_despacho(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{orden_id}"', html)

    def test_orden_abierta_sin_enviar_no_aparece(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)

        html = self._despacho_html()
        self.assertNotIn(f'data-orden-id="{orden_id}"', html)

    def test_orden_entregada_desaparece_de_despacho(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.post(f"/despacho/{orden_id}/entregado")

        html = self._despacho_html()
        self.assertNotIn(f'data-orden-id="{orden_id}"', html)

    def test_mesa_pickup_delivery_aparecen_todas(self):
        mesa_id = self._crear_orden(tipo="Mesa", referencia="Mesa 1")
        pickup_id = self._crear_orden(tipo="Para llevar", referencia="Pedro")
        delivery_id = self._crear_orden(tipo="Delivery", referencia="Calle 5")
        for oid in (mesa_id, pickup_id, delivery_id):
            self._agregar_item(oid)
            self.client.get(f"/enviar_cocina/{oid}")

        html = self._despacho_html()
        for oid in (mesa_id, pickup_id, delivery_id):
            self.assertIn(f'data-orden-id="{oid}"', html)

    def test_orden_mas_antigua_aparece_primero(self):
        orden_a = self._crear_orden(referencia="Mesa A")
        self._agregar_item(orden_a)
        self.client.get(f"/enviar_cocina/{orden_a}")

        orden_b = self._crear_orden(referencia="Mesa B")
        self._agregar_item(orden_b)
        self.client.get(f"/enviar_cocina/{orden_b}")

        html = self._despacho_html()
        pos_a = html.find(f'data-orden-id="{orden_a}"')
        pos_b = html.find(f'data-orden-id="{orden_b}"')
        self.assertNotEqual(pos_a, -1)
        self.assertNotEqual(pos_b, -1)
        self.assertLess(pos_a, pos_b)

    def test_indicador_en_cocina_y_listo(self):
        orden_en_cocina = self._crear_orden(referencia="Mesa 1")
        self._agregar_item(orden_en_cocina)
        self.client.get(f"/enviar_cocina/{orden_en_cocina}")

        orden_lista = self._crear_orden(referencia="Mesa 2")
        self._agregar_item(orden_lista)
        self.client.get(f"/enviar_cocina/{orden_lista}")
        # /listo/<id> esta gateado a rol cocina; aqui solo interesa el
        # estado resultante en despacho, asi que se marca directo.
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE ordenes SET estado='listo' WHERE id=?", (orden_lista,))
        conn.commit()
        conn.close()

        html = self._despacho_html()
        self.assertIn("EN COCINA", html)
        self.assertIn("LISTO", html)


class EntregadoIdempotenteTest(DespachoRoutesTest):
    def test_entregado_guarda_timestamp_y_usuario(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self.client.post(f"/despacho/{orden_id}/entregado")

        self.assertEqual(respuesta.get_json(), {"ok": True})
        estado, listo_despacho_at, listo_despacho_por, _facturar = self._estado_orden(orden_id)
        self.assertIsNotNone(listo_despacho_at)
        self.assertEqual(listo_despacho_por, "Monica")

    def test_doble_click_no_produce_dos_entregas(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.post(f"/despacho/{orden_id}/entregado")
        _estado, primera_fecha, primer_usuario, _f = self._estado_orden(orden_id)

        with self.client.session_transaction() as sess:
            sess["usuario_nombre"] = "OtroUsuario"

        self.client.post(f"/despacho/{orden_id}/entregado")
        _estado, segunda_fecha, segundo_usuario, _f = self._estado_orden(orden_id)

        self.assertEqual(primera_fecha, segunda_fecha)
        self.assertEqual(primer_usuario, segundo_usuario)

    def test_entregado_no_marca_facturar_ni_cierra(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.post(f"/despacho/{orden_id}/entregado")

        estado, _at, _por, facturar = self._estado_orden(orden_id)
        self.assertNotEqual(estado, "cerrada")
        self.assertIn(facturar, (0, None))

    def test_facturar_no_marca_entregado(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.get(f"/activar_factura/{orden_id}")

        _estado, listo_despacho_at, _por, facturar = self._estado_orden(orden_id)
        self.assertIsNone(listo_despacho_at)
        self.assertEqual(facturar, 1)

    def test_tarjeta_facturar_apunta_a_la_ruta_existente(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        html = self._despacho_html()
        self.assertIn(f'href="/activar_factura/{orden_id}"', html)
        self.assertIn(f'href="/orden/{orden_id}"', html)

    def test_facturar_desde_despacho_genera_job_y_no_retira_la_tarjeta(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.get(f"/activar_factura/{orden_id}")

        self.assertTrue(self._tiene_job_recibo(orden_id))
        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{orden_id}"', html)


class VisibilidadFinancieraTest(DespachoRoutesTest):
    """Corrige la regresion detectada antes del push: CERRADA/COBRADA/
    FACTURADA NO son ENTREGADA. La unica condicion de salida de
    DESPACHO es listo_despacho_at IS NOT NULL (ver docstring de
    listar_pedidos_despacho en kitchen_comandas.py para la unica
    excepcion auditada: cierre_id, el archivo de jornada, no el cobro)."""

    def test_orden_en_cocina_aparece(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_orden_lista_aparece(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE ordenes SET estado='listo' WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()

        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_orden_facturada_sigue_apareciendo(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.get(f"/activar_factura/{orden_id}")

        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_orden_cobrada_sigue_apareciendo(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_cobrada(orden_id)

        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_orden_cerrada_pero_no_despachada_sigue_apareciendo(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_cobrada(orden_id)

        estado, listo_despacho_at, _por, _f = self._estado_orden(orden_id)
        self.assertEqual(estado, "cerrada")
        self.assertIsNone(listo_despacho_at)
        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_entregado_retira_la_tarjeta(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)

        self.client.post(f"/despacho/{orden_id}/entregado")

        self.assertNotIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_facturar_no_cambia_listo_despacho_at(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.get(f"/activar_factura/{orden_id}")

        _estado, listo_despacho_at, _por, _f = self._estado_orden(orden_id)
        self.assertIsNone(listo_despacho_at)

    def test_cobrar_no_cambia_listo_despacho_at(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_cobrada(orden_id)

        _estado, listo_despacho_at, _por, _f = self._estado_orden(orden_id)
        self.assertIsNone(listo_despacho_at)

    def test_cerrar_financieramente_no_equivale_a_entregar(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_cobrada(orden_id)

        estado, listo_despacho_at, listo_despacho_por, _f = self._estado_orden(orden_id)
        self.assertEqual(estado, "cerrada")
        self.assertIsNone(listo_despacho_at)
        self.assertIsNone(listo_despacho_por)
        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_delivery_cerrado_pero_no_despachado_sigue_visible(self):
        orden_id = self._crear_orden(tipo="Delivery", referencia="Calle 5")
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_cobrada(orden_id)

        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{orden_id}"', html)
        self.assertIn("LISTO PARA DELIVERY", html)

    def test_pickup_cerrado_pero_no_entregado_sigue_visible(self):
        orden_id = self._crear_orden(tipo="Para llevar", referencia="Pedro")
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_cobrada(orden_id)

        self.assertIn(f'data-orden-id="{orden_id}"', self._despacho_html())

    def test_badge_listo_se_mantiene_tras_cobrar(self):
        # cobrar() sobreescribe ordenes.estado a 'cerrada', perdiendo el
        # 'listo' anterior -- el badge debe seguir viniendo de
        # orden_comandas.estado, no de ordenes.estado.
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE orden_comandas SET estado='listo' WHERE orden_id=?", (orden_id,))
        conn.commit()
        conn.close()

        self._marcar_cobrada(orden_id)

        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{orden_id}"', html)
        # Unica orden en pantalla: debe mostrar LISTO, no EN COCINA.
        self.assertIn("LISTO", html)
        self.assertNotIn("EN COCINA", html)


class AlertasBebidasTest(DespachoRoutesTest):
    def test_bebida_en_pedido_inicial_no_genera_alerta(self):
        orden_id = self._crear_orden()
        self._crear_producto("Frescolita", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self._agregar_item(orden_id, producto="Frescolita")

        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._alertas_pendientes(), [])

    def test_bebida_agregada_despues_genera_una_alerta(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")

        alertas = self._alertas_pendientes()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["payload"]["items"], ["1x Coca-Cola"])

    def test_varios_items_agregados_juntos_forman_una_sola_alerta(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._crear_producto("Cerveza", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Coca-Cola")
        self._agregar_item(orden_id, producto="Coca-Cola")
        self._agregar_item(orden_id, producto="Cerveza")
        self.client.get(f"/enviar_cocina/{orden_id}")

        alertas = self._alertas_pendientes()
        self.assertEqual(len(alertas), 1)
        self.assertCountEqual(alertas[0]["payload"]["items"], ["2x Coca-Cola", "1x Cerveza"])

    def test_producto_no_clasificado_agregado_despues_no_genera_alerta(self):
        orden_id = self._crear_orden()
        self._crear_producto("Lumpia", "Platos adicionales")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Lumpia")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._alertas_pendientes(), [])

    def test_pickup_con_bebida_agregada_no_genera_alerta(self):
        orden_id = self._crear_orden(tipo="Para llevar", referencia="Pedro")
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._alertas_pendientes(), [])

    def test_delivery_con_bebida_agregada_no_genera_alerta(self):
        orden_id = self._crear_orden(tipo="Delivery", referencia="Calle 5")
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._alertas_pendientes(), [])

    def test_alerta_persiste_hasta_ser_atendida(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")

        # Simula un refresh: leer /despacho varias veces no borra la alerta.
        self._despacho_html()
        self._despacho_html()

        self.assertEqual(len(self._alertas_pendientes()), 1)

    def test_atendido_elimina_la_alerta_y_guarda_usuario_y_hora(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")
        alerta_id = self._alertas_pendientes()[0]["id"]

        respuesta = self.client.post(f"/despacho/alertas/{alerta_id}/atendido")

        self.assertEqual(respuesta.get_json(), {"ok": True})
        self.assertEqual(self._alertas_pendientes(), [])
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT atendido_at, atendido_por FROM service_alerts WHERE id=?", (alerta_id,))
        atendido_at, atendido_por = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(atendido_at)
        self.assertEqual(atendido_por, "Monica")

    def test_atendido_no_marca_la_orden_como_entregada(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")
        alerta_id = self._alertas_pendientes()[0]["id"]

        self.client.post(f"/despacho/alertas/{alerta_id}/atendido")

        _estado, listo_despacho_at, _por, _f = self._estado_orden(orden_id)
        self.assertIsNone(listo_despacho_at)
        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{orden_id}"', html)


class _AbortingCursor:
    """Envuelve un cursor real reproduciendo la semantica REAL de
    PostgreSQL ante un fallo dentro de una transaccion: una vez que una
    sentencia falla, la transaccion queda "aborted" y CUALQUIER sentencia
    posterior (menos un ROLLBACK/ROLLBACK TO SAVEPOINT) sigue fallando,
    hasta que se libera con ese rollback. sqlite3 (usado en estos tests)
    NO tiene esta semantica -- por eso no basta con un mock que solo
    lance una excepcion una vez; hay que simularla explicitamente
    (incluyendo que un COMMIT sobre una transaccion abortada equivale a
    un ROLLBACK, ver _AbortingConnection.commit) para que la prueba
    detecte de verdad si el codigo usa SAVEPOINT."""

    def __init__(self, real_cursor, poison_needle, conn_state):
        self._real = real_cursor
        self._poison_needle = poison_needle
        self._conn_state = conn_state

    def execute(self, sql, params=()):
        stripped = sql.strip().upper()
        if self._conn_state.aborted:
            if stripped.startswith("ROLLBACK"):
                self._conn_state.aborted = False
                return self._real.execute(sql, params)
            raise Exception(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        if self._poison_needle in stripped and stripped.startswith("INSERT"):
            self._conn_state.aborted = True
            raise Exception("simulated INSERT failure poisoning the transaction")
        return self._real.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _AbortingConnection:
    def __init__(self, real_conn, poison_needle):
        self._real = real_conn
        self._poison_needle = poison_needle
        self.aborted = False

    def cursor(self):
        return _AbortingCursor(self._real.cursor(), self._poison_needle, self)

    def commit(self):
        # Postgres real: COMMIT sobre una transaccion "aborted" se
        # convierte en ROLLBACK (con un WARNING), nunca confirma nada.
        if self.aborted:
            self.aborted = False
            return self._real.rollback()
        return self._real.commit()

    def __getattr__(self, name):
        return getattr(self._real, name)


class ServiceAlertTransactionIsolationTest(DespachoRoutesTest):
    """Mision seccion 12/13: un fallo REAL (a nivel SQL, no solo una
    excepcion de Python mockeada) al crear una service_alert NUNCA debe
    poder tumbar la comanda/print_job de cocina que ya se creo en la
    misma transaccion -- ni siquiera bajo la semantica de PostgreSQL,
    donde una sentencia fallida deja la transaccion "aborted" hasta un
    ROLLBACK (posible o total)."""

    def test_fallo_real_de_service_alert_no_pierde_comanda_ni_print_job(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Coca-Cola")

        conexion_real = web_app.get_connection

        def fabrica_abortante():
            return _AbortingConnection(conexion_real(), "SERVICE_ALERTS")

        with unittest.mock.patch.object(web_app, "get_connection", fabrica_abortante):
            respuesta = self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(respuesta.status_code, 302)

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, secuencia FROM orden_comandas WHERE orden_id=? ORDER BY secuencia",
            (orden_id,),
        )
        comandas = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM print_jobs WHERE required_role='COCINA'")
        total_print_jobs = cursor.fetchone()[0]
        conn.close()

        self.assertEqual([c[1] for c in comandas], [0, 1])
        self.assertEqual(total_print_jobs, 2)
        # La alerta se perdio (tolerable) pero NUNCA la comanda/print_job.
        self.assertEqual(self._alertas_pendientes(), [])


class EscenarioAutoReviewTest(DespachoRoutesTest):
    """Reproduce el escenario de autoverificacion de la mision (seccion
    28): Monica factura Mesa 4, luego Mesa 3 recibe bebidas agregadas
    (alerta), atiende la alerta, y por separado marca Mesa 4 entregada.
    Verifica: facturar != entregar; alerta atendida != orden entregada."""

    def test_escenario_autoreview_completo(self):
        self._crear_producto("Coca-Cola", "Bebidas")
        self._crear_producto("Cerveza", "Bebidas")

        mesa_3 = self._crear_orden(referencia="Mesa 3")
        self._agregar_item(mesa_3, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{mesa_3}")

        mesa_4 = self._crear_orden(referencia="Mesa 4")
        self._agregar_item(mesa_4, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{mesa_4}")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE ordenes SET estado='listo' WHERE id=?", (mesa_4,))
        conn.commit()
        conn.close()

        # Monica factura Mesa 4 (no debe afectar despacho).
        self.client.get(f"/activar_factura/{mesa_4}")
        _estado, despachado_mesa_4, _por, facturar_mesa_4 = self._estado_orden(mesa_4)
        self.assertIsNone(despachado_mesa_4)
        self.assertEqual(facturar_mesa_4, 1)

        # Mesa 3 agrega bebidas -> debe generar UNA alerta.
        self._agregar_item(mesa_3, producto="Coca-Cola")
        self._agregar_item(mesa_3, producto="Coca-Cola")
        self._agregar_item(mesa_3, producto="Cerveza")
        self.client.get(f"/enviar_cocina/{mesa_3}")

        estado_json = self._estado_json()
        self.assertEqual(estado_json["contador_alertas"], 1)
        alerta_id = self._alertas_pendientes()[0]["id"]

        # Monica atiende la alerta -> desaparece, Mesa 3 sigue activa.
        self.client.post(f"/despacho/alertas/{alerta_id}/atendido")
        self.assertEqual(self._alertas_pendientes(), [])
        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{mesa_3}"', html)

        # Monica marca Mesa 4 ENTREGADO -> desaparece de despacho.
        self.client.post(f"/despacho/{mesa_4}/entregado")
        html = self._despacho_html()
        self.assertNotIn(f'data-orden-id="{mesa_4}"', html)
        self.assertIn(f'data-orden-id="{mesa_3}"', html)


class CierreJornadaDespachoTest(DespachoRoutesTest):
    """Corrige el hueco detectado antes del push: cerrar_jornada()
    archivaba (asignaba cierre_id) ordenes ya cobradas sin exigir que
    Monica las hubiera entregado, haciendolas desaparecer de DESPACHO
    sin pasar por listo_despacho_at. Ver el docstring de
    listar_pedidos_despacho() (kitchen_comandas.py) para la unica
    excepcion aceptada (cierre_id de un dia YA archivado, para no
    resucitar historico)."""

    def setUp(self):
        super().setUp()
        self._login(rol="master")

    def _cierre_ids(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, cierre_id, listo_despacho_at FROM ordenes ORDER BY id")
        filas = cursor.fetchall()
        conn.close()
        return filas

    def test_cierre_bloqueado_por_orden_en_cocina_no_despachada(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self.client.get("/cerrar_jornada")

        self.assertIn("No se puede cerrar la jornada", respuesta.get_data(as_text=True))
        _id, cierre_id, _listo_despacho_at = self._cierre_ids()[0]
        self.assertIsNone(cierre_id)

    def test_cierre_bloqueado_por_orden_lista_no_despachada(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE ordenes SET estado='listo' WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()

        respuesta = self.client.get("/cerrar_jornada")

        self.assertIn("No se puede cerrar la jornada", respuesta.get_data(as_text=True))
        _id, cierre_id, _listo_despacho_at = self._cierre_ids()[0]
        self.assertIsNone(cierre_id)

    def test_cierre_bloqueado_por_orden_cerrada_no_despachada(self):
        # El hueco real: cobrada (estado='cerrada') pero no entregada.
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)

        respuesta = self.client.get("/cerrar_jornada")

        self.assertIn(
            "No se puede cerrar la jornada: hay pedidos pendientes en Despacho.",
            respuesta.get_data(as_text=True),
        )
        _id, cierre_id, listo_despacho_at = self._cierre_ids()[0]
        self.assertIsNone(cierre_id)
        self.assertIsNone(listo_despacho_at)

    def test_cierre_permitido_despues_de_entregado(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)
        self.client.post(f"/despacho/{orden_id}/entregado")

        respuesta = self.client.get("/cerrar_jornada")

        cuerpo = respuesta.get_data(as_text=True)
        self.assertNotIn("No se puede cerrar la jornada", cuerpo)
        _id, cierre_id, listo_despacho_at = self._cierre_ids()[0]
        self.assertIsNotNone(cierre_id)
        self.assertIsNotNone(listo_despacho_at)

    def test_historico_archivado_sigue_fuera_de_despacho(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)
        self.client.post(f"/despacho/{orden_id}/entregado")
        self.client.get("/cerrar_jornada")

        html = self._despacho_html()
        self.assertNotIn(f'data-orden-id="{orden_id}"', html)

    def test_cierre_no_modifica_listo_despacho_at(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)
        self.client.post(f"/despacho/{orden_id}/entregado")
        _id, _cierre_id, despachado_antes = self._cierre_ids()[0]

        self.client.get("/cerrar_jornada")

        _id, _cierre_id, despachado_despues = self._cierre_ids()[0]
        self.assertEqual(despachado_antes, despachado_despues)

    def test_mensaje_de_bloqueo_es_claro(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)

        respuesta = self.client.get("/cerrar_jornada")

        cuerpo = respuesta.get_data(as_text=True)
        self.assertIn(
            "No se puede cerrar la jornada: hay pedidos pendientes en Despacho.",
            cuerpo,
        )
        self.assertIn("Despacho", cuerpo)

    def test_orden_eliminada_no_bloquea_cierre(self):
        # Auditoria: en este proyecto "anular/cancelar" una orden es
        # eliminarla (DELETE FROM ordenes via /eliminar_orden), no un
        # estado persistido -- no existe "anulada" en ordenes.estado.
        # Una vez eliminada, deja de existir para cualquier conteo.
        pendiente_id = self._crear_orden(referencia="Mesa 1")
        self._agregar_item(pendiente_id)
        self.client.get(f"/enviar_cocina/{pendiente_id}")

        cobrada_id = self._crear_orden(referencia="Mesa 2")
        self._agregar_item(cobrada_id)
        self.client.get(f"/enviar_cocina/{cobrada_id}")
        self._marcar_cobrada(cobrada_id)
        self.client.post(f"/despacho/{cobrada_id}/entregado")

        # "pendiente_id" bloquearia el cierre (en cocina, no despachada);
        # se cancela/anula eliminandola, como ya permite el sistema.
        self.client.post(
            f"/eliminar_orden/{pendiente_id}",
            data={"clave": web_app.CLAVE_SUPERVISOR},
        )

        respuesta = self.client.get("/cerrar_jornada")

        cuerpo = respuesta.get_data(as_text=True)
        self.assertNotIn("No se puede cerrar la jornada", cuerpo)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ordenes WHERE id=?", (pendiente_id,))
        existe = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(existe, 0)


class IncrementalKitchenRegressionTest(DespachoRoutesTest):
    """Regresion real detectada antes del push: una vez que una mesa
    quedaba COBRADA (estado='cerrada'), /agregar (y el equivalente de
    self-ordering) rechazaban cualquier producto nuevo con "orden
    cerrada" -- una regla que tenia sentido ANTES de Despacho (cerrada
    significaba "terminada"), pero que nunca se actualizo cuando la
    mision Despacho redefinio CERRADA != ENTREGADA. El sintoma
    reportado ("Plato B no llega a cocina, no se imprime, no aparece en
    Despacho, pero una bebida agregada despues SI genera alerta") se
    explica exactamente asi: si la mesa NO estaba cobrada, agregar y
    enviar funcionaba siempre (bebida incluida); si SI estaba cobrada,
    /agregar rechazaba el plato ANTES de que llegara a orden_items, por
    lo que jamas habia nada que enviar.

    Fix real: app/domain/sales/order_states.py::puede_agregar_item_orden
    -- agregar un item NUEVO solo se bloquea por orden archivada o ya
    despachada, nunca solo por estar cobrada. Aplicado en /agregar
    (web_app.py) y en self-ordering (_revalidar_destino /
    _validar_orden_mesa_abierta)."""

    def setUp(self):
        super().setUp()
        web_app.asegurar_menu_neko_wok()
        web_app.desactivar_menu_china_house()

    def _producto_id(self, nombre):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM productos WHERE nombre=? ORDER BY id LIMIT 1", (nombre,))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row, nombre)
        return row[0]

    def _comandas(self, orden_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, secuencia FROM orden_comandas WHERE orden_id=? ORDER BY secuencia",
            (orden_id,),
        )
        filas = cursor.fetchall()
        conn.close()
        return filas

    def _items_de_comanda(self, comanda_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT oi.producto FROM orden_comanda_items ci "
            "JOIN orden_items oi ON oi.id = ci.orden_item_id "
            "WHERE ci.comanda_id=? ORDER BY oi.id",
            (comanda_id,),
        )
        filas = [r[0] for r in cursor.fetchall()]
        conn.close()
        return filas

    def _print_job_event_keys(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT event_key FROM print_jobs WHERE required_role='COCINA'")
        filas = [r[0] for r in cursor.fetchall()]
        conn.close()
        return filas

    # --- 1-10: ciclo de vida seq0 -> seq1 -> seq2, Despacho acumulado ---

    def test_primer_envio_crea_secuencia_cero_con_plato_a(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")

        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual([c[1] for c in comandas], [0])
        self.assertEqual(self._items_de_comanda(comandas[0][0]), ["Plato A"])

    def test_plato_agregado_pero_no_enviado_no_aparece_en_despacho(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Plato B")

        html = self._despacho_html()
        inicio = html.find(f'data-orden-id="{orden_id}"')
        fin = html.find("pedido-acciones", inicio)
        tarjeta = html[inicio:fin]
        self.assertIn("Plato A", tarjeta)
        self.assertNotIn("Plato B", tarjeta)

    def test_enviar_plato_b_crea_secuencia_uno_solo_con_plato_b(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato B")

        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual([c[1] for c in comandas], [0, 1])
        self.assertEqual(self._items_de_comanda(comandas[1][0]), ["Plato B"])

    def test_secuencia_uno_crea_print_job_cocina(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato B")

        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual(len(self._print_job_event_keys()), 2)
        self.assertIn(f"comanda-{comandas[1][0]}-base", self._print_job_event_keys())

    def test_despacho_tras_secuencia_uno_muestra_a_y_b(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato B")
        self.client.get(f"/enviar_cocina/{orden_id}")

        html = self._despacho_html()
        inicio = html.find(f'data-orden-id="{orden_id}"')
        fin = html.find("pedido-acciones", inicio)
        tarjeta = html[inicio:fin]
        self.assertIn("Plato A", tarjeta)
        self.assertIn("Plato B", tarjeta)

    def test_agregar_plato_c_crea_secuencia_dos(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato B")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato C")

        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual([c[1] for c in comandas], [0, 1, 2])
        self.assertEqual(self._items_de_comanda(comandas[2][0]), ["Plato C"])

    def test_despacho_tras_secuencia_dos_muestra_a_b_c(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato B")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato C")
        self.client.get(f"/enviar_cocina/{orden_id}")

        html = self._despacho_html()
        inicio = html.find(f'data-orden-id="{orden_id}"')
        fin = html.find("pedido-acciones", inicio)
        tarjeta = html[inicio:fin]
        for nombre in ("Plato A", "Plato B", "Plato C"):
            self.assertIn(nombre, tarjeta)

    def test_event_keys_de_seq0_seq1_seq2_son_distintos(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato B")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Plato C")
        self.client.get(f"/enviar_cocina/{orden_id}")

        claves = self._print_job_event_keys()
        self.assertEqual(len(claves), len(set(claves)))
        self.assertEqual(len(claves), 3)

    # --- Caso plato + bebida en el mismo lote ---

    def test_plato_y_bebida_en_mismo_lote_no_pierde_el_plato(self):
        orden_id = self._crear_orden()
        self._crear_producto("Coca-Cola", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Chop Suey")
        self._agregar_item(orden_id, producto="Coca-Cola")
        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual(len(comandas), 2)
        items_lote2 = self._items_de_comanda(comandas[1][0])
        self.assertIn("Chop Suey", items_lote2)
        self.assertIn("Coca-Cola", items_lote2)
        self.assertEqual(len(self._print_job_event_keys()), 2)

    def test_bebida_incremental_no_interrumpe_el_flujo_normal(self):
        # Antes del fix, cualquier excepcion en la evaluacion de la
        # alerta habria revertido tambien la comanda/print_job. Se
        # verifica que agregar una bebida junto con un plato produce
        # AMBOS: comanda normal + alerta, uno no reemplaza al otro.
        orden_id = self._crear_orden()
        self._crear_producto("Cerveza", "Bebidas")
        self._agregar_item(orden_id, producto="Arroz Chino")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Lumpia")
        self._agregar_item(orden_id, producto="Cerveza")
        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual(len(comandas), 2)
        self.assertIn("Lumpia", self._items_de_comanda(comandas[1][0]))
        alertas = self._alertas_pendientes()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["payload"]["items"], ["1x Cerveza"])

    # --- Polling no muta estado ---

    def test_polling_de_despacho_no_modifica_estado_de_envio(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")

        for _ in range(5):
            self.client.get("/api/despacho/estado")

        comandas = self._comandas(orden_id)
        self.assertEqual([c[1] for c in comandas], [0])

    # --- LA REGRESION REAL: cobrar entre envios ---

    def test_cobrar_entre_envios_permite_agregar_y_enviar_incremental(self):
        """Reproduce EXACTAMENTE el bug reportado, usando la ruta REAL
        /agregar (no el atajo de test _agregar_item): Plato A se envia,
        la mesa se cobra (estado='cerrada') SIN estar despachada
        todavia, y despues se intenta agregar Plato B. Antes del fix,
        /agregar devolvia "No puedes agregar productos a una orden
        cerrada" y Plato B jamas llegaba a orden_items -- por lo que
        /enviar_cocina no tenia nada que enviar."""
        orden_id = self._crear_orden()
        producto_a = self._producto_id("Neko Clan Triple")
        self.client.get(f"/agregar/{orden_id}/{producto_a}")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)

        producto_b = self._producto_id("Chop Suey de Pollo")
        respuesta = self.client.get(f"/agregar/{orden_id}/{producto_b}")
        self.assertEqual(respuesta.status_code, 302)
        self.client.get(f"/enviar_cocina/{orden_id}")

        comandas = self._comandas(orden_id)
        self.assertEqual([c[1] for c in comandas], [0, 1])
        self.assertIn("Chop Suey de Pollo", self._items_de_comanda(comandas[1][0]))
        self.assertEqual(len(self._print_job_event_keys()), 2)
        html = self._despacho_html()
        inicio = html.find(f'data-orden-id="{orden_id}"')
        fin = html.find("pedido-acciones", inicio)
        tarjeta = html[inicio:fin]
        self.assertIn("Neko Clan Triple", tarjeta)
        self.assertIn("Chop Suey de Pollo", tarjeta)

    def test_agregar_via_ruta_real_tras_cobrar_ya_no_se_rechaza(self):
        orden_id = self._crear_orden()
        producto_id = self._producto_id("Neko Clan Triple")
        self.client.get(f"/agregar/{orden_id}/{producto_id}")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)

        respuesta = self.client.get(f"/agregar/{orden_id}/{producto_id}")

        self.assertEqual(respuesta.status_code, 302)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orden_items WHERE orden_id=?", (orden_id,))
        total = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(total, 2)

    def test_agregar_bloqueado_tras_entregado(self):
        orden_id = self._crear_orden()
        producto_id = self._producto_id("Neko Clan Triple")
        self.client.get(f"/agregar/{orden_id}/{producto_id}")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)
        self.client.post(f"/despacho/{orden_id}/entregado")

        respuesta = self.client.get(f"/agregar/{orden_id}/{producto_id}")

        self.assertIn("No puedes agregar productos", respuesta.get_data(as_text=True))

    def test_agregar_sigue_bloqueado_para_orden_archivada(self):
        orden_id = self._crear_orden()
        producto_id = self._producto_id("Neko Clan Triple")
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE ordenes SET cierre_id=1 WHERE id=?", (orden_id,))
        conn.commit()
        conn.close()

        respuesta = self.client.get(f"/agregar/{orden_id}/{producto_id}")

        self.assertIn("archivada", respuesta.get_data(as_text=True))

    # --- Self-ordering: misma regresion, mismo fix ---

    def test_self_ordering_cobrar_entre_envios_permite_incremental(self):
        orden_id = self._crear_orden(referencia="mesa:1")
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._marcar_cobrada(orden_id)

        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        token = link["token"]
        catalogo = web_app.app.test_client().get(f"/self-order/{token}")
        self.assertNotIn(b"Mesa no habilitada", catalogo.data)

        producto_id = self._producto_id("Neko Clan Triple")
        respuesta = web_app.app.test_client().post(
            f"/self-order/{token}/submit",
            json={
                "submission_id": "regresion-cobrar-1",
                "items": [
                    {
                        "producto_id": producto_id,
                        "cantidad": 1,
                        "configuracion": [],
                        "indicacion": "",
                    }
                ],
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        comandas = self._comandas(orden_id)
        self.assertEqual([c[1] for c in comandas], [0, 1])

    def test_self_ordering_bloqueado_tras_entregado(self):
        orden_id = self._crear_orden(referencia="mesa:1")
        self._agregar_item(orden_id, producto="Plato A")
        self.client.get(f"/enviar_cocina/{orden_id}")
        link = self.client.post(f"/orden/{orden_id}/self-ordering/link").get_json()["link"]
        token = link["token"]

        self._marcar_cobrada(orden_id)
        self.client.post(f"/despacho/{orden_id}/entregado")

        catalogo = web_app.app.test_client().get(f"/self-order/{token}")
        self.assertIn(b"Mesa no habilitada", catalogo.data)

        nuevo_link = self.client.post(f"/orden/{orden_id}/self-ordering/link")
        self.assertEqual(nuevo_link.status_code, 409)


class MigracionListoDespachoTest(DespachoRoutesTest):
    """Mision "correccion semantica de Despacho", seccion 16: migrar
    despachado_at/despachado_por -> listo_despacho_at/listo_despacho_por
    sin perder datos historicos y de forma idempotente."""

    def test_columnas_legacy_se_conservan(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(ordenes)")
        columnas = {fila[1] for fila in cursor.fetchall()}
        conn.close()
        self.assertIn("despachado_at", columnas)
        self.assertIn("despachado_por", columnas)
        self.assertIn("listo_despacho_at", columnas)
        self.assertIn("listo_despacho_por", columnas)

    def test_backfill_copia_legacy_solo_si_el_campo_nuevo_esta_vacio(self):
        orden_id = self._crear_orden()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ordenes SET despachado_at=?, despachado_por=? WHERE id=?",
            ("2026-08-01 12:00:00", "Monica", orden_id),
        )
        conn.commit()
        conn.close()

        web_app.migrar_listo_despacho_desde_legado()

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT listo_despacho_at, listo_despacho_por FROM ordenes WHERE id=?",
            (orden_id,),
        )
        listo_at, listo_por = cursor.fetchone()
        conn.close()
        self.assertEqual(listo_at, "2026-08-01 12:00:00")
        self.assertEqual(listo_por, "Monica")

    def test_backfill_no_sobreescribe_un_listo_despacho_at_ya_establecido(self):
        orden_id = self._crear_orden()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE ordenes
            SET despachado_at=?, despachado_por=?,
                listo_despacho_at=?, listo_despacho_por=?
            WHERE id=?
            """,
            ("2026-08-01 12:00:00", "Monica", "2026-08-01 09:00:00", "Sara", orden_id),
        )
        conn.commit()
        conn.close()

        web_app.migrar_listo_despacho_desde_legado()

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT listo_despacho_at, listo_despacho_por FROM ordenes WHERE id=?",
            (orden_id,),
        )
        listo_at, listo_por = cursor.fetchone()
        conn.close()
        self.assertEqual(listo_at, "2026-08-01 09:00:00")
        self.assertEqual(listo_por, "Sara")

    def test_init_db_es_idempotente_tras_la_migracion(self):
        orden_id = self._crear_orden()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ordenes SET despachado_at=?, despachado_por=? WHERE id=?",
            ("2026-08-01 12:00:00", "Monica", orden_id),
        )
        conn.commit()
        conn.close()

        web_app.init_db()
        web_app.init_db()

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT despachado_at, despachado_por, listo_despacho_at, listo_despacho_por FROM ordenes WHERE id=?",
            (orden_id,),
        )
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row, ("2026-08-01 12:00:00", "Monica", "2026-08-01 12:00:00", "Monica"))

    def test_marcar_listo_para_retirar_ya_no_escribe_columnas_legacy(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.post(f"/despacho/{orden_id}/entregado")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT despachado_at, despachado_por, listo_despacho_at, listo_despacho_por FROM ordenes WHERE id=?",
            (orden_id,),
        )
        despachado_at, despachado_por, listo_at, listo_por = cursor.fetchone()
        conn.close()
        self.assertIsNone(despachado_at)
        self.assertIsNone(despachado_por)
        self.assertIsNotNone(listo_at)
        self.assertEqual(listo_por, "Monica")


if __name__ == "__main__":
    unittest.main()
