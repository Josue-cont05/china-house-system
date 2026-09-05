"""Tests de print_queue_client.py (scripts_locales): cliente HTTP de la
cola central de impresion. Nunca hace peticiones reales: `sesion` se
inyecta siempre con un doble de prueba.

Incluye especificamente la regresion real encontrada en produccion:
un antes_de_request del backend redirigia /api/printing/status a
/login para un cliente sin sesion (Neko Local no tiene sesion de
navegador). `requests` sigue redirects por defecto, asi que el
resultado era HTTP 200 con la pagina HTML de login en vez del JSON
esperado -- y el cliente antiguo lo reducia todo a None, sin dejar
ningun rastro de POR QUE. evaluar_status()/evaluar_claim() ahora
clasifican eso como ESTADO_ERROR_BACKEND con un detalle legible.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import print_queue_client as client  # noqa: E402


def _respuesta(status_code=200, json_data=None, content_type="application/json", json_error=False):
    resp = SimpleNamespace()
    resp.status_code = status_code
    resp.headers = {"Content-Type": content_type}
    if json_error:
        def _json():
            raise ValueError("Expecting value: line 2 column 5 (char 5)")
        resp.json = _json
    else:
        resp.json = lambda: json_data
    return resp


class UrlsTest(unittest.TestCase):
    """Mision seccion 2: auditar que todas las URLs usadas por Neko
    Local apuntan al backend real, sin localhost/dominios viejos/dobles
    barras/http en vez de https."""

    def test_status_url_exacta(self):
        self.assertEqual(client.URL_STATUS, "https://neko-wok-system.onrender.com/api/printing/status")

    def test_claim_url_exacta(self):
        self.assertEqual(client.URL_CLAIM, "https://neko-wok-system.onrender.com/api/printing/claim")

    def test_base_job_url_exacta(self):
        self.assertEqual(client.URL_BASE_JOB, "https://neko-wok-system.onrender.com/api/printing")

    def test_todas_usan_https(self):
        for url in (client.URL_STATUS, client.URL_CLAIM, client.URL_BASE_JOB):
            self.assertTrue(url.startswith("https://"))

    def test_ninguna_apunta_a_localhost_ni_dominio_viejo(self):
        for url in (client.URL_STATUS, client.URL_CLAIM, client.URL_BASE_JOB):
            texto = url.lower()
            self.assertNotIn("localhost", texto)
            self.assertNotIn("127.0.0.1", texto)
            self.assertNotIn("china-house", texto)

    def test_ninguna_tiene_doble_barra_despues_del_dominio(self):
        for url in (client.URL_STATUS, client.URL_CLAIM, client.URL_BASE_JOB):
            resto = url.split("://", 1)[1]
            self.assertNotIn("//", resto)

    def test_ack_y_fail_se_construyen_sobre_base_job(self):
        self.assertTrue(f"{client.URL_BASE_JOB}/1/ack".startswith(client.URL_STATUS.rsplit("/status", 1)[0]))
        self.assertTrue(f"{client.URL_BASE_JOB}/1/fail".startswith(client.URL_STATUS.rsplit("/status", 1)[0]))


class EvaluarStatusTest(unittest.TestCase):
    def test_conectada_con_pendientes(self):
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(200, {"ok": True, "pendientes": 3, "por_rol": {"COCINA": 3}})

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_CONECTADA)
        self.assertEqual(datos, {"pendientes": 3, "por_rol": {"COCINA": 3}})
        self.assertIsNone(detalle)

    def test_sin_roles_no_hace_peticion_y_esta_conectada_por_definicion(self):
        sesion = mock.Mock()

        estado, datos, detalle = client.evaluar_status((), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_CONECTADA)
        self.assertEqual(datos, {"pendientes": 0, "por_rol": {}})
        sesion.get.assert_not_called()

    def test_regresion_real_html_de_login_en_vez_de_json(self):
        """EL BUG REAL: HTTP 200 pero Content-Type text/html (la pagina
        de login, porque el endpoint no estaba en rutas_publicas)."""
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(200, content_type="text/html; charset=utf-8", json_error=True)

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_ERROR_BACKEND)
        self.assertIsNone(datos)
        self.assertIn("content-type", detalle.lower())

    def test_http_500_es_error_backend(self):
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(500, content_type="text/html")

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_ERROR_BACKEND)
        self.assertIn("500", detalle)

    def test_json_invalido_con_content_type_json_es_error_backend(self):
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(200, content_type="application/json", json_error=True)

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_ERROR_BACKEND)
        self.assertIn("json", detalle.lower())

    def test_ok_false_es_error_backend(self):
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(200, {"ok": False, "error": "roles desconocidos"})

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_ERROR_BACKEND)

    def test_timeout_es_sin_conexion(self):
        sesion = mock.Mock()
        sesion.get.side_effect = requests.exceptions.Timeout("tardo demasiado")

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_SIN_CONEXION)
        self.assertIn("timeout", detalle.lower())

    def test_connection_error_es_sin_conexion(self):
        sesion = mock.Mock()
        sesion.get.side_effect = requests.exceptions.ConnectionError("DNS fallo")

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_SIN_CONEXION)

    def test_ssl_error_es_sin_conexion(self):
        sesion = mock.Mock()
        sesion.get.side_effect = requests.exceptions.SSLError("certificado invalido")

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_SIN_CONEXION)
        self.assertIn("ssl", detalle.lower())

    def test_excepcion_generica_no_se_propaga(self):
        sesion = mock.Mock()
        sesion.get.side_effect = RuntimeError("algo raro")

        estado, datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_SIN_CONEXION)

    def test_nunca_devuelve_none_silencioso_como_unico_resultado(self):
        # Contrato: SIEMPRE hay un `detalle` breve cuando no esta CONECTADA.
        sesion = mock.Mock()
        sesion.get.side_effect = RuntimeError("misterioso")

        estado, _datos, detalle = client.evaluar_status(("COCINA",), sesion=sesion)

        self.assertNotEqual(estado, client.ESTADO_CONECTADA)
        self.assertTrue(detalle)


class EvaluarClaimTest(unittest.TestCase):
    def test_conectada_con_job(self):
        sesion = mock.Mock()
        sesion.post.return_value = _respuesta(200, {"ok": True, "job": {"id": 1}})

        estado, job, detalle = client.evaluar_claim("st1", ("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_CONECTADA)
        self.assertEqual(job, {"id": 1})

    def test_conectada_sin_job_disponible(self):
        sesion = mock.Mock()
        sesion.post.return_value = _respuesta(200, {"ok": True, "job": None})

        estado, job, detalle = client.evaluar_claim("st1", ("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_CONECTADA)
        self.assertIsNone(job)

    def test_regresion_real_html_de_login(self):
        sesion = mock.Mock()
        sesion.post.return_value = _respuesta(200, content_type="text/html", json_error=True)

        estado, job, detalle = client.evaluar_claim("st1", ("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_ERROR_BACKEND)
        self.assertIsNone(job)

    def test_sin_roles_no_hace_peticion(self):
        sesion = mock.Mock()

        estado, job, detalle = client.evaluar_claim("st1", (), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_CONECTADA)
        self.assertIsNone(job)
        sesion.post.assert_not_called()

    def test_sin_conexion_nunca_devuelve_job(self):
        sesion = mock.Mock()
        sesion.post.side_effect = requests.exceptions.ConnectionError("caida")

        estado, job, detalle = client.evaluar_claim("st1", ("COCINA",), sesion=sesion)

        self.assertEqual(estado, client.ESTADO_SIN_CONEXION)
        self.assertIsNone(job)


class ContratoSimpleTest(unittest.TestCase):
    """consultar_status()/reclamar(): contrato simple (dict/None) usado
    por el resto del codigo, construido sobre evaluar_status()/
    evaluar_claim()."""

    def test_consultar_status_conectada_devuelve_dict(self):
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(200, {"ok": True, "pendientes": 2, "por_rol": {}})

        self.assertEqual(client.consultar_status(("COCINA",), sesion=sesion), {"pendientes": 2, "por_rol": {}})

    def test_consultar_status_error_backend_devuelve_none(self):
        sesion = mock.Mock()
        sesion.get.return_value = _respuesta(200, content_type="text/html", json_error=True)

        self.assertIsNone(client.consultar_status(("COCINA",), sesion=sesion))

    def test_reclamar_sin_conexion_devuelve_none(self):
        sesion = mock.Mock()
        sesion.post.side_effect = requests.exceptions.Timeout("x")

        self.assertIsNone(client.reclamar("st1", ("COCINA",), sesion=sesion))

    def test_reclamar_error_backend_devuelve_none_no_el_job(self):
        # Aunque el backend devolviera algo parecido a un job, si la
        # respuesta no se pudo clasificar como CONECTADA, nunca se debe
        # entregar un job (evitar imprimir algo mal interpretado).
        sesion = mock.Mock()
        sesion.post.return_value = _respuesta(500)

        self.assertIsNone(client.reclamar("st1", ("COCINA",), sesion=sesion))


if __name__ == "__main__":
    unittest.main()
