"""Menu como centro de administracion: productos, modificadores (flujo de
negocio), asociacion a productos, caso Jugo Natural de punta a punta e
imagenes de producto guardadas en la base de datos."""

import json
import os
import re
import tempfile
import unittest
from io import BytesIO

from PIL import Image

from app.domain.sales.modifiers import (
    MAXIMO_SIN_LIMITE,
    describir_reglas_grupo,
    normalizar_reglas_grupo,
)
from app.infrastructure.database.modifiers import (
    listar_grupos_modificadores_admin,
    listar_opciones_de_grupo_admin,
)
from app.infrastructure.database.sales.catalog import SqlSalesCatalogRepository
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(tempfile.gettempdir(), f"neko_pos_test_menu_admin_{os.getpid()}.db")


def _imagen_bytes(formato, tamano=(640, 480), modo="RGB", color=(220, 60, 60)):
    salida = BytesIO()
    imagen = Image.new(modo, tamano, color if modo == "RGB" else color + (128,))
    # algo de detalle para que la compresion sea realista
    for x in range(0, tamano[0], 7):
        for y in range(0, tamano[1], 11):
            imagen.putpixel((x, y), (x % 255, y % 255, (x * y) % 255) + (() if modo == "RGB" else (255,)))
    imagen.save(salida, format=formato)
    return salida.getvalue()


class ReglasGrupoTest(unittest.TestCase):
    def test_una_opcion_fija_minimo_y_maximo(self):
        self.assertEqual(normalizar_reglas_grupo(True, False, 5, 9), (1, 1))
        self.assertEqual(normalizar_reglas_grupo(False, False, 5, 9), (0, 1))

    def test_varias_opciones_respeta_avanzado_pero_coherente(self):
        self.assertEqual(normalizar_reglas_grupo(True, True), (1, MAXIMO_SIN_LIMITE))
        self.assertEqual(normalizar_reglas_grupo(False, True), (0, MAXIMO_SIN_LIMITE))
        self.assertEqual(normalizar_reglas_grupo(True, True, "2", "3"), (2, 3))
        self.assertEqual(normalizar_reglas_grupo(True, True, "0", "3"), (1, 3))
        self.assertEqual(normalizar_reglas_grupo(True, True, "4", "2"), (4, 4))
        # Opcional: el backend no exige minimo, asi que se guarda 0.
        self.assertEqual(normalizar_reglas_grupo(False, True, "2", "3"), (0, 3))
        self.assertEqual(normalizar_reglas_grupo(False, True, "x", ""), (0, MAXIMO_SIN_LIMITE))

    def test_descripcion_en_lenguaje_de_negocio(self):
        self.assertEqual(describir_reglas_grupo(True, False, 1, 1), "Obligatorio · Elegir una opción")
        self.assertEqual(describir_reglas_grupo(False, False, 0, 1), "Opcional · Elegir una opción")
        self.assertEqual(describir_reglas_grupo(False, True, 0, 3), "Opcional · Elegir hasta 3")
        self.assertEqual(describir_reglas_grupo(True, True, 1, MAXIMO_SIN_LIMITE), "Obligatorio · Elegir varias")


