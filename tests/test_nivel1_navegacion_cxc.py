"""Nivel 1: logo del header -> inicio del rol, tipo de orden como
botones (mismos valores de formulario) y descripcion visible en CxC
derivada de la venta origen."""

import os
import re
import tempfile
import unittest

from app.domain.cxc.descripcion import (
    agrupar_productos,
    etiqueta_tipo_orden,
    texto_descripcion_cxc,
    texto_productos,
)
from app.infrastructure.database.clientes import crear_cliente
from app.infrastructure.database.cxc import (
    crear_cuenta_por_cobrar_inicial,
    listar_datos_descripcion_cxc,
)
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_nivel1_{os.getpid()}.db"
)


class DescripcionCxcDominioTest(unittest.TestCase):
    def test_etiqueta_tipo(self):
        self.assertEqual(etiqueta_tipo_orden("Para llevar"), "Pick Up")
        self.assertEqual(etiqueta_tipo_orden("mesa"), "Mesa")
        self.assertEqual(etiqueta_tipo_orden("Delivery"), "Delivery")
        self.assertEqual(etiqueta_tipo_orden("Otro"), "Otro")

    def test_agrupa_y_recorta_productos(self):
        productos = agrupar_productos(["Combo 3", "Cerveza", "Combo 3", "Té", "Postre", " "])
        self.assertEqual(productos, [("Combo 3", 2), ("Cerveza", 1), ("Té", 1), ("Postre", 1)])
        self.assertEqual(texto_productos(productos, 2), "2× Combo 3, 1× Cerveza +2 más")
        self.assertEqual(texto_productos(productos), "2× Combo 3, 1× Cerveza, 1× Té, 1× Postre")

    def test_texto_completo_y_vacio(self):
        texto = texto_descripcion_cxc("Mesa", "Mesa 4", "Cena de cumpleaños", [("Neko Combo 3", 2)])
        self.assertEqual(texto, "Mesa · Mesa 4 — 2× Neko Combo 3 · Obs: Cena de cumpleaños")
        self.assertEqual(texto_descripcion_cxc(None, "-", "-", []), "Sin detalle de la venta")


