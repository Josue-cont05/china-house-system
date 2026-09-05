"""Tests de printer_diagnostics.py (scripts_locales): motor de
diagnostico/reparacion de la POS58, separado de Tkinter.

Incluye especificamente la regresion del caso real encontrado en la
primera prueba en PC limpia: Windows crea COM3 y COM4 (ambos "Serie
estandar sobre el vinculo Bluetooth") tras emparejar la POS58, pero
ninguno de los dos puede abrirse. La GUI NUNCA debe bloquearse ni pedir
seleccion manual de COM en ese caso.
"""

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import printer_diagnostics as pd  # noqa: E402


def _puerto(device, description="Standard Serial over Bluetooth link", hwid="BTHENUM\\X"):
    return SimpleNamespace(device=device, description=description, hwid=hwid, manufacturer=None, product=None)


# ----------------------------------------------------------------------
# probar_apertura(): threading + timeout real, sin GUI.
# ----------------------------------------------------------------------
class ProbarAperturaTest(unittest.TestCase):
    def test_abre_correctamente(self):
        resultado = pd.probar_apertura(lambda p: None, "COM6", timeout=1)

        self.assertTrue(resultado.abrio)
        self.assertIsNone(resultado.error)
        self.assertEqual(resultado.puerto, "COM6")

    def test_excepcion_se_reporta_como_fallo_sin_propagarse(self):
        def abridor(_puerto):
            raise OSError(22, "El dispositivo no reconoce el comando")

        resultado = pd.probar_apertura(abridor, "COM3", timeout=1)

        self.assertFalse(resultado.abrio)
        self.assertIn("22", resultado.error)

    def test_apertura_que_se_cuelga_no_bloquea_mas_del_timeout(self):
        def abridor(_puerto):
            time.sleep(5)  # simula una apertura de COM Bluetooth que nunca vuelve

        inicio = time.monotonic()
        resultado = pd.probar_apertura(abridor, "COM3", timeout=0.2)
        transcurrido = time.monotonic() - inicio

        self.assertFalse(resultado.abrio)
        self.assertEqual(resultado.error, "timeout")
        self.assertLess(transcurrido, 1.0)  # nunca espera los 5s completos del abridor


# ----------------------------------------------------------------------
# AsistenteDeteccion: la secuencia de decisiones (sin threading real: el
# `probador` inyectado ya devuelve ResultadoPrueba directamente).
# ----------------------------------------------------------------------
class AsistenteDeteccionCasoRealTest(unittest.TestCase):
    """El caso real reportado: COM3 y COM4, ambos fallan al abrir."""

    def test_com3_com4_ambos_fallan_no_pide_seleccion_ni_pregunta_si_no(self):
        candidatos = [_puerto("COM3"), _puerto("COM4")]
        probador = mock.Mock(
            side_effect=[
                pd.ResultadoPrueba("COM3", False, "timeout"),
                pd.ResultadoPrueba("COM4", False, "timeout"),
            ]
        )
        preguntar = mock.Mock()
        progreso_visto = []

        asistente = pd.AsistenteDeteccion(
            candidatos=candidatos, probador=probador, preguntar_si_no=preguntar,
            en_progreso=progreso_visto.append,
        )
        estado, puerto, resultados = asistente.ejecutar()

        self.assertEqual(estado, pd.ESTADO_PAREADA_SIN_ENLACE)
        self.assertIsNone(puerto)
        self.assertEqual(len(resultados), 2)
        self.assertTrue(all(not r.abrio for r in resultados))
        preguntar.assert_not_called()  # nunca "¿salio?" si ni siquiera abrio
        self.assertEqual(probador.call_count, 2)  # probo COM4 automaticamente tras fallar COM3

    def test_mensajes_de_progreso_nunca_mencionan_com_ni_excepciones(self):
        candidatos = [_puerto("COM3"), _puerto("COM4")]
        probador = mock.Mock(
            side_effect=[
                pd.ResultadoPrueba("COM3", False, "SerialException: OSError(22)"),
                pd.ResultadoPrueba("COM4", False, "timeout"),
            ]
        )
        progreso_visto = []

        pd.AsistenteDeteccion(
            candidatos=candidatos, probador=probador, preguntar_si_no=mock.Mock(),
            en_progreso=progreso_visto.append,
        ).ejecutar()

        texto = " ".join(progreso_visto).lower()
        for prohibido in ("com3", "com4", "oserror", "serialexception", "hwid", "timeout"):
            self.assertNotIn(prohibido, texto)


