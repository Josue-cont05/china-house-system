"""Rediseno UX de /orden/<id>: catalogo por categorias, tarjetas con
cantidad, imagen/placeholder, estado agotado derivado de modificadores
y resumen agrupado. Verifica el contrato HTML que usa el
JS de agregado (clases/data-*) y que el backend de agregado no cambio."""

import os
import re
import tempfile
import unittest

from app.domain.sales.item_builder import MAX_CANTIDAD_ITEM
from app.domain.sales.modifiers import (
    GrupoModificador,
    OpcionModificador,
    producto_agotado_por_modificadores,
)
from app.infrastructure.database import modifiers as modifiers_db
from app.presentation.web.order_detail_view import estilo_categoria_pos
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_order_detail_redesign_{os.getpid()}.db"
)


def _opcion(nombre, disponible=True, activa=True):
    return OpcionModificador(
        id=1, nombre=nombre, activa=activa, disponible=disponible, precio_adicional=0.0, orden=0
    )


def _grupo(opciones, obligatorio=True, minimo=1, activo=True):
    return GrupoModificador(
        id=1,
        nombre="Sabor",
        activo=activo,
        obligatorio=obligatorio,
        seleccion_multiple=False,
        minimo=minimo,
        maximo=1,
        orden=0,
        opciones=tuple(opciones),
    )


class ProductoAgotadoTest(unittest.TestCase):
    def test_grupo_obligatorio_sin_opciones_disponibles_agota_el_producto(self):
        grupos = [_grupo([_opcion("Mora", disponible=False), _opcion("Fresa", disponible=False)])]
        self.assertTrue(producto_agotado_por_modificadores(grupos))

    def test_una_opcion_disponible_basta(self):
        grupos = [_grupo([_opcion("Mora", disponible=False), _opcion("Fresa")])]
        self.assertFalse(producto_agotado_por_modificadores(grupos))

    def test_grupo_opcional_o_inactivo_no_agota(self):
        sin_opciones = [_opcion("Mora", disponible=False)]
        self.assertFalse(producto_agotado_por_modificadores([_grupo(sin_opciones, obligatorio=False)]))
        self.assertFalse(producto_agotado_por_modificadores([_grupo(sin_opciones, minimo=0)]))
        self.assertFalse(producto_agotado_por_modificadores([_grupo(sin_opciones, activo=False)]))
        self.assertFalse(producto_agotado_por_modificadores([]))


class EstiloCategoriaTest(unittest.TestCase):
    def test_colores_por_palabra_clave_con_fallback_neutro(self):
        self.assertEqual(estilo_categoria_pos("Neko Combos")[0], "#35D07F")
        self.assertEqual(estilo_categoria_pos("Promociones Neko")[0], "#FF8A4C")
        self.assertEqual(estilo_categoria_pos("Neko Dúo")[0], "#4DA3FF")
        self.assertEqual(estilo_categoria_pos("Cervezas")[0], "#F2B94B")
        self.assertEqual(estilo_categoria_pos("Bebidas")[0], "#5BC0EB")
        self.assertEqual(estilo_categoria_pos("Extras")[0], "#A78BFA")
        self.assertEqual(estilo_categoria_pos("Postres")[0], "#F472B6")
        self.assertEqual(estilo_categoria_pos("Categoria Rara")[0], "#94A3B8")


