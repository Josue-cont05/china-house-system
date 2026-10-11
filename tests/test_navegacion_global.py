"""Navegacion global (boton Menu + drawer) y simplificacion de Inicio.

La navegacion SOLO refleja permisos: las opciones de cada rol son las
mismas que pintaba antes index() (menu_links) y proteger_sistema() sigue
bloqueando en backend aunque se escriba la URL a mano."""

import os
import re
import tempfile
import unittest

from app.presentation.web.navigation import claves_navegacion_rol
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_navegacion_global_{os.getpid()}.db"
)

# Opciones que index() mostraba a cada rol ANTES de este cambio
# (copiado del antiguo bloque `menu_links`), ademas de "Inicio".
OPCIONES_MASTER = [
    "/cambiar_tasa", "/exportar", "/cierre", "/reportes", "/dashboard", "/cerrar_jornada",
    "/menu", "/inventario", "/compras", "/produccion", "/recetas", "/movimientos_inventario",
    "/usuarios", "/cocina", "/cuentas_por_cobrar", "/delivery", "/despacho",
]


def _hrefs_drawer(html):
    inicio = html.index('<nav class="ds-drawer" id="navDrawer"')
    fin = html.index("</nav>", inicio)
    return re.findall(r'class="ds-nav-item(?: activo)?" href="([^"]+)"', html[inicio:fin])


class ClavesNavegacionRolTest(unittest.TestCase):
    def test_mismas_reglas_que_el_menu_anterior_de_inicio(self):
        self.assertEqual(
            claves_navegacion_rol("master", True),
            ["inicio", "tasa", "exportar", "cierre", "reportes", "dashboard", "cerrar_jornada",
             "menu", "inventario", "compras", "produccion", "recetas", "movimientos",
             "usuarios", "cocina", "cxc", "delivery", "despacho"],
        )
        self.assertEqual(claves_navegacion_rol("mesonera", True), ["inicio", "despacho"])
        self.assertEqual(claves_navegacion_rol("socio", True), ["inicio", "reportes", "dashboard", "despacho"])
        self.assertEqual(
            claves_navegacion_rol("mesonera_reportes", True), ["inicio", "reportes", "dashboard", "despacho"]
        )
        self.assertEqual(
            claves_navegacion_rol("cocina_reportes", False),
            ["inicio", "cocina", "produccion", "inventario", "reportes", "dashboard"],
        )
        self.assertEqual(claves_navegacion_rol("cocina", False), ["inicio"])
        self.assertEqual(claves_navegacion_rol("produccion", False), ["inicio"])