class AsistenteDeteccionOtrosCasosTest(unittest.TestCase):
    def test_primer_candidato_abre_y_usuario_confirma_si(self):
        candidatos = [_puerto("COM6")]
        probador = mock.Mock(return_value=pd.ResultadoPrueba("COM6", True, None))

        estado, puerto, resultados = pd.AsistenteDeteccion(
            candidatos, probador, preguntar_si_no=lambda: True
        ).ejecutar()

        self.assertEqual(estado, pd.ESTADO_OK)
        self.assertEqual(puerto.device, "COM6")
        self.assertEqual(len(resultados), 1)

    def test_primer_candidato_abre_pero_usuario_dice_no_prueba_el_segundo(self):
        candidatos = [_puerto("COM6"), _puerto("COM7")]
        probador = mock.Mock(
            side_effect=[
                pd.ResultadoPrueba("COM6", True, None),
                pd.ResultadoPrueba("COM7", True, None),
            ]
        )
        respuestas = iter([False, True])

        estado, puerto, resultados = pd.AsistenteDeteccion(
            candidatos, probador, preguntar_si_no=lambda: next(respuestas)
        ).ejecutar()

        self.assertEqual(estado, pd.ESTADO_OK)
        self.assertEqual(puerto.device, "COM7")
        self.assertEqual(probador.call_count, 2)

    def test_primer_candidato_no_abre_pasa_automaticamente_al_segundo(self):
        candidatos = [_puerto("COM3"), _puerto("COM6")]
        probador = mock.Mock(
            side_effect=[
                pd.ResultadoPrueba("COM3", False, "timeout"),
                pd.ResultadoPrueba("COM6", True, None),
            ]
        )

        estado, puerto, _ = pd.AsistenteDeteccion(
            candidatos, probador, preguntar_si_no=lambda: True
        ).ejecutar()

        self.assertEqual(estado, pd.ESTADO_OK)
        self.assertEqual(puerto.device, "COM6")

    def test_todos_los_candidatos_dicen_no_termina_pareada_sin_enlace(self):
        candidatos = [_puerto("COM6"), _puerto("COM7")]
        probador = mock.Mock(return_value=pd.ResultadoPrueba("X", True, None))

        estado, puerto, _ = pd.AsistenteDeteccion(
            candidatos, probador, preguntar_si_no=lambda: False
        ).ejecutar()

        self.assertEqual(estado, pd.ESTADO_PAREADA_SIN_ENLACE)
        self.assertIsNone(puerto)

    def test_sin_candidatos_no_llama_ni_probador_ni_preguntar(self):
        probador = mock.Mock()
        preguntar = mock.Mock()

        estado, puerto, resultados = pd.AsistenteDeteccion([], probador, preguntar).ejecutar()

        self.assertEqual(estado, pd.ESTADO_SIN_CANDIDATOS)
        self.assertIsNone(puerto)
        self.assertEqual(resultados, [])
        probador.assert_not_called()
        preguntar.assert_not_called()

    def test_puerto_no_relacionado_no_forma_parte_de_los_candidatos(self):
        # ordenar_candidatos_por_probabilidad ya excluye estos antes de
        # llegar aqui; el asistente simplemente no los ve.
        candidatos = [_puerto("COM6")]
        probador = mock.Mock(return_value=pd.ResultadoPrueba("COM6", True, None))

        pd.AsistenteDeteccion(candidatos, probador, preguntar_si_no=lambda: True).ejecutar()

        self.assertEqual(probador.call_count, 1)

    def test_registra_en_log_ambos_fallos(self):
        candidatos = [_puerto("COM3"), _puerto("COM4")]
        probador = mock.Mock(
            side_effect=[
                pd.ResultadoPrueba("COM3", False, "timeout"),
                pd.ResultadoPrueba("COM4", False, "timeout"),
            ]
        )
        log = mock.Mock()

        pd.AsistenteDeteccion(candidatos, probador, preguntar_si_no=mock.Mock(), log=log).ejecutar()

        self.assertGreaterEqual(log.info.call_count, 2)


# ----------------------------------------------------------------------
# esperar_puertos_nuevos(): asistente de reparacion, sin time.sleep real.
# ----------------------------------------------------------------------
class EsperarPuertosNuevosTest(unittest.TestCase):
    def test_encuentra_puerto_nuevo_en_el_primer_intento(self):
        antes = [_puerto("COM3")]
        despues = [_puerto("COM3"), _puerto("COM5")]
        dormir = mock.Mock()

        actuales, nuevos = pd.esperar_puertos_nuevos(lambda: despues, antes, dormir=dormir)

        self.assertEqual([p.device for p in nuevos], ["COM5"])
        dormir.assert_not_called()

    def test_reintenta_hasta_encontrar_puerto_tardio(self):
        antes = [_puerto("COM3")]
        respuestas = iter([antes, antes, [_puerto("COM3"), _puerto("COM5")]])
        dormir = mock.Mock()

        actuales, nuevos = pd.esperar_puertos_nuevos(
            lambda: next(respuestas), antes, intentos=5, dormir=dormir
        )

        self.assertEqual([p.device for p in nuevos], ["COM5"])
        self.assertEqual(dormir.call_count, 2)

    def test_agota_intentos_sin_encontrar_nada_nuevo(self):
        antes = [_puerto("COM3")]
        dormir = mock.Mock()

        actuales, nuevos = pd.esperar_puertos_nuevos(lambda: antes, antes, intentos=3, dormir=dormir)

        self.assertEqual(nuevos, [])
        self.assertEqual(dormir.call_count, 3)


