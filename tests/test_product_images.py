"""Imagen opcional por producto (productos.imagen_url): validacion pura,
repositorio y campo en /editar_producto (Menu)."""

import os
import tempfile
import unittest

from app.domain.sales.product_images import ImagenProductoInvalida, normalizar_imagen_url
from app.infrastructure.database.sales.catalog import SqlSalesCatalogRepository
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_product_images_{os.getpid()}.db"
)


class NormalizarImagenUrlTest(unittest.TestCase):
    def test_vacio_significa_sin_imagen(self):
        self.assertIsNone(normalizar_imagen_url(""))
        self.assertIsNone(normalizar_imagen_url("   "))
        self.assertIsNone(normalizar_imagen_url(None))

    def test_acepta_https_http_y_ruta_del_servidor(self):
        self.assertEqual(normalizar_imagen_url(" https://cdn.neko.test/a.jpg "), "https://cdn.neko.test/a.jpg")
        self.assertEqual(normalizar_imagen_url("http://192.168.1.5/a.png"), "http://192.168.1.5/a.png")
        self.assertEqual(normalizar_imagen_url("/static/productos/combo1.webp"), "/static/productos/combo1.webp")

    def test_rechaza_esquemas_peligrosos_y_rutas_ambiguas(self):
        for valor in (
            "javascript:alert(1)",
            "data:image/svg+xml;base64,AAAA",
            "//evil.test/x.png",
            "productos/x.png",
            "/static/a b.png",
            '/static/a".png',
            "/static/<x>.png",
            "/" + "a" * 600,
        ):
            with self.subTest(valor=valor):
                with self.assertRaises(ImagenProductoInvalida):
                    normalizar_imagen_url(valor)


class ImagenProductoMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_sqlite_path = web_app.CONFIG["SQLITE_PATH"]
        web_app.CONFIG["SQLITE_PATH"] = _PRIVATE_DB_PATH
        web_app.init_db()

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
        cursor.execute("DELETE FROM productos")
        cursor.execute("DELETE FROM categorias")
        cursor.execute("INSERT INTO categorias (nombre, activo) VALUES ('Bebidas', 1)")
        self.categoria_id = web_app.obtener_ultimo_id(cursor, "categorias")
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id, activo) VALUES ('Jugo', 2.0, ?, 1)",
            (self.categoria_id,),
        )
        self.producto_id = web_app.obtener_ultimo_id(cursor, "productos")
        cursor.execute("SELECT id FROM usuarios WHERE rol='master' ORDER BY id LIMIT 1")
        master_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        self.repo = SqlSalesCatalogRepository(web_app.get_connection)
        self.client = web_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = master_id
            sess["usuario_nombre"] = "Emmanuel"
            sess["usuario"] = "Emmanuel"
            sess["usuario_rol"] = "master"

    def _editar(self, **extra):
        data = {"nombre": "Jugo", "precio": "2.0", "categoria_id": str(self.categoria_id)}
        data.update(extra)
        return self.client.post(f"/editar_producto/{self.producto_id}", data=data)

    def test_formulario_de_edicion_muestra_campo_imagen(self):
        response = self.client.get(f"/editar_producto/{self.producto_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="imagen_url"', response.data)

    def test_guardar_y_quitar_imagen(self):
        self.assertEqual(self._editar(imagen_url="/static/productos/jugo.jpg").status_code, 302)
        self.assertEqual(self.repo.obtener_imagen_producto(self.producto_id), "/static/productos/jugo.jpg")
        self.assertEqual(self.repo.listar_imagenes_productos(), {self.producto_id: "/static/productos/jugo.jpg"})

        self.assertEqual(self._editar(imagen_url="").status_code, 302)
        self.assertIsNone(self.repo.obtener_imagen_producto(self.producto_id))
        self.assertEqual(self.repo.listar_imagenes_productos(), {})

    def test_url_invalida_se_rechaza_sin_modificar_el_producto(self):
        response = self._editar(nombre="Jugo cambiado", imagen_url="javascript:alert(1)")
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.repo.obtener_imagen_producto(self.producto_id))
        self.assertEqual(self.repo.obtener_producto(self.producto_id)[0], "Jugo")

    def test_post_sin_campo_imagen_no_borra_la_existente(self):
        self.repo.actualizar_imagen_producto(self.producto_id, "https://cdn.neko.test/jugo.jpg")
        self.assertEqual(self._editar().status_code, 302)
        self.assertEqual(self.repo.obtener_imagen_producto(self.producto_id), "https://cdn.neko.test/jugo.jpg")


if __name__ == "__main__":
    unittest.main()