class Nivel1RoutesTest(unittest.TestCase):
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
        web_app.init_db()
        conn = web_app.get_connection()
        cursor = conn.cursor()
        for table in (
            "cuentas_por_cobrar_movimientos",
            "cuentas_por_cobrar",
            "clientes",
            "orden_items",
            "ordenes",
        ):
            cursor.execute(f"DELETE FROM {table}")
        cursor.execute("SELECT id FROM usuarios WHERE rol='master' ORDER BY id LIMIT 1")
        self.master_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        self.client = web_app.app.test_client()
        self._login("master")

    def _login(self, rol):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = self.master_id
            sess["usuario_nombre"] = "Emmanuel"
            sess["usuario"] = "Emmanuel"
            sess["usuario_rol"] = rol

    # -- Logo -> Inicio --------------------------------------------------
    def test_logo_del_header_lleva_al_inicio(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('<a href="/" class="titulo titulo-inicio"', html)
        self.assertIn('aria-label="Neko Wok POS: ir a Inicio"', html)
        # Es el mismo header compartido en otras pantallas.
        html = self.client.get("/cuentas_por_cobrar").get_data(as_text=True)
        self.assertIn('<a href="/" class="titulo titulo-inicio"', html)

    def test_logo_respeta_el_inicio_de_cada_rol(self):
        self.assertEqual(web_app.ruta_inicio_rol("master"), "/")
        self.assertEqual(web_app.ruta_inicio_rol("mesonera"), "/")
        self.assertEqual(web_app.ruta_inicio_rol("cocina"), "/cocina")
        self.assertEqual(web_app.ruta_inicio_rol("cocina_reportes"), "/cocina")
        self.assertEqual(web_app.ruta_inicio_rol("produccion"), "/produccion")
        # El header compartido apunta al inicio del rol en sesion (cocina
        # no tiene acceso a "/", el login ya la manda a /cocina).
        with web_app.app.test_request_context("/"):
            web_app.session["usuario_id"] = self.master_id
            web_app.g.usuario_rol_actual = "cocina"
            html = web_app.barra_superior()
        self.assertIn('<a href="/cocina" class="titulo titulo-inicio"', html)

    # -- Tipo de orden ---------------------------------------------------
    def _form_nueva_orden(self):
        html = self.client.get("/").get_data(as_text=True)
        inicio = html.index('<form action="/crear_orden" method="post">')
        return html[inicio:html.index("</form>", inicio)]

    def test_tipo_de_orden_son_tres_botones_exclusivos(self):
        form = self._form_nueva_orden()
        self.assertNotIn('<select name="tipo"', form)
        radios = re.findall(r'<input type="radio" name="tipo" value="([^"]+)"( checked)?>', form)
        self.assertEqual([valor for valor, _ in radios], ["Mesa", "Delivery", "Para llevar"])
        # Radios con el mismo name: el navegador garantiza seleccion exclusiva.
        self.assertEqual([marcado for _, marcado in radios], [" checked", "", ""])
        self.assertIn("🪑 Mesa", form)
        self.assertIn("🛵 Delivery", form)
        self.assertIn("🥡 Pick Up", form)
        self.assertIn('role="radiogroup"', form)
        # Campos condicionales de siempre.
        self.assertIn('id="grupoMesaOrden"', form)
        self.assertIn('name="referencia_mesa" id="referenciaMesaOrden" required', form)
        self.assertIn('id="grupoReferenciaOrden" style="display:none;"', form)
        self.assertIn('name="referencia" id="referenciaLibreOrden"', form)

    def test_js_alterna_campos_segun_tipo_elegido(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("""document.querySelector('#tipoOrden input[name="tipo"]:checked')""", html)
        self.assertIn('const esMesa = !elegido || elegido.value === "Mesa";', html)
        self.assertIn("mesaSelect.required = esMesa;", html)
        self.assertIn("referenciaInput.required = !esMesa;", html)

    def _orden_creada(self):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT tipo, referencia, cliente FROM ordenes ORDER BY id DESC LIMIT 1")
        fila = cursor.fetchone()
        conn.close()
        return fila

    def test_cada_boton_envia_el_mismo_valor_que_el_select_anterior(self):
        form = self._form_nueva_orden()
        mesa = re.search(r'<select name="referencia_mesa"[^>]*>\s*<option value="([^"]+)"', form).group(1)

        respuesta = self.client.post(
            "/crear_orden", data={"tipo": "Mesa", "referencia_mesa": mesa, "cliente": "Ana"}
        )
        self.assertEqual(respuesta.status_code, 302)
        tipo, referencia, cliente = self._orden_creada()
        self.assertEqual((tipo, cliente), ("Mesa", "Ana"))
        self.assertTrue(referencia)

        respuesta = self.client.post(
            "/crear_orden", data={"tipo": "Delivery", "referencia": "Av. Bolívar", "cliente": "Luis"}
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self._orden_creada(), ("Delivery", "Av. Bolívar", "Luis"))

        respuesta = self.client.post(
            "/crear_orden", data={"tipo": "Para llevar", "referencia": "0414-555", "cliente": "Eva"}
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self._orden_creada(), ("Para llevar", "0414-555", "Eva"))

    # -- CxC ---------------------------------------------------------------
    def _venta_a_credito(self, tipo="Mesa", referencia="Mesa 4", observacion="Cena de equipo"):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, observacion, usuario_id)
            VALUES (315, '2026-10-10 20:00:00', '2026-10-10', ?, ?, 'Carlos', 'cerrada', ?, ?)
            """,
            (tipo, referencia, observacion, self.master_id),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        for producto, precio in (("Neko Combo 3", 7.0), ("Neko Combo 3", 7.0), ("Cerveza Polar", 2.5)):
            cursor.execute(
                "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, ?, '')",
                (orden_id, producto, precio),
            )
        cliente_id = crear_cliente(
            cursor, "Carlos", "0414", "V-1", "", 1, "2026-10-10 20:00:00", web_app.obtener_ultimo_id
        )
        cuenta_id = crear_cuenta_por_cobrar_inicial(
            cursor, orden_id, cliente_id, "Carlos", 16.5, "2026-10-10 20:05:00",
            self.master_id, web_app.obtener_ultimo_id,
        )
        conn.commit()
        conn.close()
        return orden_id, cliente_id, cuenta_id

    def test_repositorio_lee_datos_de_la_venta_origen(self):
        orden_id, _cliente_id, _cuenta_id = self._venta_a_credito()
        conn = web_app.get_connection()
        datos = listar_datos_descripcion_cxc(conn.cursor(), [orden_id, None, 999999])
        conn.close()
        self.assertEqual(set(datos), {orden_id})
        self.assertEqual(datos[orden_id]["tipo"], "Mesa")
        self.assertEqual(datos[orden_id]["referencia"], "Mesa 4")
        self.assertEqual(datos[orden_id]["observacion"], "Cena de equipo")
        self.assertEqual(datos[orden_id]["productos"], ["Neko Combo 3", "Neko Combo 3", "Cerveza Polar"])

    def test_listado_de_cxc_muestra_descripcion(self):
        self._venta_a_credito()
        html = self.client.get("/cuentas_por_cobrar").get_data(as_text=True)
        self.assertIn("<th>Descripción</th>", html)
        self.assertIn(
            '<td class="descripcion-cxc">Mesa · Mesa 4 — 2× Neko Combo 3, 1× Cerveza Polar · Obs: Cena de equipo</td>',
            html,
        )
        self.assertIn("#315", html)
        self.assertIn("$ 16.50", html)

    def test_detalle_de_cliente_y_pago_masivo_muestran_descripcion(self):
        _orden_id, cliente_id, _cuenta_id = self._venta_a_credito(tipo="Para llevar", referencia="Carlos", observacion="")
        esperado = '<td class="descripcion-cxc">Pick Up · Carlos — 2× Neko Combo 3, 1× Cerveza Polar</td>'
        html = self.client.get(f"/cuentas_por_cobrar/clientes/{cliente_id}").get_data(as_text=True)
        self.assertIn(esperado, html)
        html = self.client.get(f"/cuentas_por_cobrar/clientes/{cliente_id}/pago_masivo").get_data(as_text=True)
        self.assertIn(esperado, html)
        self.assertIn('name="cuenta_seleccionada"', html)

    def test_detalle_de_cuenta_muestra_descripcion_y_venta_origen(self):
        _orden_id, _cliente_id, cuenta_id = self._venta_a_credito()
        html = self.client.get(f"/cuentas_por_cobrar/{cuenta_id}").get_data(as_text=True)
        self.assertIn('class="descripcion-cxc-destacada"', html)
        self.assertIn("Mesa · Mesa 4 — 2× Neko Combo 3, 1× Cerveza Polar · Obs: Cena de equipo", html)
        self.assertIn("<b>Tipo:</b> Mesa · Mesa 4", html)
        self.assertIn("<b>Productos:</b> 2× Neko Combo 3, 1× Cerveza Polar", html)
        self.assertIn("<b>Observación de la orden:</b> Cena de equipo", html)
        # Calculos intactos.
        self.assertIn("<b>Saldo pendiente:</b> $ 16.50", html)

    def test_descripcion_escapa_html(self):
        self._venta_a_credito(referencia="<b>Mesa</b>", observacion='<script>x</script>')
        html = self.client.get("/cuentas_por_cobrar").get_data(as_text=True)
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)


if __name__ == "__main__":
    unittest.main()
