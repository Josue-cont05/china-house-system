"""Design system global de NekoPOS (app.presentation.web.design_system):
tokens oficiales, alias legacy, componentes ds-* y pantallas migradas."""

import os
import re
import tempfile
import unittest

from app.presentation.web.design_system import estilos_design_system
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_design_system_{os.getpid()}.db"
)

TOKENS_OFICIALES = {
    "--bg-main": "#0F1115",
    "--bg-panel": "#161A22",
    "--bg-card": "#1C2230",
    "--bg-hover": "#242C3B",
    "--border": "#2E3747",
    "--text-primary": "#F5F7FA",
    "--text-secondary": "#AAB3C2",
    "--text-muted": "#7D8796",
    "--accent-primary": "#35D07F",
    "--accent-secondary": "#F2B94B",
    "--success": "#35D07F",
    "--warning": "#F2B94B",
    "--danger": "#EF4444",
    "--info": "#4DA3FF",
}


class DesignSystemCssTest(unittest.TestCase):
    def setUp(self):
        self.css = estilos_design_system()

    def test_estilos_base_es_el_design_system(self):
        self.assertEqual(web_app.estilos_base(), self.css)

    def test_tokens_oficiales_con_valores_exactos(self):
        for token, valor in TOKENS_OFICIALES.items():
            with self.subTest(token=token):
                self.assertIn(f"{token}: {valor};", self.css)

    def test_variables_legacy_son_alias_de_tokens(self):
        for legacy, token in (
            ("--panel", "--bg-panel"),
            ("--panel-secundario", "--bg-card"),
            ("--tarjeta", "--bg-card"),
            ("--borde", "--border"),
            ("--texto", "--text-primary"),
            ("--texto-secundario", "--text-secondary"),
            ("--verde-neko", "--accent-primary"),
            ("--naranja", "--accent-secondary"),
            ("--gris-fondo", "--bg-main"),
        ):
            with self.subTest(legacy=legacy):
                self.assertIn(f"{legacy}: var({token});", self.css)

    def test_componentes_comunes_disponibles(self):
        for clase in (
            ".ds-page", ".ds-page-header", ".ds-panel", ".ds-card",
            ".ds-btn", ".ds-btn-primary", ".ds-btn-secondary", ".ds-btn-danger", ".ds-btn-warning",
            ".ds-label", ".ds-segmented", ".ds-table", ".ds-num",
            ".ds-badge-success", ".ds-badge-warning", ".ds-badge-danger", ".ds-badge-info",
            ".ds-alert-success", ".ds-alert-warning", ".ds-alert-danger", ".ds-alert-info",
            ".ds-kpi-grid", ".ds-kpi", ".ds-total", ".ds-tabs", ".ds-tab",
            ".ds-modal", ".ds-modal-actions", ".ds-empty",
        ):
            with self.subTest(clase=clase):
                self.assertRegex(self.css, re.escape(clase) + r"[\s,{:.]")

    def test_foco_visible_y_movimiento_reducido(self):
        self.assertIn(":focus-visible", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_sin_colores_de_tema_claro(self):
        for color in ("#f5f6fa", "#ffffff", "background: white", "#dcfce7", "#fee2e2"):
            self.assertNotIn(color, self.css.lower())


class PantallasMigradasTest(unittest.TestCase):
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
        for table in ("orden_items", "ordenes"):
            cursor.execute(f"DELETE FROM {table}")
        cursor.execute("SELECT id FROM usuarios WHERE rol='master' ORDER BY id LIMIT 1")
        self.master_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        self.client = web_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = self.master_id
            sess["usuario_nombre"] = "Emmanuel"
            sess["usuario_rol"] = "master"

    def _orden(self, estado):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id)
            VALUES (1, '2026-10-11 12:00:00', '2026-10-11', 'Mesa', 'Mesa 1', 'Ana', ?, ?)
            """,
            (estado, self.master_id),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def test_inicio_usa_componentes_del_sistema(self):
        self._orden("abierta")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('class="ds-segmented" id="tipoOrden"', html)
        self.assertEqual(html.count('class="ds-segmented-option"'), 3)
        self.assertIn('<label class="ds-label">', html)
        self.assertIn("ds-btn ds-btn-primary ds-btn-lg ds-btn-block btn-nueva-orden", html)
        self.assertIn('<span class="ds-badge ds-badge-info">Abierta</span>', html)
        self.assertIn("ds-btn ds-btn-secondary btn-ver", html)
        self.assertNotIn("color:#6b7280", html)
        self.assertNotIn('style="background:#f97316', html)

    def test_inicio_sin_ordenes_usa_estado_vacio(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('<div class="ds-empty">Sin órdenes activas</div>', html)

    def test_cierre_de_jornada_usa_modal_y_alertas_del_sistema(self):
        html = self.client.get("/cerrar_jornada").get_data(as_text=True)
        # Sin ordenes cerradas: pantalla de bloqueo con alerta del sistema.
        self.assertIn('class="ds-alert ds-alert-warning"', html)
        self.assertIn("No hay ordenes cerradas para esta jornada", html)
        self.assertNotIn("font-family:Arial", html)

        self._orden("abierta")
        html = self.client.get("/cerrar_jornada").get_data(as_text=True)
        self.assertIn("No se puede cerrar la jornada", html)
        self.assertIn("ds-alert", html)

    def test_cxc_usa_tokens_sin_tema_claro(self):
        html = self.client.get("/cuentas_por_cobrar").get_data(as_text=True)
        estilos_cxc = web_app.estilos_admin_cxc()
        self.assertIn(estilos_cxc, html)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{6}\b", estilos_cxc))
        for viejo in ("#fef3c7", "#dcfce7", "#fee2e2", "#fff7ed"):
            self.assertNotIn(viejo, estilos_cxc)

    def test_orden_no_redefine_la_paleta(self):
        orden_id = self._orden("abierta")
        html = self.client.get(f"/orden/{orden_id}").get_data(as_text=True)
        self.assertNotRegex(html, r"body\.pagina-orden \{\s*--bg-main")
        self.assertIn("--bg-main: #0F1115;", html)

    def _venta_cerrada_y_despachada(self, producto="Neko Combo 3"):
        orden_id = self._orden("cerrada")
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ordenes SET fecha_hora=?, listo_despacho_at=? WHERE id=?",
            (web_app.ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S"), "2026-10-11 13:00:00", orden_id),
        )
        cursor.execute(
            "INSERT INTO orden_items (orden_id, producto, precio, indicacion) VALUES (?, ?, 7.0, '')",
            (orden_id, producto),
        )
        conn.commit()
        conn.close()
        return orden_id

    def test_cierre_del_dia_integrado_al_sistema(self):
        html = self.client.get("/cierre").get_data(as_text=True)
        self.assertIn('id="navMenuBtn"', html)
        self.assertIn('class="titulo titulo-inicio"', html)
        self.assertIn('<h1 class="ds-page-title">📦 Cierre del Día</h1>', html)
        self.assertIn('class="ds-kpi ds-kpi-accent"', html)
        for viejo in ("#f7f5f0", "background: white", "#f0fdf4", "#bbf7d0"):
            self.assertNotIn(viejo, html)
        # Sin ventas: estado informativo, sin boton de cierre.
        self.assertIn('class="ds-alert ds-alert-info cierre-estado"', html)
        self.assertIn('<span class="ds-badge ds-badge-neutral">Sin ventas</span>', html)
        self.assertNotIn('href="/cerrar_jornada"', html.split('id="navDrawer"')[0])

    def test_cierre_del_dia_estado_lista_y_bloqueada(self):
        self._venta_cerrada_y_despachada()
        html = self.client.get("/cierre").get_data(as_text=True)
        self.assertIn('class="ds-alert ds-alert-success cierre-estado"', html)
        self.assertIn("✅ Jornada lista para cierre", html)
        self.assertIn('<span class="ds-badge ds-badge-success">Lista</span>', html)
        self.assertIn('<a href="/cerrar_jornada" class="ds-btn ds-btn-warning ds-btn-lg">', html)

        self._orden("abierta")
        html = self.client.get("/cierre").get_data(as_text=True)
        self.assertIn('class="ds-alert ds-alert-warning cierre-estado"', html)
        self.assertIn('<span class="ds-badge ds-badge-warning">Bloqueada</span>', html)
        self.assertNotIn('class="ds-btn ds-btn-warning ds-btn-lg"', html)

    def test_cierre_del_dia_escapa_nombres(self):
        self._venta_cerrada_y_despachada(producto="<script>alert(1)</script>")
        html = self.client.get("/cierre").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_logo_de_cocina_y_despacho_lleva_al_inicio(self):
        for path in ("/cocina", "/despacho"):
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertRegex(html, r"""<a href=['"]/['"] class="topbar-brand" title="Ir a Inicio">""")


if __name__ == "__main__":
    unittest.main()
