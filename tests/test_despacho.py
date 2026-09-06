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
        cursor.execute("SELECT estado, despachado_at, despachado_por, facturar FROM ordenes WHERE id=?", (orden_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def _alertas_pendientes(self):
        repo = web_app.SqlServiceAlertsRepository(web_app.get_connection)
        return repo.listar_pendientes()

    def _despacho_html(self):
        return self.client.get("/despacho").get_data(as_text=True)

    def _estado_json(self):
        return self.client.get("/api/despacho/estado").get_json()


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
        estado, despachado_at, despachado_por, _facturar = self._estado_orden(orden_id)
        self.assertIsNotNone(despachado_at)
        self.assertEqual(despachado_por, "Monica")

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

        _estado, despachado_at, _por, facturar = self._estado_orden(orden_id)
        self.assertIsNone(despachado_at)
        self.assertEqual(facturar, 1)

    def test_tarjeta_facturar_apunta_a_la_ruta_existente(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        html = self._despacho_html()
        self.assertIn(f'href="/activar_factura/{orden_id}"', html)
        self.assertIn(f'href="/orden/{orden_id}"', html)


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

        _estado, despachado_at, _por, _f = self._estado_orden(orden_id)
        self.assertIsNone(despachado_at)
        html = self._despacho_html()
        self.assertIn(f'data-orden-id="{orden_id}"', html)


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


if __name__ == "__main__":
    unittest.main()
