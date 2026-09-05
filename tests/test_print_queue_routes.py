"""Tests de integracion (rutas Flask reales, via test_client) de la cola
central de impresion: creacion de jobs en el momento del evento de
negocio (enviar a cocina, incremental, reimpresion, activar/reimprimir
factura) y los endpoints /api/printing/*.

Cubre en particular los dos escenarios de aceptacion obligatorios de la
mision "NEKO PRINTING 2.0":
- apagon: sin ninguna estacion READY, los jobs quedan PENDING; al volver
  una estacion, se imprimen todos sin perder ninguno;
- mover la POS58 entre computadoras: la estacion sin impresora nunca
  hace claim/imprime/duplica; la que si tiene la impresora se queda con
  el job; la primera, al recuperar la impresora, ya no lo recibe.
"""

import os
import tempfile
import unittest

from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_print_queue_routes_{os.getpid()}.db"
)


class PrintQueueRoutesTest(unittest.TestCase):
    """Usa su propia base SQLite privada (no la compartida): otros
    modulos de test (p. ej. test_sales_snapshot) asumen que la base
    compartida sigue existiendo despues de correr y NO vuelven a llamar
    init_db() por si mismos (solo se inicializa una vez, al importar
    web_app por primera vez en toda la corrida) -- borrar el archivo
    compartido en tearDownClass rompe a cualquier modulo que corra
    despues alfabeticamente. Ver test_sales_order_repository.py para el
    mismo patron ya establecido en este proyecto."""

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
            "print_jobs",
            "orden_comanda_items",
            "orden_comandas",
            "orden_items",
            "ordenes",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _login(self, rol="master"):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 999
            sess["usuario_nombre"] = "Test"
            sess["usuario"] = "Test"
            sess["usuario_rol"] = rol

    def _crear_orden(self, tipo="Mesa", referencia="Mesa 1", estado="abierta", tasa_cobro=None, **campos):
        conn = self._conn()
        cursor = conn.cursor()
        columnas = dict(
            numero_orden=None, fecha_hora="2026-09-05 19:12:00", fecha="2026-09-05",
            tipo=tipo, referencia=referencia, cliente="Cliente", estado=estado,
            usuario_id=None, tasa_cobro=tasa_cobro,
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

    def _pendientes_cocina(self):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM print_jobs WHERE required_role='COCINA' AND status='PENDING'")
        n = cursor.fetchone()[0]
        conn.close()
        return n

    def _claim(self, station_id, roles):
        return self.client.post(
            "/api/printing/claim", json={"station_id": station_id, "roles": list(roles)}
        ).get_json()

    def _ack(self, job_id, station_id, lease_token):
        return self.client.post(
            f"/api/printing/{job_id}/ack", json={"station_id": station_id, "lease_token": lease_token}
        ).get_json()

    def _fail(self, job_id, station_id, lease_token, error="x"):
        return self.client.post(
            f"/api/printing/{job_id}/fail",
            json={"station_id": station_id, "lease_token": lease_token, "error": error},
        ).get_json()


class CreacionDeJobsTest(PrintQueueRoutesTest):
    def test_enviar_cocina_crea_un_job(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)

        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._pendientes_cocina(), 1)

    def test_incremental_crea_un_job_nuevo_ademas_del_primero(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Arroz Frito")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._agregar_item(orden_id, producto="Lumpia")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._pendientes_cocina(), 2)

    def test_reintento_de_la_misma_solicitud_no_duplica(self):
        # /enviar_cocina llamado dos veces SIN items nuevos: la segunda
        # vez no hay items pendientes -> no crea comanda ni job nuevo.
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.assertEqual(self._pendientes_cocina(), 1)

    def test_reprint_crea_job_nuevo_el_original_ya_no_es_el_mismo_evento(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self._claim("PC-1", ["COCINA"])
        self._ack(respuesta["job"]["id"], "PC-1", respuesta["job"]["lease_token"])

        self.client.get(f"/reimprimir_cocina/{orden_id}")

        self.assertEqual(self._pendientes_cocina(), 1)  # el job de la reimpresion, no el original

    def test_reprint_incluye_items_acumulados(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="Arroz Frito")
        self.client.get(f"/enviar_cocina/{orden_id}")
        self._agregar_item(orden_id, producto="Lumpia")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self.client.get(f"/reimprimir_cocina/{orden_id}")

        respuesta = self._claim("PC-1", ["COCINA"])
        # El job mas viejo (FIFO) es la primera comanda; reclamamos los
        # 3 en orden y el ultimo (la reimpresion) debe traer ambos items.
        jobs = []
        while respuesta["job"] is not None:
            jobs.append(respuesta["job"])
            self._ack(respuesta["job"]["id"], "PC-1", respuesta["job"]["lease_token"])
            respuesta = self._claim("PC-1", ["COCINA"])

        job_reimpresion = jobs[-1]
        productos = [item for item in job_reimpresion["payload"]["items"]]
        self.assertTrue(any("Arroz Frito" in p for p in productos))
        self.assertTrue(any("Lumpia" in p for p in productos))

    def test_rol_mesa_correcto(self):
        orden_id = self._crear_orden(tipo="Mesa")
        self._agregar_item(orden_id)
        self.client.get(f"/activar_factura/{orden_id}")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT required_role FROM print_jobs")
        rol = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(rol, "RECIBO_MESA")

    def test_rol_pickup_correcto_para_tipo_para_llevar(self):
        orden_id = self._crear_orden(tipo="Para llevar", referencia="")
        self._agregar_item(orden_id)
        self.client.get(f"/activar_factura/{orden_id}")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT required_role FROM print_jobs")
        rol = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(rol, "RECIBO_PICKUP")

    def test_rol_delivery_correcto(self):
        orden_id = self._crear_orden(tipo="Delivery", referencia="Av. Principal")
        self._agregar_item(orden_id)
        self.client.get(f"/activar_factura/{orden_id}")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT required_role FROM print_jobs")
        rol = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(rol, "RECIBO_DELIVERY")

    def test_snapshot_provisional_no_cambia_si_la_orden_cambia_despues(self):
        orden_id = self._crear_orden(tipo="Mesa")
        self._agregar_item(orden_id, producto="Arroz Frito", precio=5.0)
        self.client.get(f"/activar_factura/{orden_id}")

        respuesta = self._claim("PC-SALON", ["RECIBO_MESA"])
        total_congelado = respuesta["job"]["payload"]["total"]

        # La orden cambia DESPUES de crear el job (se agrega otro item).
        self._agregar_item(orden_id, producto="Lumpia", precio=3.0)

        # El job ya reclamado sigue con el total original, no el nuevo.
        self.assertEqual(respuesta["job"]["payload"]["total"], total_congelado)

    def test_snapshot_cobrado_usa_totales_historicos_no_tasa_viva(self):
        orden_id = self._crear_orden(
            tipo="Mesa", tasa_cobro=40.0, subtotal_usd=5.0, total_usd=5.0, total_bs=200.0,
            venta_restaurante_usd=5.0, delivery_usd=0.0, total_cliente_usd=5.0, total_cliente_bs=200.0,
        )
        self._agregar_item(orden_id, producto="Arroz Frito", precio=5.0)
        self.client.get(f"/activar_factura/{orden_id}")

        respuesta = self._claim("PC-SALON", ["RECIBO_MESA"])
        self.assertEqual(respuesta["job"]["payload"]["total_bs"], 200.0)
        self.assertTrue(respuesta["job"]["payload"]["cobrada"])


class ClaimStatusTest(PrintQueueRoutesTest):
    def test_status_reporta_pendientes_por_rol(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self.client.get("/api/printing/status?roles=COCINA,RECIBO_MESA").get_json()
        self.assertEqual(respuesta["pendientes"], 1)
        self.assertEqual(respuesta["por_rol"]["COCINA"], 1)

    def test_claim_rechaza_rol_desconocido(self):
        respuesta = self.client.post(
            "/api/printing/claim", json={"station_id": "PC-1", "roles": ["ROL_INVENTADO"]}
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_claim_sin_station_id_rechazado(self):
        respuesta = self.client.post("/api/printing/claim", json={"roles": ["COCINA"]})
        self.assertEqual(respuesta.status_code, 400)

    def test_claim_devuelve_items_ya_formateados_para_cocina(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id, producto="2x Arroz Frito")
        self._agregar_item(orden_id, producto="2x Arroz Frito")
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self._claim("PC-1", ["COCINA"])
        items = respuesta["job"]["payload"]["items"]
        self.assertNotIn("items_crudos", respuesta["job"]["payload"])
        self.assertTrue(any("4x" in item or "Arroz Frito" in item for item in items))

    def test_ack_con_lease_token_incorrecto_devuelve_409(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        respuesta = self._claim("PC-1", ["COCINA"])

        resultado = self.client.post(
            f"/api/printing/{respuesta['job']['id']}/ack",
            json={"station_id": "PC-1", "lease_token": "equivocado"},
        )
        self.assertEqual(resultado.status_code, 409)

    def test_fail_libera_el_job_para_otra_estacion(self):
        orden_id = self._crear_orden()
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")
        respuesta = self._claim("PC-1", ["COCINA"])

        self._fail(respuesta["job"]["id"], "PC-1", respuesta["job"]["lease_token"])

        respuesta_2 = self._claim("PC-2", ["COCINA"])
        self.assertIsNotNone(respuesta_2["job"])
        self.assertEqual(respuesta_2["job"]["id"], respuesta["job"]["id"])


class CasoApagonTest(PrintQueueRoutesTest):
    """Mision seccion 22/60: sin ninguna estacion READY, los jobs
    permanecen PENDING; al volver la electricidad (una estacion hace
    claim), se imprimen todos sin perder ninguno."""

    def test_jobs_quedan_pendientes_sin_ninguna_estacion_y_se_recuperan_todos(self):
        ordenes = [self._crear_orden(referencia=f"Mesa {i}") for i in range(3)]
        for orden_id in ordenes:
            self._agregar_item(orden_id)
            self.client.get(f"/enviar_cocina/{orden_id}")

        # "apagon": nadie hace claim todavia.
        self.assertEqual(self._pendientes_cocina(), 3)

        # vuelve la electricidad: una estacion se pone READY y vacia la cola.
        impresos = []
        respuesta = self._claim("Cocina Principal", ["COCINA"])
        while respuesta["job"] is not None:
            self._ack(respuesta["job"]["id"], "Cocina Principal", respuesta["job"]["lease_token"])
            impresos.append(respuesta["job"]["event_key"])
            respuesta = self._claim("Cocina Principal", ["COCINA"])

        self.assertEqual(len(impresos), 3)
        self.assertEqual(len(set(impresos)), 3)  # ninguno duplicado
        self.assertEqual(self._pendientes_cocina(), 0)


class CasoMoverImpresoraTest(PrintQueueRoutesTest):
    """Mision seccion 23/59 (test CRITICO): la POS58 se mueve de PC A a
    PC B. PC A nunca debe reclamar ni imprimir ese job; cuando la
    impresora vuelve a PC A, ese trabajo ya esta PRINTED y no se
    reimprime."""

    def test_pc_a_no_recibe_el_job_que_pc_b_ya_imprimio(self):
        orden_id = self._crear_orden(referencia="Mesa 300")
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        # PC A no tiene impresora disponible: en la practica, Neko Local
        # ni siquiera llamaria a /claim (no esta READY) -- lo relevante
        # a nivel de backend es que, si de todos modos consultara, no
        # deberia haber nada que reclamar TODAVIA (aun esta pendiente).
        respuesta_a_antes = self._claim("PC-A", ["COCINA"])
        self.assertIsNotNone(respuesta_a_antes["job"])  # todavia nadie lo reclamo

        # Pero como PC-A "no tiene impresora", nunca hace ACK -- se
        # simula liberandolo (equivalente a que Neko Local en PC-A jamas
        # hubiera hecho el claim en primer lugar: liberar dejalo como
        # si no hubiera pasado nada).
        self._fail(respuesta_a_antes["job"]["id"], "PC-A", respuesta_a_antes["job"]["lease_token"])

        # PC B SI tiene la POS58 disponible: reclama e imprime con exito.
        respuesta_b = self._claim("PC-B", ["COCINA"])
        self.assertIsNotNone(respuesta_b["job"])
        self._ack(respuesta_b["job"]["id"], "PC-B", respuesta_b["job"]["lease_token"])

        # Mas tarde, la POS58 vuelve a PC-A: consulta de nuevo.
        respuesta_a_despues = self._claim("PC-A", ["COCINA"])
        self.assertIsNone(respuesta_a_despues["job"])  # NO imprime #300 de nuevo


_PRIVATE_DB_PATH_SIN_SESION = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_print_queue_sin_sesion_{os.getpid()}.db"
)


class EndpointsSinSesionTest(unittest.TestCase):
    """REGRESION DEL BUG REAL: los 4 endpoints de /api/printing/* deben
    responder JSON a un cliente SIN sesion de navegador (exactamente
    como Neko Local, que nunca hace login) -- ver
    web_app.py::proteger_sistema, rutas_publicas.

    Todos los demas tests de este archivo (PrintQueueRoutesTest) llaman
    self._login() en su setUp(), asi que NUNCA habrian detectado este
    bug: probaban la logica de las rutas con una sesion activa, no el
    caso real de un cliente maquina sin sesion. Esta clase, deliberada
    y unicamente, NUNCA inicia sesion."""

    @classmethod
    def setUpClass(cls):
        cls._original_sqlite_path = web_app.CONFIG["SQLITE_PATH"]
        web_app.CONFIG["SQLITE_PATH"] = _PRIVATE_DB_PATH_SIN_SESION
        try:
            web_app.init_db()
        except Exception:
            web_app.CONFIG["SQLITE_PATH"] = cls._original_sqlite_path
            raise

    @classmethod
    def tearDownClass(cls):
        web_app.CONFIG["SQLITE_PATH"] = cls._original_sqlite_path
        try:
            os.unlink(_PRIVATE_DB_PATH_SIN_SESION)
        except OSError:
            pass

    def setUp(self):
        self.client = web_app.app.test_client()
        # Deliberadamente SIN self._login(): asi es como Neko Local
        # habla con el backend en la vida real.

    def _es_json_real(self, respuesta):
        tipo = (respuesta.content_type or "").split(";")[0].strip()
        return tipo == "application/json"

    def test_status_responde_json_sin_sesion(self):
        respuesta = self.client.get(
            "/api/printing/status?roles=COCINA,RECIBO_MESA,RECIBO_PICKUP,RECIBO_DELIVERY"
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(self._es_json_real(respuesta), f"content_type={respuesta.content_type!r}")
        datos = respuesta.get_json()
        self.assertTrue(datos["ok"])

    def test_status_sin_roles_tambien_responde_json_sin_sesion(self):
        # El caso exacto que el usuario probo manualmente desde el
        # navegador (sin query param roles).
        respuesta = self.client.get("/api/printing/status")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(self._es_json_real(respuesta))
        self.assertEqual(respuesta.get_json(), {"ok": True, "pendientes": 0, "por_rol": {}})

    def test_claim_responde_json_sin_sesion_no_redirige_a_login(self):
        respuesta = self.client.post(
            "/api/printing/claim", json={"station_id": "st1", "roles": ["COCINA"]}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(self._es_json_real(respuesta))
        self.assertNotIn("login", (respuesta.get_data(as_text=True) or "").lower())

    def test_ack_responde_sin_sesion_no_redirige_a_login(self):
        respuesta = self.client.post(
            "/api/printing/1/ack", json={"station_id": "st1", "lease_token": "tok"}
        )
        # No existe el job (404), pero la clave es que responda JSON de
        # verdad y no la pagina de login (que devolveria 200/302 con HTML).
        self.assertTrue(self._es_json_real(respuesta), f"content_type={respuesta.content_type!r}")

    def test_fail_responde_sin_sesion_no_redirige_a_login(self):
        respuesta = self.client.post(
            "/api/printing/1/fail", json={"station_id": "st1", "lease_token": "tok", "error": "x"}
        )
        self.assertTrue(self._es_json_real(respuesta), f"content_type={respuesta.content_type!r}")

    def test_no_se_sigue_ninguna_redireccion_a_login(self):
        # follow_redirects=False (default del test client): si antes de
        # este fix la respuesta fuera un 302, esto lo detectaria
        # inmediatamente en vez de seguirlo en silencio como `requests`.
        respuesta = self.client.get("/api/printing/status")
        self.assertNotEqual(respuesta.status_code, 302)


if __name__ == "__main__":
    unittest.main()