class MenuAdminRoutesTest(unittest.TestCase):
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
        for tabla in (
            "producto_imagenes", "producto_grupos_modificadores", "opciones_modificador",
            "grupos_modificadores", "orden_items", "ordenes", "productos", "categorias",
        ):
            cursor.execute(f"DELETE FROM {tabla}")
        cursor.execute("INSERT INTO categorias (nombre, activo) VALUES ('Bebidas', 1)")
        self.categoria_id = web_app.obtener_ultimo_id(cursor, "categorias")
        cursor.execute("SELECT id FROM usuarios WHERE rol='master' ORDER BY id LIMIT 1")
        self.master_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        self.repo = SqlSalesCatalogRepository(web_app.get_connection)
        self.client = web_app.app.test_client()
        self._login(self.master_id)

    # -- helpers -----------------------------------------------------------
    def _login(self, usuario_id):
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = usuario_id
            sess["usuario_nombre"] = "Emmanuel"

    def _login_rol(self, rol):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)",
            (f"Test {rol} {os.urandom(3).hex()}", os.urandom(3).hex(), rol),
        )
        usuario_id = web_app.obtener_ultimo_id(cursor, "usuarios")
        conn.commit()
        conn.close()
        self._login(usuario_id)

    def _producto(self, nombre="Jugo Natural", precio=2.0, activo=1, imagen_url=None):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO productos (nombre, precio, categoria_id, activo, imagen_url) VALUES (?, ?, ?, ?, ?)",
            (nombre, precio, self.categoria_id, activo, imagen_url),
        )
        producto_id = web_app.obtener_ultimo_id(cursor, "productos")
        conn.commit()
        conn.close()
        return producto_id

    def _orden(self):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id)
            VALUES (1, '2026-10-11 12:00:00', '2026-10-11', 'Mesa', 'Mesa 1', 'Ana', 'abierta', ?)
            """,
            (self.master_id,),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _crear_grupo(self, nombre, tipo="unica", obligatorio="1", **extra):
        datos = {"nombre": nombre, "tipo_seleccion": tipo, "obligatorio": obligatorio, "minimo": "1", "maximo": "1", "orden": "0"}
        datos.update(extra)
        respuesta = self.client.post("/menu/modificadores", data=datos)
        self.assertEqual(respuesta.status_code, 302)
        conn = web_app.get_connection()
        grupos = listar_grupos_modificadores_admin(conn.cursor())
        conn.close()
        grupo = next(g for g in grupos if g[1] == nombre)
        self.assertIn(f"#grupo-{grupo[0]}", respuesta.headers["Location"])
        return grupo

    def _agregar_opcion(self, grupo_id, nombre, precio="0"):
        respuesta = self.client.post(
            f"/menu/modificadores/{grupo_id}/opciones/crear",
            data={"nombre": nombre, "precio_adicional": precio, "orden": "0"},
        )
        self.assertEqual(respuesta.status_code, 302)

    def _subir(self, producto_id, datos, nombre="foto.jpg"):
        return self.client.post(
            f"/menu/producto/{producto_id}/imagen",
            data={"imagen": (BytesIO(datos), nombre)},
            content_type="multipart/form-data",
        )

    def _fila_imagen(self, producto_id):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT mime_type, ancho, alto, tamano_bytes FROM producto_imagenes WHERE producto_id=?",
            (producto_id,),
        )
        fila = cursor.fetchone()
        conn.close()
        return fila

    # -- Menu ----------------------------------------------------------------
    def test_menu_muestra_pestanas_filtros_y_tarjetas(self):
        producto_id = self._producto()
        self._producto("Te Viejo", activo=0)
        html = self.client.get("/menu").get_data(as_text=True)
        self.assertIn('<a class="ds-tab activo" href="/menu" aria-current="page">🍽️ Productos</a>', html)
        self.assertIn('<a class="ds-tab" href="/menu/modificadores">🧩 Modificadores</a>', html)
        for control in ('id="menuBuscar"', 'id="menuCategoria"', 'id="menuEstado"'):
            self.assertIn(control, html)
        self.assertIn(f'data-producto-id="{producto_id}"', html)
        self.assertIn('data-estado="inactivo"', html)
        self.assertIn(f'href="/editar_producto/{producto_id}"', html)
        self.assertIn("$2.00", html)
        # Sin borrado destructivo desde la interfaz.
        self.assertNotIn("/eliminar_producto/", html)
        self.assertIn('<option value="activo">Activos</option>', html)

    def test_activar_desactivar_producto_sin_borrar(self):
        producto_id = self._producto()
        self.assertEqual(self.client.post(f"/menu/producto/{producto_id}/activo", data={"activo": "0"}).status_code, 302)
        nombres = [p[1] for p in self.repo.listar_catalogo_activo()]
        self.assertNotIn("Jugo Natural", nombres)
        self.assertIsNotNone(self.repo.obtener_producto(producto_id))
        self.client.post(f"/menu/producto/{producto_id}/activo", data={"activo": "1"})
        self.assertIn("Jugo Natural", [p[1] for p in self.repo.listar_catalogo_activo()])

    def test_rutas_nuevas_requieren_master(self):
        producto_id = self._producto()
        self._login_rol("mesonera")
        self.assertEqual(self.client.get("/menu").status_code, 403)
        self.assertEqual(self.client.post(f"/menu/producto/{producto_id}/activo", data={"activo": "0"}).status_code, 403)
        self.assertEqual(self._subir(producto_id, _imagen_bytes("JPEG")).status_code, 403)
        self.assertEqual(self.client.post(f"/menu/producto/{producto_id}/imagen/quitar").status_code, 403)
        self.assertIsNone(self._fila_imagen(producto_id))

    # -- Modificadores ---------------------------------------------------------
    def test_crear_grupos_con_reglas_automaticas(self):
        g = self._crear_grupo("Sabor", "unica", "1", minimo="5", maximo="9")
        self.assertEqual((g[3], g[4], g[5], g[6]), (1, 0, 1, 1))
        g = self._crear_grupo("Salsa", "unica", "0")
        self.assertEqual((g[3], g[4], g[5], g[6]), (0, 0, 0, 1))
        g = self._crear_grupo("Toppings", "multiple", "1", minimo="0", maximo="")
        self.assertEqual((g[3], g[4], g[5], g[6]), (1, 1, 1, MAXIMO_SIN_LIMITE))
        g = self._crear_grupo("Extras", "multiple", "0", minimo="2", maximo="3")
        self.assertEqual((g[3], g[4], g[5], g[6]), (0, 1, 0, 3))
        g = self._crear_grupo("Salsas", "multiple", "1", minimo="2", maximo="3")
        self.assertEqual((g[3], g[4], g[5], g[6]), (1, 1, 2, 3))

    def test_editar_grupo_aplica_reglas(self):
        g = self._crear_grupo("Tamaño", "multiple", "0", minimo="0", maximo="4")
        respuesta = self.client.post(
            f"/menu/modificadores/{g[0]}/editar",
            data={"nombre": "Tamaño", "tipo_seleccion": "unica", "obligatorio": "1", "minimo": "0", "maximo": "4", "orden": "2"},
        )
        self.assertEqual(respuesta.status_code, 302)
        conn = web_app.get_connection()
        g = next(x for x in listar_grupos_modificadores_admin(conn.cursor()) if x[0] == g[0])
        conn.close()
        self.assertEqual(g[3:], (1, 0, 1, 1, 2))

    def test_pantalla_modificadores_en_lenguaje_de_negocio(self):
        g = self._crear_grupo("Sabor")
        self._agregar_opcion(g[0], "Fresa")
        self._agregar_opcion(g[0], "Parchita", "0.50")
        producto_id = self._producto()
        self.client.post(
            f"/editar_producto/{producto_id}",
            data={"nombre": "Jugo Natural", "precio": "2", "categoria_id": str(self.categoria_id), "grupo_modificador": str(g[0])},
        )
        html = self.client.get("/menu/modificadores").get_data(as_text=True)
        self.assertIn('<a class="ds-tab activo" href="/menu/modificadores" aria-current="page">', html)
        self.assertIn("Crea un grupo", html)
        self.assertIn("Asócialo a un producto desde Menú → Editar producto", html)
        self.assertIn("➕ Crear grupo", html)
        self.assertIn("Obligatorio · Elegir una opción · 2 opciones", html)
        self.assertIn("Usado en: Jugo Natural", html)
        self.assertIn("+$0.50", html)
        self.assertIn("Elegir una opción", html)
        self.assertIn("Permitir varias", html)
        # Avanzado existe y esta colapsado.
        self.assertIn('<details class="grupo-avanzado">', html)
        self.assertIn('name="minimo"', html)
        self.assertNotIn('<details class="grupo-avanzado" open', html)

    def test_disponible_agotada_y_activa_inactiva_de_opciones(self):
        g = self._crear_grupo("Sabor")
        self._agregar_opcion(g[0], "Mora")
        conn = web_app.get_connection()
        opcion_id = listar_opciones_de_grupo_admin(conn.cursor(), g[0])[0][0]
        conn.close()
        respuesta = self.client.post(f"/menu/modificadores/opciones/{opcion_id}/disponible", data={"disponible": "0"})
        self.assertTrue(respuesta.headers["Location"].endswith(f"#opcion-{opcion_id}"))
        html = self.client.get("/menu/modificadores").get_data(as_text=True)
        self.assertIn("Agotada", html)
        self.assertIn("Marcar disponible", html)
        self.client.post(f"/menu/modificadores/opciones/{opcion_id}/activa", data={"activa": "0"})
        conn = web_app.get_connection()
        fila = listar_opciones_de_grupo_admin(conn.cursor(), g[0])[0]
        conn.close()
        self.assertEqual((fila[2], fila[3]), (0, 0))  # inactiva, agotada; no se borra

    def test_desactivar_opcion_no_altera_historico(self):
        g = self._crear_grupo("Sabor")
        self._agregar_opcion(g[0], "Guanábana")
        producto_id = self._producto()
        self.client.post(
            f"/editar_producto/{producto_id}",
            data={"nombre": "Jugo Natural", "precio": "2", "categoria_id": str(self.categoria_id), "grupo_modificador": str(g[0])},
        )
        orden_id = self._orden()
        self.assertEqual(
            self.client.get(f"/agregar_con_modificadores/{orden_id}/{producto_id}?grupo_{g[0]}=Guanábana").status_code,
            302,
        )
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT indicacion FROM orden_items WHERE orden_id=?", (orden_id,))
        indicacion_antes = cursor.fetchone()[0]
        opcion_id = listar_opciones_de_grupo_admin(cursor, g[0])[0][0]
        conn.close()
        self.client.post(f"/menu/modificadores/opciones/{opcion_id}/activa", data={"activa": "0"})
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT indicacion FROM orden_items WHERE orden_id=?", (orden_id,))
        self.assertEqual(cursor.fetchone()[0], indicacion_antes)
        conn.close()
        self.assertIn("Guanábana", self.client.get(f"/orden/{orden_id}").get_data(as_text=True))

    # -- Editar producto -----------------------------------------------------
    def test_editar_producto_muestra_opciones_del_producto(self):
        sabor = self._crear_grupo("Sabor")
        tamano = self._crear_grupo("Tamaño", "unica", "0")
        producto_id = self._producto()
        self.client.post(
            f"/editar_producto/{producto_id}",
            data={"nombre": "Jugo Natural", "precio": "2", "categoria_id": str(self.categoria_id), "grupo_modificador": str(sabor[0])},
        )
        html = self.client.get(f"/editar_producto/{producto_id}").get_data(as_text=True)
        self.assertIn("<h2>Opciones del producto</h2>", html)
        self.assertIn("Los grupos seleccionados se pedirán al agregar este producto a una orden.", html)
        self.assertIn(f'name="grupo_modificador" value="{sabor[0]}" checked>', html)
        self.assertIn(f'name="grupo_modificador" value="{tamano[0]}" >', html)
        self.assertIn("<h2>Imagen del producto</h2>", html)
        self.assertIn('accept="image/jpeg,image/png,image/webp"', html)
        self.assertIn("Se mostrará en el POS y futuro menú QR.", html)
        self.assertIn('name="imagen_url"', html)

    # -- Jugo Natural ------------------------------------------------------
    def test_jugo_natural_de_punta_a_punta(self):
        self.client.post("/menu", data={"nombre": "Jugo Natural", "precio": "2.5", "categoria": str(self.categoria_id)})
        producto_id = next(p[0] for p in self.repo.listar_catalogo_activo() if p[1] == "Jugo Natural")

        sabor = self._crear_grupo("Sabor", "unica", "1")
        for opcion in ("Fresa", "Mora", "Guanábana", "Parchita"):
            self._agregar_opcion(sabor[0], opcion)
        azucar = self._crear_grupo("Nivel de azúcar", "unica", "1")
        for opcion in ("Con azúcar", "Sin azúcar", "Bajo de azúcar", "Mucha azúcar"):
            self._agregar_opcion(azucar[0], opcion)

        self.client.post(
            f"/editar_producto/{producto_id}",
            data={
                "nombre": "Jugo Natural", "precio": "2.5", "categoria_id": str(self.categoria_id),
                "grupo_modificador": [str(sabor[0]), str(azucar[0])],
            },
        )

        orden_id = self._orden()
        html = self.client.get(f"/orden/{orden_id}").get_data(as_text=True)
        tarjeta = re.search(rf'<article[^>]*data-producto-id="{producto_id}">(.*?)</article>', html, re.S).group(1)
        self.assertIn("btn-modificadores", tarjeta)
        datos = re.search(r'data-modificadores="([^"]+)"', tarjeta).group(1)
        grupos = json.loads(datos.replace("&quot;", '"').replace("&#x27;", "'"))
        self.assertEqual([g["nombre"] for g in grupos], ["Sabor", "Nivel de azúcar"])
        self.assertTrue(all(g["obligatorio"] and g["minimo"] == 1 and g["maximo"] == 1 for g in grupos))
        self.assertEqual([o["nombre"] for o in grupos[0]["opciones"]], ["Fresa", "Mora", "Guanábana", "Parchita"])
        self.assertEqual(len(grupos[1]["opciones"]), 4)

        # Falta un grupo obligatorio -> el backend lo rechaza.
        incompleto = self.client.get(f"/agregar_con_modificadores/{orden_id}/{producto_id}?grupo_{sabor[0]}=Mora")
        self.assertNotEqual(incompleto.status_code, 302)
        # Ambos grupos -> se agrega con la configuracion.
        completo = self.client.get(
            f"/agregar_con_modificadores/{orden_id}/{producto_id}?grupo_{sabor[0]}=Mora&grupo_{azucar[0]}=Sin%20az%C3%BAcar&cantidad=2"
        )
        self.assertEqual(completo.status_code, 302)
        resumen = self.client.get(f"/orden/{orden_id}").get_data(as_text=True)
        self.assertIn('data-item-producto="Jugo Natural" data-cantidad="2"', resumen)
        self.assertIn("Mora", resumen)
        self.assertIn("Sin azúcar", resumen)

    def test_orden_permite_omitir_grupo_opcional(self):
        extras = self._crear_grupo("Extras", "unica", "0")
        self._agregar_opcion(extras[0], "Hielo extra")
        producto_id = self._producto()
        self.client.post(
            f"/editar_producto/{producto_id}",
            data={"nombre": "Jugo Natural", "precio": "2", "categoria_id": str(self.categoria_id), "grupo_modificador": str(extras[0])},
        )
        orden_id = self._orden()
        html = self.client.get(f"/orden/{orden_id}").get_data(as_text=True)
        self.assertIn("&quot;obligatorio&quot;: false", html)
        self.assertIn('omitir.textContent = "Sin " + paso.titulo.toLowerCase();', html)
        self.assertEqual(self.client.get(f"/agregar_con_modificadores/{orden_id}/{producto_id}").status_code, 302)

    # -- Imagenes ----------------------------------------------------------
    def test_subir_jpg_png_webp_persiste_en_bd_y_se_sirve(self):
        for formato, nombre in (("JPEG", "a.jpg"), ("PNG", "b.png"), ("WEBP", "c.webp")):
            with self.subTest(formato=formato):
                producto_id = self._producto(f"Producto {formato}")
                respuesta = self._subir(producto_id, _imagen_bytes(formato, tamano=(1600, 1200)), nombre)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("ok=imagen", respuesta.headers["Location"])
                mime, ancho, alto, tamano = self._fila_imagen(producto_id)
                self.assertEqual((ancho, alto), (1000, 750))
                servida = self.client.get(f"/producto/{producto_id}/imagen")
                self.assertEqual(servida.status_code, 200)
                self.assertEqual(servida.mimetype, mime)
                self.assertEqual(len(servida.data), tamano)
                self.assertEqual(servida.headers["X-Content-Type-Options"], "nosniff")

    def test_archivo_invalido_no_se_guarda(self):
        producto_id = self._producto()
        for datos, nombre in (
            (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "x.svg"),
            (b"<html>no</html>", "foto.jpg"),
            (b"\x89PNG\r\n\x1a\n" + b"basura" * 50, "falsa.png"),
        ):
            with self.subTest(nombre=nombre):
                respuesta = self._subir(producto_id, datos, nombre)
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn('class="ds-alert ds-alert-danger"', respuesta.get_data(as_text=True))
                self.assertIsNone(self._fila_imagen(producto_id))

    def test_cache_version_y_miniatura(self):
        producto_id = self._producto()
        self._subir(producto_id, _imagen_bytes("JPEG", tamano=(1600, 1200)))
        url = self.repo.listar_imagenes_productos()[producto_id]
        self.assertRegex(url, rf"^/producto/{producto_id}/imagen\?v=[0-9a-f]{{12}}&t=mini$")
        mini = self.client.get(url)
        self.assertEqual(mini.headers["Cache-Control"], "public, max-age=31536000, immutable")
        grande = self.client.get(f"/producto/{producto_id}/imagen")
        self.assertLess(len(mini.data), len(grande.data))
        self.assertEqual(grande.headers["Cache-Control"], "public, max-age=300")
        no_modificada = self.client.get(url, headers={"If-None-Match": mini.headers["ETag"]})
        self.assertEqual(no_modificada.status_code, 304)

    def test_reemplazar_y_quitar_imagen(self):
        producto_id = self._producto()
        self._subir(producto_id, _imagen_bytes("JPEG", color=(10, 200, 10)))
        url_1 = self.repo.listar_imagenes_productos()[producto_id]
        self._subir(producto_id, _imagen_bytes("PNG", tamano=(500, 500), color=(10, 10, 200)))
        url_2 = self.repo.listar_imagenes_productos()[producto_id]
        self.assertNotEqual(url_1, url_2)
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM producto_imagenes WHERE producto_id=?", (producto_id,))
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

        respuesta = self.client.post(f"/menu/producto/{producto_id}/imagen/quitar")
        self.assertIn("ok=imagen_quitada", respuesta.headers["Location"])
        self.assertIsNone(self._fila_imagen(producto_id))
        self.assertEqual(self.client.get(f"/producto/{producto_id}/imagen").status_code, 404)
        self.assertIsNotNone(self.repo.obtener_producto(producto_id))
        self.assertIn("Imagen quitada", self.client.get(f"/editar_producto/{producto_id}?ok=imagen_quitada").get_data(as_text=True))

    def test_prioridad_bd_luego_imagen_url_luego_placeholder(self):
        con_url = self._producto("Con URL", imagen_url="https://cdn.neko.test/a.jpg")
        sin_nada = self._producto("Sin imagen")
        ambas = self._producto("Ambas", imagen_url="https://cdn.neko.test/b.jpg")
        self._subir(ambas, _imagen_bytes("JPEG"))
        urls = self.repo.listar_imagenes_productos()
        self.assertEqual(urls[con_url], "https://cdn.neko.test/a.jpg")
        self.assertNotIn(sin_nada, urls)
        self.assertTrue(urls[ambas].startswith(f"/producto/{ambas}/imagen?v="))

        menu = self.client.get("/menu").get_data(as_text=True)
        self.assertIn(f'<img src="/producto/{ambas}/imagen?v=', menu)
        self.assertIn('<img src="https://cdn.neko.test/a.jpg"', menu)

        orden_id = self._orden()
        html = self.client.get(f"/orden/{orden_id}").get_data(as_text=True)
        tarjeta = re.search(rf'<article[^>]*data-producto-id="{ambas}">(.*?)</article>', html, re.S).group(1)
        self.assertIn(f'<img src="/producto/{ambas}/imagen?v=', tarjeta)
        tarjeta = re.search(rf'<article[^>]*data-producto-id="{sin_nada}">(.*?)</article>', html, re.S).group(1)
        self.assertNotIn("<img", tarjeta)
        self.assertIn("card-placeholder", tarjeta)

    def test_imagen_publica_para_futuro_menu_qr(self):
        producto_id = self._producto()
        self._subir(producto_id, _imagen_bytes("JPEG"))
        anonimo = web_app.app.test_client()
        self.assertEqual(anonimo.get(f"/producto/{producto_id}/imagen").status_code, 200)
        self.assertEqual(anonimo.get("/menu").status_code, 302)
        self.assertEqual(anonimo.post(f"/menu/producto/{producto_id}/imagen/quitar").status_code, 302)
        self.assertIsNotNone(self._fila_imagen(producto_id))

    def test_eliminar_producto_limpia_imagen_y_asociaciones(self):
        g = self._crear_grupo("Sabor")
        producto_id = self._producto()
        self.client.post(
            f"/editar_producto/{producto_id}",
            data={"nombre": "Jugo Natural", "precio": "2", "categoria_id": str(self.categoria_id), "grupo_modificador": str(g[0])},
        )
        self._subir(producto_id, _imagen_bytes("JPEG"))
        self.repo.eliminar_producto(producto_id)
        self.assertIsNone(self._fila_imagen(producto_id))
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM producto_grupos_modificadores WHERE producto_id=?", (producto_id,))
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