class OrderDetailRedesignRouteTest(unittest.TestCase):
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
            "orden_items",
            "ordenes",
            "producto_grupos_modificadores",
            "opciones_modificador",
            "grupos_modificadores",
            "productos",
            "categorias",
        ):
            cursor.execute(f"DELETE FROM {table}")
        cursor.execute("SELECT id FROM usuarios WHERE rol='master' ORDER BY id LIMIT 1")
        self.master_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        self.client = web_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = self.master_id
            sess["usuario_nombre"] = "Emmanuel"
            sess["usuario"] = "Emmanuel"
            sess["usuario_rol"] = "master"

    # -- helpers ---------------------------------------------------------
    def _producto(self, nombre, precio, categoria, imagen_url=None):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM categorias WHERE nombre=?", (categoria,))
        fila = cursor.fetchone()
        if fila:
            categoria_id = fila[0]
        else:
            cursor.execute("INSERT INTO categorias (nombre, activo) VALUES (?, 1)", (categoria,))
            categoria_id = web_app.obtener_ultimo_id(cursor, "categorias")
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id, activo, imagen_url) VALUES (?, ?, ?, 1, ?)",
            (nombre, precio, categoria_id, imagen_url),
        )
        producto_id = web_app.obtener_ultimo_id(cursor, "productos")
        conn.commit()
        conn.close()
        return producto_id

    def _orden(self, estado="abierta"):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (7, "2026-10-11 12:00:00", "2026-10-11", "mesa", "Mesa 2", "Cliente", estado, self.master_id),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _grupo_sabor(self, producto_id, disponibles):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        grupo_id = modifiers_db.crear_grupo_modificador(cursor, web_app.obtener_ultimo_id, nombre="Sabor")
        for nombre, disponible in disponibles:
            opcion_id = modifiers_db.crear_opcion_modificador(
                cursor, web_app.obtener_ultimo_id, grupo_id=grupo_id, nombre=nombre
            )
            if not disponible:
                cursor.execute("UPDATE opciones_modificador SET disponible=0 WHERE id=?", (opcion_id,))
        modifiers_db.asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        conn.commit()
        conn.close()
        return grupo_id

    def _tarjeta(self, html, producto_id):
        match = re.search(
            rf'<article class="([^"]*)"[^>]*data-producto-id="{producto_id}">(.*?)</article>',
            html,
            re.S,
        )
        self.assertIsNotNone(match, f"no se encontro la tarjeta del producto {producto_id}")
        return match.group(1), match.group(2)

    def _html(self, orden_id):
        response = self.client.get(f"/orden/{orden_id}")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    # -- tests -----------------------------------------------------------
    def test_categorias_se_renderizan_como_secciones_y_chips_en_orden_pos(self):
        self._producto("Cerveza Polar", 2.5, "Cervezas")
        self._producto("Neko Combo 1", 5.3, "Neko Combos")
        self._producto("Refresco 1 Lt", 1.2, "Bebidas")
        html = self._html(self._orden())

        self.assertIn('id="buscarProducto"', html)
        self.assertIn('placeholder="Buscar producto..."', html)
        self.assertIn('id="btnVerOrden"', html)
        secciones = re.findall(r'<section class="cat-seccion" id="([^"]+)"', html)
        # Neko Combos y Bebidas siguen ORDEN_CATEGORIAS_POS; Cervezas (fuera de la lista) va al final.
        self.assertEqual(secciones, ["cat-neko-combos", "cat-bebidas", "cat-cervezas"])
        chips = re.findall(r'<a class="cat-chip" href="#([^"]+)" data-target="([^"]+)"', html)
        self.assertEqual([c[0] for c in chips], secciones)
        self.assertEqual([c[1] for c in chips], secciones)
        self.assertIn("--cat:#F2B94B", html)

    def test_tarjeta_simple_tiene_cantidad_integrada_y_contrato_de_agregado(self):
        producto_id = self._producto("Cerveza Polar", 2.5, "Cervezas")
        orden_id = self._orden()
        clases, tarjeta = self._tarjeta(self._html(orden_id), producto_id)

        self.assertIn("producto-item", clases)
        self.assertNotIn("agotado", clases)
        self.assertIn('class="qty-stepper"', tarjeta)
        self.assertIn(f'max="{MAX_CANTIDAD_ITEM}"', tarjeta)
        self.assertIn('value="1"', tarjeta)
        self.assertIn("btn-simple", tarjeta)
        self.assertIn(f'data-url="/agregar/{orden_id}/{producto_id}"', tarjeta)
        self.assertIn("Añadir", tarjeta)
        self.assertIn("$2.50", tarjeta)

    def test_combo_refresco_y_modificadores_conservan_su_flujo(self):
        combo_id = self._producto("Neko Combo 1", 5.3, "Neko Combos")
        refresco_id = self._producto("Refresco 1 Lt", 1.2, "Bebidas")
        jugo_id = self._producto("Jugo Natural", 2.0, "Bebidas")
        grupo_id = self._grupo_sabor(jugo_id, [("Mora", True), ("Fresa", True)])
        orden_id = self._orden()
        html = self._html(orden_id)

        _, combo = self._tarjeta(html, combo_id)
        self.assertIn("btn-configurable", combo)
        self.assertIn('data-tipo="combo"', combo)
        self.assertIn("data-acompanantes=", combo)
        _, refresco = self._tarjeta(html, refresco_id)
        self.assertIn("btn-refresco", refresco)
        clases_jugo, jugo = self._tarjeta(html, jugo_id)
        self.assertNotIn("agotado", clases_jugo)
        self.assertIn("btn-modificadores", jugo)
        self.assertIn(f'data-url="/agregar_con_modificadores/{orden_id}/{jugo_id}"', jugo)
        self.assertIn("Mora", jugo)
        self.assertNotIn(" disabled", jugo)

        # El backend sigue aplicando una configuracion comun a N unidades.
        response = self.client.get(
            f"/agregar_con_modificadores/{orden_id}/{jugo_id}?grupo_{grupo_id}=Mora&cantidad=3"
        )
        self.assertEqual(response.status_code, 302)
        html = self._html(orden_id)
        self.assertIn('data-item-producto="Jugo Natural" data-cantidad="3"', html)

    def test_producto_con_modificador_obligatorio_agotado_se_muestra_agotado(self):
        te_id = self._producto("Te Frio", 1.5, "Bebidas")
        self._grupo_sabor(te_id, [("Limon", False)])
        clases, tarjeta = self._tarjeta(self._html(self._orden()), te_id)

        self.assertIn("agotado", clases)
        self.assertIn("badge-agotado", tarjeta)
        self.assertRegex(tarjeta, r'class="btn-add btn-modificadores[^"]*"[^>]* disabled>')
        self.assertRegex(tarjeta, r'class="qty-input"[^>]* disabled>')

    def test_producto_sin_imagen_usa_placeholder_y_con_imagen_muestra_img(self):
        sin_imagen = self._producto("Pollo Agridulce", 4.8, "Favoritos de Neko")
        con_imagen = self._producto(
            "Neko Combo 2", 6.0, "Neko Combos", imagen_url="/static/productos/combo2.jpg"
        )
        html = self._html(self._orden())

        _, tarjeta = self._tarjeta(html, sin_imagen)
        self.assertIn("card-placeholder", tarjeta)
        self.assertNotIn("<img", tarjeta)
        _, tarjeta = self._tarjeta(html, con_imagen)
        self.assertIn('<img src="/static/productos/combo2.jpg"', tarjeta)
        self.assertIn("card-placeholder", tarjeta)  # queda debajo como fallback si la imagen falla

    def test_resumen_agrupa_unidades_y_cantidad_multiple_sigue_creando_filas(self):
        producto_id = self._producto("Cerveza Polar", 2.5, "Cervezas")
        orden_id = self._orden()
        response = self.client.get(f"/agregar/{orden_id}/{producto_id}?cantidad=4")
        self.assertEqual(response.status_code, 302)

        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orden_items WHERE orden_id=?", (orden_id,))
        self.assertEqual(cursor.fetchone()[0], 4)
        conn.close()

        html = self._html(orden_id)
        self.assertEqual(html.count('data-item-producto="Cerveza Polar"'), 1)
        self.assertIn('data-cantidad="4"', html)
        self.assertIn("$10.00", html)
        self.assertIn("Total Orden: $10.00", html)
        self.assertIn('data-items="4"', html)

    def test_orden_vacia_muestra_estado_vacio(self):
        self._producto("Cerveza Polar", 2.5, "Cervezas")
        html = self._html(self._orden())
        self.assertIn("Aún no hay productos", html)

    def test_orden_cerrada_no_renderiza_catalogo(self):
        self._producto("Cerveza Polar", 2.5, "Cervezas")
        html = self._html(self._orden(estado="cerrada"))
        self.assertIn('class="pagina-orden sin-catalogo"', html)
        self.assertNotIn('id="buscarProducto"', html)
        self.assertNotIn('<section class="cat-seccion"', html)
        self.assertIn("el catálogo está bloqueado", html)


if __name__ == "__main__":
    unittest.main()