class NavegacionGlobalRoutesTest(unittest.TestCase):
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
        self.client = web_app.app.test_client()

    def _login(self, rol):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE rol=? ORDER BY id LIMIT 1", (rol,))
        fila = cursor.fetchone()
        if fila:
            usuario_id = fila[0]
        else:
            cursor.execute(
                "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)",
                (f"Usuario {rol}", f"9{len(rol)}{abs(hash(rol)) % 1000}", rol),
            )
            usuario_id = web_app.obtener_ultimo_id(cursor, "usuarios")
            conn.commit()
        conn.close()
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = usuario_id
            sess["usuario_nombre"] = f"Usuario {rol}"
            sess["usuario"] = f"Usuario {rol}"
            sess["usuario_rol"] = rol

    def _html(self, path):
        respuesta = self.client.get(path)
        self.assertEqual(respuesta.status_code, 200, path)
        return respuesta.get_data(as_text=True)

    def test_header_tiene_un_unico_boton_menu_y_drawer_cerrado(self):
        self._login("master")
        html = self._html("/")
        self.assertEqual(html.count('id="navMenuBtn"'), 1)
        self.assertIn('aria-controls="navDrawer" aria-expanded="false"', html)
        self.assertIn('<nav class="ds-drawer" id="navDrawer" aria-label="Menú principal" aria-hidden="true">', html)
        self.assertIn('id="navCerrar" aria-label="Cerrar menú"', html)
        self.assertIn('id="navBackdrop"', html)
        # Ya no hay fila de botones administrativos en el header.
        self.assertNotIn('class="menu-top"', html)
        # El logo sigue llevando al inicio del rol.
        self.assertIn('<a href="/" class="titulo titulo-inicio"', html)

    def test_master_ve_todas_sus_opciones_agrupadas(self):
        self._login("master")
        html = self._html("/")
        hrefs = _hrefs_drawer(html)
        self.assertEqual(sorted(hrefs), sorted(["/"] + OPCIONES_MASTER + ["/logout"]))
        for grupo in ("Operación", "Caja y cobros", "Reportes", "Administración", "Sesión"):
            self.assertIn(f'<div class="ds-nav-group-title">{grupo}</div>', html)
        # Pagina actual marcada.
        self.assertIn('<a class="ds-nav-item activo" href="/" aria-current="page">', html)

    def test_inicio_sin_accesos_rapidos_y_operacion_primero(self):
        self._login("master")
        html = self._html("/")
        self.assertNotIn("Accesos rápidos", html)
        self.assertNotIn('class="menu-card"', html)
        self.assertNotIn('class="menu-master"', html)
        nueva = html.index('class="panel-izq inicio-nueva-orden"')
        ordenes = html.index('class="panel-der inicio-ordenes"')
        secundario = html.index('class="inicio-secundario"')
        # En el DOM (y por tanto en movil): nueva orden -> acciones secundarias -> ordenes;
        # el grid CSS coloca las ordenes antes que las acciones secundarias en movil.
        self.assertLess(nueva, ordenes)
        self.assertLess(nueva, secundario)
        self.assertIn('grid-template-areas: "nueva" "ordenes" "secundario";', html)
        # Los controles operativos existentes se preservan.
        self.assertIn('href="/cerrar_jornada" class="btn-cierre-jornada ', html)
        self.assertIn('href="/ordenes_listas" class="btn-cierre-jornada ', html)

    def test_mesonera_no_recibe_opciones_de_master(self):
        self._login("mesonera")
        html = self._html("/")
        self.assertEqual(_hrefs_drawer(html), ["/", "/despacho", "/logout"])
        for ruta in ("/usuarios", "/cerrar_jornada", "/menu", "/reportes", "/cambiar_tasa", "/exportar"):
            self.assertNotIn(f'class="ds-nav-item" href="{ruta}"', html)
        self.assertNotIn('class="inicio-secundario"', html)

    def test_ocultar_opciones_no_sustituye_los_controles_backend(self):
        self._login("mesonera")
        for ruta in ("/usuarios", "/cerrar_jornada", "/menu", "/exportar", "/recetas"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)
        self.assertEqual(self.client.post("/cerrar_jornada", data={"confirmar": "1"}).status_code, 403)

    def test_cocina_ve_solo_navegacion_compatible(self):
        self._login("cocina")
        with web_app.app.test_request_context("/cocina"):
            web_app.session["usuario_id"] = 1
            web_app.g.usuario_rol_actual = "cocina"
            html = web_app.barra_superior()
        self.assertEqual(_hrefs_drawer(html), ["/cocina", "/logout"])
        self.assertIn('<a href="/cocina" class="titulo titulo-inicio"', html)
        # Backend: cocina sigue sin acceso al Inicio de toma de ordenes.
        self.assertEqual(self.client.get("/").status_code, 403)

    def test_cocina_reportes_ve_sus_opciones(self):
        with web_app.app.test_request_context("/cocina"):
            web_app.session["usuario_id"] = 1
            web_app.g.usuario_rol_actual = "cocina_reportes"
            html = web_app.barra_superior()
        self.assertEqual(
            sorted(_hrefs_drawer(html)),
            sorted(["/cocina", "/produccion", "/inventario", "/reportes", "/dashboard", "/logout"]),
        )

    def test_produccion_ve_solo_navegacion_compatible(self):
        self._login("produccion")
        html = self._html("/produccion")
        self.assertEqual(_hrefs_drawer(html), ["/produccion", "/logout"])
        self.assertIn('<a href="/produccion" class="titulo titulo-inicio"', html)
        respuesta = self.client.get("/usuarios")
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers["Location"].endswith("/produccion"))

    def test_enlaces_contextuales_van_al_drawer_sin_duplicar(self):
        # Mismos enlaces contextuales que pasa el formulario de abono de CxC.
        with web_app.app.test_request_context("/cuentas_por_cobrar/clientes"):
            web_app.session["usuario_id"] = 1
            web_app.g.usuario_rol_actual = "master"
            html = web_app.barra_superior(
                '<a href="/cuentas_por_cobrar">Cuentas</a>'
                '<a href="/cuentas_por_cobrar/clientes">Cartera de clientes</a><a href="/">Inicio</a>'
            )
        self.assertIn('<div class="ds-nav-group-title">En esta pantalla</div>', html)
        hrefs = _hrefs_drawer(html)
        self.assertEqual(hrefs.count("/cuentas_por_cobrar/clientes"), 1)
        self.assertEqual(hrefs.count("/cuentas_por_cobrar"), 1)
        self.assertEqual(hrefs.count("/"), 1)
        # Solo la opcion mas especifica queda marcada como actual.
        self.assertEqual(html.count('aria-current="page"'), 1)
        self.assertIn('class="ds-nav-item activo" href="/cuentas_por_cobrar/clientes" aria-current="page"', html)

    def test_cocina_reportes_sin_opciones_duplicadas(self):
        with web_app.app.test_request_context("/cocina"):
            web_app.session["usuario_id"] = 1
            web_app.g.usuario_rol_actual = "cocina_reportes"
            html = web_app.barra_superior()
        hrefs = _hrefs_drawer(html)
        self.assertEqual(len(hrefs), len(set(hrefs)))

    def test_rutas_de_la_navegacion_existen(self):
        reglas = {regla.rule for regla in web_app.app.url_map.iter_rules()}
        for ruta in OPCIONES_MASTER + ["/", "/logout"]:
            with self.subTest(ruta=ruta):
                self.assertIn(ruta, reglas)


if __name__ == "__main__":
    unittest.main()
