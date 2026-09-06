"""Tests del motor general de notificaciones (mision "engine general de
notificaciones" + Mesa + Pick Up + Delivery): campana global, LISTO PARA
RETIRAR avisando al responsable real (nunca nombres hardcodeados), y
asignacion de conductor de Delivery (interno/NEEDS_DRIVER/externo)."""

import os
import tempfile
import unittest

from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_notifications_{os.getpid()}.db"
)


class NotificationsTestBase(unittest.TestCase):
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

    def _conn(self):
        return web_app.get_connection()

    def _clear_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in (
            "notifications",
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
            "usuarios",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _crear_usuario(self, nombre, rol="mesonera", conductor=False, conductor_default=False, coordinador=False):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usuarios (
                nombre, pin, rol, activo, es_conductor_delivery,
                es_conductor_delivery_default, es_coordinador_delivery
            )
            VALUES (?, '0000', ?, 1, ?, ?, ?)
            """,
            (nombre, rol, int(conductor), int(conductor_default), int(coordinador)),
        )
        usuario_id = web_app.obtener_ultimo_id(cursor, "usuarios")
        conn.commit()
        conn.close()
        return usuario_id

    def _login(self, usuario_id, nombre, rol="mesonera"):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = usuario_id
            sess["usuario_nombre"] = nombre
            sess["usuario"] = nombre
            sess["usuario_rol"] = rol

    def _crear_orden(self, tipo="Mesa", referencia="Mesa 4", usuario_id=None, **campos):
        conn = self._conn()
        cursor = conn.cursor()
        columnas = dict(
            numero_orden=None, fecha_hora="2026-09-05 19:12:00", fecha="2026-09-05",
            tipo=tipo, referencia=referencia, cliente="Cliente", estado="abierta",
            usuario_id=usuario_id,
        )
        columnas.update(campos)
        nombres = ",".join(columnas.keys())
        placeholders = ",".join("?" for _ in columnas)
        cursor.execute(f"INSERT INTO ordenes ({nombres}) VALUES ({placeholders})", tuple(columnas.values()))
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _agregar_item(self, orden_id, producto="Arroz Frito", precio=5.0):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, '')",
            (orden_id, producto, precio),
        )
        conn.commit()
        conn.close()

    def _notificaciones_de(self, usuario_id):
        repo = web_app.SqlNotificationsRepository(web_app.get_connection)
        return repo.listar_para_usuario(usuario_id)

    def _marcar_listo(self, orden_id):
        return self.client.post(f"/despacho/{orden_id}/entregado")


class CampanaApiTest(NotificationsTestBase):
    def test_usuario_ve_solo_sus_notificaciones(self):
        usuario_a = self._crear_usuario("Sara")
        usuario_b = self._crear_usuario("Julissa")
        web_app._crear_notificacion("evt-a", usuario_a, "TEST", "Para A", "mensaje a")
        web_app._crear_notificacion("evt-b", usuario_b, "TEST", "Para B", "mensaje b")

        self._login(usuario_a, "Sara")
        respuesta = self.client.get("/api/notificaciones").get_json()

        self.assertEqual(len(respuesta["notificaciones"]), 1)
        self.assertEqual(respuesta["notificaciones"][0]["titulo"], "Para A")
        self.assertEqual(respuesta["no_leidas"], 1)

    def test_no_autenticado_redirige_a_login(self):
        # El guard global before_request (proteger_sistema) intercepta
        # ANTES de llegar a la ruta y redirige a /login -- el chequeo
        # 401 dentro de la ruta es defensa adicional para llamadas que
        # sí llegan sin sesion (p.ej. sesion borrada a mitad de request).
        respuesta = self.client.get("/api/notificaciones")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/login", respuesta.headers["Location"])

    def test_marcar_leida_es_idempotente_y_respeta_ownership(self):
        usuario_a = self._crear_usuario("Sara")
        usuario_b = self._crear_usuario("Julissa")
        web_app._crear_notificacion("evt-a", usuario_a, "TEST", "Para A", "mensaje a")

        self._login(usuario_b, "Julissa")
        notif_id = self._notificaciones_de(usuario_a)[0]["id"]
        self.client.post(f"/api/notificaciones/{notif_id}/leer")
        self.assertFalse(self._notificaciones_de(usuario_a)[0]["leida"])  # B no pudo marcar la de A

        self._login(usuario_a, "Sara")
        self.client.post(f"/api/notificaciones/{notif_id}/leer")
        self.client.post(f"/api/notificaciones/{notif_id}/leer")  # doble click
        self.assertTrue(self._notificaciones_de(usuario_a)[0]["leida"])

    def test_marcar_todas_leidas(self):
        usuario_a = self._crear_usuario("Sara")
        web_app._crear_notificacion("evt-1", usuario_a, "TEST", "T1", "m1")
        web_app._crear_notificacion("evt-2", usuario_a, "TEST", "T2", "m2")

        self._login(usuario_a, "Sara")
        self.client.post("/api/notificaciones/leer_todas")

        self.assertTrue(all(n["leida"] for n in self._notificaciones_de(usuario_a)))

    def test_event_key_evita_duplicados(self):
        usuario_a = self._crear_usuario("Sara")
        creada_1 = web_app._crear_notificacion("evt-unico", usuario_a, "TEST", "T", "m")
        creada_2 = web_app._crear_notificacion("evt-unico", usuario_a, "TEST", "T", "m")

        self.assertTrue(creada_1)
        self.assertFalse(creada_2)
        self.assertEqual(len(self._notificaciones_de(usuario_a)), 1)


class MesaNotificationTest(NotificationsTestBase):
    def test_mesa_lista_notifica_solo_al_responsable_real(self):
        sara = self._crear_usuario("Sara")
        otro = self._crear_usuario("Julissa")
        orden_id = self._crear_orden(tipo="Mesa", referencia="Mesa 4", usuario_id=sara)
        self._agregar_item(orden_id)
        self._login(otro, "Julissa")  # Monica/otra mesonera opera Despacho, no necesariamente Sara
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self._marcar_listo(orden_id)

        self.assertEqual(respuesta.get_json(), {"ok": True})
        notifs_sara = self._notificaciones_de(sara)
        self.assertEqual(len(notifs_sara), 1)
        self.assertIn("Mesa 4", notifs_sara[0]["titulo"])
        self.assertIn("PEDIDO LISTO", notifs_sara[0]["titulo"])
        self.assertNotIn("entregado", notifs_sara[0]["mensaje"].lower())
        self.assertIn("retir", notifs_sara[0]["mensaje"].lower())
        self.assertEqual(self._notificaciones_de(otro), [])

    def test_doble_click_no_duplica_notificacion(self):
        sara = self._crear_usuario("Sara")
        monica = self._crear_usuario("Monica2")
        orden_id = self._crear_orden(tipo="Mesa", referencia="Mesa 4", usuario_id=sara)
        self._agregar_item(orden_id)
        self._login(monica, "Monica2")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_listo(orden_id)
        self._marcar_listo(orden_id)

        self.assertEqual(len(self._notificaciones_de(sara)), 1)

    def test_sin_responsable_no_falla_la_ruta(self):
        monica = self._crear_usuario("Monica3")
        orden_id = self._crear_orden(tipo="Mesa", referencia="Mesa 9", usuario_id=None)
        self._agregar_item(orden_id)
        self._login(monica, "Monica3")
        self.client.get(f"/enviar_cocina/{orden_id}")

        respuesta = self._marcar_listo(orden_id)

        self.assertEqual(respuesta.status_code, 200)


class PickUpNotificationTest(NotificationsTestBase):
    def test_pickup_listo_notifica_a_quien_creo_la_orden(self):
        gaby = self._crear_usuario("Gaby")
        monica = self._crear_usuario("Monica4")
        orden_id = self._crear_orden(tipo="Para llevar", referencia="Carlos", usuario_id=gaby)
        self._agregar_item(orden_id)
        self._login(monica, "Monica4")
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_listo(orden_id)

        notifs = self._notificaciones_de(gaby)
        self.assertEqual(len(notifs), 1)
        self.assertIn("PICK UP", notifs[0]["titulo"])
        self.assertIn("avisarle al cliente", notifs[0]["mensaje"].lower())
        self.assertNotIn("entregado", notifs[0]["mensaje"].lower())


class DeliveryNotificationTest(NotificationsTestBase):
    def _crear_delivery(self, choice, cliente="Maria"):
        return self.client.post(
            "/crear_orden",
            data={
                "tipo": "Delivery",
                "referencia": "Calle 5",
                "cliente": cliente,
                "delivery_driver_choice": choice,
            },
            follow_redirects=False,
        )

    def test_delivery_asignado_a_conductor_interno_notifica_de_inmediato(self):
        josue = self._crear_usuario("Josue", conductor=True, conductor_default=True)
        gaby = self._crear_usuario("Gaby")
        self._login(gaby, "Gaby")

        respuesta = self._crear_delivery("default")

        self.assertEqual(respuesta.status_code, 302)
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT delivery_driver_user_id, delivery_driver_status FROM ordenes WHERE id=?",
            (orden_id,),
        )
        driver_id, status = cursor.fetchone()
        conn.close()
        self.assertEqual(driver_id, josue)
        self.assertEqual(status, "ASSIGNED_INTERNAL")

        notifs = self._notificaciones_de(josue)
        self.assertEqual(len(notifs), 1)
        self.assertIn("ASIGNADO", notifs[0]["titulo"])

    def test_delivery_sin_conductor_notifica_a_coordinadores(self):
        monica = self._crear_usuario("Monica", coordinador=True)
        gaby_coord = self._crear_usuario("Gaby", coordinador=True)
        josue = self._crear_usuario("Josue", conductor=True, conductor_default=True)
        gaby_mesonera = self._crear_usuario("GabyMesonera")
        self._login(gaby_mesonera, "GabyMesonera")

        respuesta = self._crear_delivery("needs_driver")
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])

        self.assertEqual(len(self._notificaciones_de(monica)), 1)
        self.assertEqual(len(self._notificaciones_de(gaby_coord)), 1)
        self.assertEqual(self._notificaciones_de(josue), [])  # conductor default NO recibe si no fue asignado

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT delivery_driver_status FROM ordenes WHERE id=?", (orden_id,))
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "NEEDS_DRIVER")

    def test_leer_notificacion_needs_driver_no_resuelve_el_estado(self):
        monica = self._crear_usuario("Monica", coordinador=True)
        self._login(monica, "Monica")
        respuesta = self._crear_delivery("needs_driver")
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])

        notif_id = self._notificaciones_de(monica)[0]["id"]
        self.client.post(f"/api/notificaciones/{notif_id}/leer")

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT delivery_driver_status FROM ordenes WHERE id=?", (orden_id,))
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "NEEDS_DRIVER")

    def test_asignacion_posterior_interna_notifica_y_cambia_estado(self):
        monica = self._crear_usuario("Monica", coordinador=True)
        josue = self._crear_usuario("Josue", conductor=True)
        self._login(monica, "Monica")
        respuesta = self._crear_delivery("needs_driver")
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])

        asignar = self.client.post(
            f"/orden/{orden_id}/delivery_conductor",
            data={"modo": "interno", "conductor_user_id": str(josue)},
            follow_redirects=False,
        )

        self.assertEqual(asignar.status_code, 302)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT delivery_driver_user_id, delivery_driver_status FROM ordenes WHERE id=?", (orden_id,))
        driver_id, status = cursor.fetchone()
        conn.close()
        self.assertEqual(driver_id, josue)
        self.assertEqual(status, "ASSIGNED_INTERNAL")
        self.assertEqual(len(self._notificaciones_de(josue)), 1)

    def test_asignacion_posterior_externa_no_requiere_usuario(self):
        monica = self._crear_usuario("Monica", coordinador=True)
        self._login(monica, "Monica")
        respuesta = self._crear_delivery("needs_driver")
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])

        asignar = self.client.post(
            f"/orden/{orden_id}/delivery_conductor",
            data={"modo": "externo"},
            follow_redirects=False,
        )

        self.assertEqual(asignar.status_code, 302)
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT delivery_driver_user_id, delivery_driver_status FROM ordenes WHERE id=?", (orden_id,))
        driver_id, status = cursor.fetchone()
        conn.close()
        self.assertIsNone(driver_id)
        self.assertEqual(status, "EXTERNAL")

    def test_delivery_listo_notifica_al_conductor_asignado(self):
        josue = self._crear_usuario("Josue", conductor=True, conductor_default=True)
        self._login(josue, "Josue")
        respuesta = self._crear_delivery("default")
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        self._marcar_listo(orden_id)

        notifs = self._notificaciones_de(josue)
        self.assertEqual(len(notifs), 2)  # asignado + listo
        titulos = [n["titulo"] for n in notifs]
        self.assertTrue(any("LISTO" in t for t in titulos))

    def test_delivery_needs_driver_listo_no_notifica_a_nadie_erroneamente(self):
        monica = self._crear_usuario("Monica", coordinador=True)
        self._login(monica, "Monica")
        respuesta = self._crear_delivery("needs_driver")
        orden_id = int(respuesta.headers["Location"].rsplit("/", 1)[-1])
        self._agregar_item(orden_id)
        self.client.get(f"/enviar_cocina/{orden_id}")

        notifs_antes = len(self._notificaciones_de(monica))
        self._marcar_listo(orden_id)

        # No revienta, y no se le atribuye el delivery a nadie que no fue asignado.
        self.assertEqual(len(self._notificaciones_de(monica)), notifs_antes)


class UsuariosDeliveryFlagsTest(NotificationsTestBase):
    def _flags(self, usuario_id):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT es_conductor_delivery, es_conductor_delivery_default, es_coordinador_delivery FROM usuarios WHERE id=?",
            (usuario_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def test_solo_master_puede_alternar_flags(self):
        mesonera = self._crear_usuario("Mesonera1", rol="mesonera")
        josue = self._crear_usuario("Josue")
        self._login(mesonera, "Mesonera1", rol="mesonera")

        respuesta = self.client.post(f"/usuarios/{josue}/delivery_flags", data={"flag": "conductor"})

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self._flags(josue), (0, 0, 0))

    def test_master_alterna_flag_conductor(self):
        master = self._crear_usuario("Emmanuel", rol="master")
        josue = self._crear_usuario("Josue")
        self._login(master, "Emmanuel", rol="master")

        self.client.post(f"/usuarios/{josue}/delivery_flags", data={"flag": "conductor"})
        self.assertEqual(self._flags(josue), (1, 0, 0))

        self.client.post(f"/usuarios/{josue}/delivery_flags", data={"flag": "conductor"})
        self.assertEqual(self._flags(josue), (0, 0, 0))

    def test_conductor_por_defecto_es_unico(self):
        master = self._crear_usuario("Emmanuel", rol="master")
        josue = self._crear_usuario("Josue")
        ismaldo = self._crear_usuario("Ismaldo")
        self._login(master, "Emmanuel", rol="master")

        self.client.post(f"/usuarios/{josue}/delivery_flags", data={"flag": "conductor_default"})
        self.assertEqual(self._flags(josue)[1], 1)

        self.client.post(f"/usuarios/{ismaldo}/delivery_flags", data={"flag": "conductor_default"})

        self.assertEqual(self._flags(josue)[1], 0)
        self.assertEqual(self._flags(ismaldo)[1], 1)


if __name__ == "__main__":
    unittest.main()