# ----------------------------------------------------------------------
# Diagnostico / formateo humano / exportacion.
# ----------------------------------------------------------------------
class ResumenHumanoTest(unittest.TestCase):
    def test_todo_ok(self):
        diagnostico = pd.construir_diagnostico(
            candidatos=[_puerto("COM6")],
            resultados=[pd.ResultadoPrueba("COM6", True, None)],
            estado=pd.ESTADO_OK,
            puerto_confirmado=_puerto("COM6"),
            bluetooth=True,
            pos58_pareada=True,
        )

        resumen = dict(pd.resumen_humano(diagnostico))

        self.assertEqual(resumen["Bluetooth"], "OK")
        self.assertEqual(resumen["POS58"], "Emparejada")
        self.assertEqual(resumen["Enlace de impresión"], "OK")
        self.assertEqual(resumen["Prueba"], "OK")

    def test_pareada_sin_enlace(self):
        diagnostico = pd.construir_diagnostico(
            candidatos=[_puerto("COM3"), _puerto("COM4")],
            resultados=[
                pd.ResultadoPrueba("COM3", False, "timeout"),
                pd.ResultadoPrueba("COM4", False, "timeout"),
            ],
            estado=pd.ESTADO_PAREADA_SIN_ENLACE,
            bluetooth=True,
            pos58_pareada=True,
        )

        resumen = dict(pd.resumen_humano(diagnostico))

        self.assertEqual(resumen["Bluetooth"], "OK")
        self.assertEqual(resumen["POS58"], "Emparejada")
        self.assertEqual(resumen["Enlace de impresión"], "Problema")

    def test_bluetooth_desconocido_no_se_afirma_ok_ni_problema(self):
        diagnostico = pd.construir_diagnostico(
            candidatos=[], resultados=[], estado=pd.ESTADO_SIN_CANDIDATOS,
            bluetooth=None, pos58_pareada=None,
        )

        resumen = dict(pd.resumen_humano(diagnostico))

        self.assertEqual(resumen["Bluetooth"], "Desconocido")
        self.assertEqual(resumen["POS58"], "Desconocido")


class FormatearDiagnosticoTextoTest(unittest.TestCase):
    def test_incluye_datos_tecnicos_relevantes(self):
        diagnostico = pd.construir_diagnostico(
            candidatos=[_puerto("COM3"), _puerto("COM4")],
            resultados=[
                pd.ResultadoPrueba("COM3", False, "timeout"),
                pd.ResultadoPrueba("COM4", False, "timeout"),
            ],
            estado=pd.ESTADO_PAREADA_SIN_ENLACE,
            bluetooth=True,
            pos58_pareada=True,
        )

        texto = pd.formatear_diagnostico_texto(diagnostico, "Neko Local 1.0.1", True, "Windows-10")

        self.assertIn("Neko Local 1.0.1", texto)
        self.assertIn("COM3", texto)
        self.assertIn("COM4", texto)
        self.assertIn("PAIRED_BUT_NO_WORKING_SERIAL_LINK", texto)
        self.assertIn("Windows-10", texto)

    def test_no_incluye_credenciales_ni_secretos(self):
        diagnostico = pd.construir_diagnostico(candidatos=[], resultados=[], estado=pd.ESTADO_SIN_CANDIDATOS)

        texto = pd.formatear_diagnostico_texto(diagnostico, "Neko Local 1.0.1", False)

        for palabra in ("password", "secret", "token", "tarjeta"):
            self.assertNotIn(palabra, texto.lower())

    def test_maneja_diagnostico_vacio_sin_lanzar(self):
        diagnostico = pd.construir_diagnostico(candidatos=[], resultados=[], estado=pd.ESTADO_SIN_CANDIDATOS)

        texto = pd.formatear_diagnostico_texto(diagnostico, "Neko Local 1.0.1", False)

        self.assertIn("(ninguno)", texto)
        self.assertIn("(ninguno probado)", texto)


class GuardarDiagnosticoTest(unittest.TestCase):
    def test_guarda_y_devuelve_la_ruta(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "diag.txt"
            resultado = pd.guardar_diagnostico("contenido de prueba", ruta=ruta)

            self.assertEqual(resultado, ruta)
            self.assertEqual(ruta.read_text(encoding="utf-8"), "contenido de prueba")

    def test_crea_carpetas_intermedias_si_faltan(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "sub1" / "sub2" / "diag.txt"

            pd.guardar_diagnostico("x", ruta=ruta)

            self.assertTrue(ruta.exists())


if __name__ == "__main__":
    unittest.main()
