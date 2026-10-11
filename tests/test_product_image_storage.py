"""Imagenes de producto en base de datos: validacion/optimizacion
(Pillow) y compatibilidad SQLite/PostgreSQL del almacenamiento."""

import unittest
from io import BytesIO
from unittest import mock

from PIL import Image

from app.domain.sales.product_images import ImagenProductoInvalida
from app.infrastructure.database import product_images as product_images_db
from app.infrastructure.images.product_image_processing import (
    LADO_MAXIMO,
    LADO_MINIATURA,
    TAMANO_MAXIMO_ORIGINAL,
    detectar_formato,
    procesar_imagen_producto,
)


def _imagen_bytes(formato, tamano=(640, 480), modo="RGB", color=(220, 60, 60)):
    salida = BytesIO()
    imagen = Image.new(modo, tamano, color if modo == "RGB" else color + (128,))
    # algo de detalle para que la compresion sea realista
    for x in range(0, tamano[0], 7):
        for y in range(0, tamano[1], 11):
            imagen.putpixel((x, y), (x % 255, y % 255, (x * y) % 255) + (() if modo == "RGB" else (255,)))
    imagen.save(salida, format=formato)
    return salida.getvalue()


class ProcesamientoImagenTest(unittest.TestCase):
    def test_acepta_jpg_png_webp_y_reencoda(self):
        for formato in ("JPEG", "PNG", "WEBP"):
            with self.subTest(formato=formato):
                resultado = procesar_imagen_producto(_imagen_bytes(formato))
                self.assertIn(resultado.mime_type, ("image/webp", "image/jpeg"))
                self.assertEqual(detectar_formato(resultado.datos), "WEBP" if resultado.mime_type == "image/webp" else "JPEG")
                self.assertEqual((resultado.ancho, resultado.alto), (640, 480))

    def test_redimensiona_y_comprime(self):
        original = _imagen_bytes("PNG", tamano=(3000, 2000))
        resultado = procesar_imagen_producto(original)
        self.assertEqual(max(resultado.ancho, resultado.alto), LADO_MAXIMO)
        self.assertEqual((resultado.ancho, resultado.alto), (1000, 667))
        self.assertLess(len(resultado.datos), len(original))
        self.assertLess(len(resultado.miniatura), len(resultado.datos))
        with Image.open(BytesIO(resultado.miniatura)) as mini:
            self.assertEqual(max(mini.size), LADO_MINIATURA)

    def test_png_con_transparencia_se_acepta(self):
        resultado = procesar_imagen_producto(_imagen_bytes("PNG", modo="RGBA"))
        self.assertTrue(resultado.datos)

    def test_rechaza_formatos_no_permitidos(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        html = b"<html><body>hola</body></html>"
        gif = BytesIO()
        Image.new("RGB", (10, 10)).save(gif, format="GIF")
        for datos in (svg, html, gif.getvalue(), b"%PDF-1.4 ...", b""):
            with self.subTest(datos=datos[:12]):
                with self.assertRaises(ImagenProductoInvalida):
                    procesar_imagen_producto(datos)

    def test_rechaza_mime_falso(self):
        # Firma PNG valida pero contenido basura: la extension/firma no basta.
        with self.assertRaises(ImagenProductoInvalida):
            procesar_imagen_producto(b"\x89PNG\r\n\x1a\n" + b"no soy una imagen" * 20)
        # Firma JPEG con datos de un PNG real: el contenido no coincide.
        png = _imagen_bytes("PNG")
        with self.assertRaises(ImagenProductoInvalida):
            procesar_imagen_producto(b"\xff\xd8\xff" + png)

    def test_rechaza_archivo_excesivo(self):
        enorme = b"\xff\xd8\xff" + b"0" * (TAMANO_MAXIMO_ORIGINAL + 1)
        with self.assertRaises(ImagenProductoInvalida) as ctx:
            procesar_imagen_producto(enorme)
        self.assertIn("pesa demasiado", str(ctx.exception))


class ImagenesDbCompatibilidadTest(unittest.TestCase):
    def test_tipo_blob_por_motor(self):
        with mock.patch.object(product_images_db, "es_postgres", return_value=True):
            self.assertEqual(product_images_db.tipo_blob_sql(), "BYTEA")
        with mock.patch.object(product_images_db, "es_postgres", return_value=False):
            self.assertEqual(product_images_db.tipo_blob_sql(), "BLOB")

    def test_create_table_postgres_usa_bytea_y_es_idempotente(self):
        sentencias = []
        cursor = mock.Mock()
        cursor.execute.side_effect = lambda sql, *a: sentencias.append(sql)
        conn = mock.Mock(cursor=mock.Mock(return_value=cursor))
        with mock.patch.object(product_images_db, "es_postgres", return_value=True):
            product_images_db.crear_tabla_producto_imagenes(lambda: conn, lambda: "SERIAL PRIMARY KEY")
        sql = sentencias[0]
        self.assertIn("CREATE TABLE IF NOT EXISTS producto_imagenes", sql)
        self.assertIn("datos BYTEA NOT NULL", sql)
        self.assertIn("producto_id INTEGER NOT NULL UNIQUE", sql)
        self.assertNotIn("DROP", sql.upper())

    def test_lectura_acepta_memoryview_de_psycopg2(self):
        cursor = mock.Mock()
        cursor.fetchone.return_value = ("image/webp", memoryview(b"RIFF1234WEBP"), "2026-10-11", 12)
        mime, datos, version = product_images_db.obtener_imagen_producto(cursor, 1)
        self.assertEqual((mime, datos), ("image/webp", b"RIFF1234WEBP"))
        self.assertIsInstance(datos, bytes)
        self.assertTrue(version)


if __name__ == "__main__":
    unittest.main()
