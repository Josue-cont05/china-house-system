"""Tests del entrypoint unico de Neko Local (neko_local.main): despacho
por argumentos hacia GUI / --kitchen-worker / --receipt-worker /
--version / --diagnostics, sin abrir Tkinter, Bluetooth, COM ni hacer
requests reales. Es el mismo entrypoint que usara NekoLocal.exe una vez
empaquetado (ver launcher_core.GestorWorkerProceso, seccion 4 de la
mision de empaquetado).
"""

import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import launcher_core  # noqa: E402
import neko_local  # noqa: E402
import neko_version  # noqa: E402
import printer_diagnostics  # noqa: E402


class VersionYAyudaTest(unittest.TestCase):
    def test_version_imprime_y_no_abre_gui(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            with mock.patch("builtins.print") as mock_print:
                resultado = neko_local.main(["--version"])

        MockApp.assert_not_called()
        self.assertEqual(resultado, 0)
        mock_print.assert_called_once_with(neko_version.version_texto())

    def test_diagnostics_no_abre_gui_ni_hardware(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            with mock.patch.object(neko_local, "_mostrar_diagnostics") as mock_diag:
                resultado = neko_local.main(["--diagnostics"])

        MockApp.assert_not_called()
        mock_diag.assert_called_once()
        self.assertEqual(resultado, 0)

    def test_diagnostics_no_imprime_secretos_y_cubre_las_rutas_clave(self):
        salida = []
        with mock.patch("builtins.print", side_effect=lambda *a: salida.append(" ".join(str(x) for x in a))):
            neko_local._mostrar_diagnostics()

        texto = "\n".join(salida)
        self.assertIn("frozen:", texto)
        self.assertIn("config_path:", texto)
        self.assertIn("state_dir:", texto)
        self.assertIn("logs_dir:", texto)
        self.assertNotIn("printer_fingerprint", texto)  # no vuelca la huella completa

    def test_help_no_abre_gui(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            with self.assertRaises(SystemExit) as ctx:
                neko_local.main(["--help"])

        MockApp.assert_not_called()
        self.assertEqual(ctx.exception.code, 0)

    def test_sin_argumentos_abre_la_gui(self):
        with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
            instancia = MockApp.return_value
            resultado = neko_local.main([])

        MockApp.assert_called_once()
        instancia.run.assert_called_once()
        self.assertEqual(resultado, 0)


class DespachoWorkerTest(unittest.TestCase):
    def test_print_dispatcher_delega_en_print_dispatcher(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"print_dispatcher": modulo_falso}):
            with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
                resultado = neko_local.main(["--print-dispatcher"])

        MockApp.assert_not_called()
        modulo_falso.main.assert_called_once_with([])
        self.assertEqual(resultado, 0)

    def test_print_dispatcher_reenvia_override_de_puerto(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"print_dispatcher": modulo_falso}):
            neko_local.main(["--print-dispatcher", "--port", "COM9"])

        modulo_falso.main.assert_called_once_with(["--port", "COM9"])

    def test_kitchen_worker_delega_en_script_comanda_cocina(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_comanda_cocina": modulo_falso}):
            with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
                resultado = neko_local.main(["--kitchen-worker"])

        MockApp.assert_not_called()
        modulo_falso.main.assert_called_once_with([])
        self.assertEqual(resultado, 0)

    def test_kitchen_worker_reenvia_override_de_puerto(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_comanda_cocina": modulo_falso}):
            neko_local.main(["--kitchen-worker", "--port", "COM9"])

        modulo_falso.main.assert_called_once_with(["--port", "COM9"])

    def test_receipt_worker_delega_en_script_factura(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_factura": modulo_falso}):
            with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
                resultado = neko_local.main(["--receipt-worker"])

        MockApp.assert_not_called()
        modulo_falso.main.assert_called_once_with([])
        self.assertEqual(resultado, 0)

    def test_receipt_worker_reenvia_override_de_puerto(self):
        modulo_falso = mock.Mock()
        modulo_falso.main.return_value = 0

        with mock.patch.dict(sys.modules, {"script_factura": modulo_falso}):
            neko_local.main(["--receipt-worker", "--port", "COM9"])

        modulo_falso.main.assert_called_once_with(["--port", "COM9"])


class GuiConDispatcherUnificadoTest(unittest.TestCase):
    """La app arranca con UN solo GestorWorkerProceso para el dispatcher
    unificado (mision "NEKO PRINTING 2.0", seccion 29: una sola tuberia
    fisica hacia la POS58, nunca dos procesos escribiendole al mismo
    tiempo), sin necesitar abrir Tkinter de verdad para inspeccionarlo."""

    def test_gestor_dispatcher_tiene_worker_path_y_modo_frozen_correctos(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertEqual(app.gestor_dispatcher.worker_path, launcher_core.WORKER_DISPATCHER_PATH)
            self.assertEqual(app.gestor_dispatcher.modo_frozen, launcher_core.MODO_FROZEN_DISPATCHER)
        finally:
            app.root.destroy()

    def test_no_existen_gestores_separados_de_cocina_y_recibos(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertFalse(hasattr(app, "gestor_cocina"))
            self.assertFalse(hasattr(app, "gestor_recibos"))
        finally:
            app.root.destroy()

    def test_titulo_incluye_la_version(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertIn(neko_version.APP_VERSION, app.root.title())
        finally:
            app.root.destroy()


def _buscar_texto_boton(widget, texto):
    for hijo in widget.winfo_children():
        if hijo.winfo_class() in ("TButton", "Button") and hijo.cget("text") == texto:
            return True
        if _buscar_texto_boton(hijo, texto):
            return True
    return False


class BotonesUiTest(unittest.TestCase):
    """El caso real de PC limpia (COM3/COM4 congelando la GUI) exigio un
    boton de troubleshooting siempre visible, sin eliminar el de
    deteccion automatica (mision de troubleshooting, seccion 1)."""

    def test_boton_solucionar_problemas_existe(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertTrue(_buscar_texto_boton(app.root, "SOLUCIONAR PROBLEMAS DE IMPRESORA"))
        finally:
            app.root.destroy()

    def test_boton_configurar_automaticamente_sigue_existiendo(self):
        app = neko_local.NekoLocalApp()
        try:
            self.assertTrue(_buscar_texto_boton(app.root, "CONFIGURAR IMPRESORA AUTOMÁTICAMENTE"))
        finally:
            app.root.destroy()


class AmbosBotonesComparteLogicaTest(unittest.TestCase):
    def test_configurar_automatico_y_solucionar_problemas_llaman_al_mismo_flujo(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(app, "_lanzar_diagnostico") as mock_lanzar:
                app._configurar_automaticamente()
                app._solucionar_problemas()
            self.assertEqual(mock_lanzar.call_count, 2)
        finally:
            app.root.destroy()


def _puerto(device, description="Standard Serial over Bluetooth link"):
    return SimpleNamespace(device=device, description=description, hwid=f"BTHENUM\\{device}", manufacturer=None, product=None)


class TrabajoDeteccionTest(unittest.TestCase):
    """_trabajo_deteccion corre en el hilo de trabajo real de
    _PuenteHiloGUI, pero se puede invocar directamente (sin hilos) para
    probar la logica: nunca toca hardware real porque
    printer_diagnostics.probar_apertura y windows_bluetooth.evaluar_bluetooth
    quedan mockeados."""

    def test_estado_ok_persiste_la_config(self):
        app = neko_local.NekoLocalApp()
        try:
            puerto = _puerto("COM6", "POS58")
            with mock.patch("neko_local.windows_bluetooth.evaluar_bluetooth", return_value=(True, True)), \
                 mock.patch("neko_local.port_detection.listar_puertos", return_value=[puerto]), \
                 mock.patch(
                     "neko_local.port_detection.ordenar_candidatos_por_probabilidad", return_value=[puerto]
                 ), \
                 mock.patch(
                     "neko_local.printer_diagnostics.probar_apertura",
                     return_value=printer_diagnostics.ResultadoPrueba("COM6", True, None),
                 ), \
                 mock.patch("neko_local.neko_config.guardar_config") as mock_guardar:
                diagnostico = app._trabajo_deteccion(progreso=lambda t: None, preguntar=lambda t: True)

            self.assertEqual(diagnostico.estado, printer_diagnostics.ESTADO_OK)
            self.assertEqual(diagnostico.puerto_confirmado.device, "COM6")
            mock_guardar.assert_called_once()
        finally:
            app.root.destroy()

    def test_caso_real_com3_com4_ambos_fallan_no_guarda_config_ni_pregunta(self):
        app = neko_local.NekoLocalApp()
        try:
            com3, com4 = _puerto("COM3"), _puerto("COM4")
            with mock.patch("neko_local.windows_bluetooth.evaluar_bluetooth", return_value=(True, True)), \
                 mock.patch("neko_local.port_detection.listar_puertos", return_value=[com3, com4]), \
                 mock.patch(
                     "neko_local.port_detection.ordenar_candidatos_por_probabilidad", return_value=[com3, com4]
                 ), \
                 mock.patch(
                     "neko_local.printer_diagnostics.probar_apertura",
                     side_effect=[
                         printer_diagnostics.ResultadoPrueba("COM3", False, "timeout"),
                         printer_diagnostics.ResultadoPrueba("COM4", False, "timeout"),
                     ],
                 ), \
                 mock.patch("neko_local.neko_config.guardar_config") as mock_guardar:
                preguntar = mock.Mock()
                diagnostico = app._trabajo_deteccion(progreso=lambda t: None, preguntar=preguntar)

            self.assertEqual(diagnostico.estado, printer_diagnostics.ESTADO_PAREADA_SIN_ENLACE)
            preguntar.assert_not_called()
            mock_guardar.assert_not_called()
        finally:
            app.root.destroy()


class AlTerminarDeteccionTest(unittest.TestCase):
    def test_estado_ok_muestra_info_y_actualiza(self):
        app = neko_local.NekoLocalApp()
        try:
            diagnostico = printer_diagnostics.construir_diagnostico(
                candidatos=[], resultados=[], estado=printer_diagnostics.ESTADO_OK,
                puerto_confirmado=_puerto("COM6"),
            )
            app._ventana_progreso = mock.Mock()
            with mock.patch("neko_local.messagebox.showinfo") as mock_info, \
                 mock.patch.object(app, "_actualizar_estados") as mock_actualizar:
                app._al_terminar_deteccion(diagnostico)
            mock_info.assert_called_once()
            mock_actualizar.assert_called_once()
        finally:
            app.root.destroy()

    def test_estado_pareada_sin_enlace_abre_asistente_reparacion(self):
        app = neko_local.NekoLocalApp()
        try:
            diagnostico = printer_diagnostics.construir_diagnostico(
                candidatos=[], resultados=[], estado=printer_diagnostics.ESTADO_PAREADA_SIN_ENLACE
            )
            app._ventana_progreso = mock.Mock()
            with mock.patch.object(app, "_mostrar_asistente_reparacion") as mock_reparar:
                app._al_terminar_deteccion(diagnostico)
            mock_reparar.assert_called_once_with(diagnostico)
        finally:
            app.root.destroy()

    def test_estado_sin_candidatos_muestra_pantalla_sin_candidatos(self):
        app = neko_local.NekoLocalApp()
        try:
            diagnostico = printer_diagnostics.construir_diagnostico(
                candidatos=[], resultados=[], estado=printer_diagnostics.ESTADO_SIN_CANDIDATOS
            )
            app._ventana_progreso = mock.Mock()
            with mock.patch.object(app, "_mostrar_sin_candidatos") as mock_sin:
                app._al_terminar_deteccion(diagnostico)
            mock_sin.assert_called_once()
        finally:
            app.root.destroy()

    def test_error_inesperado_muestra_mensaje_sin_lanzar(self):
        app = neko_local.NekoLocalApp()
        try:
            app._ventana_progreso = mock.Mock()
            with mock.patch("neko_local.messagebox.showerror") as mock_error:
                app._al_terminar_deteccion(("error", RuntimeError("boom")))
            mock_error.assert_called_once()
        finally:
            app.root.destroy()


class PuenteHiloGuiTest(unittest.TestCase):
    """El fallo real que motivo este modulo: la ventana de "Configurar
    impresora" quedaba en "(No responde)" al abrir un COM Bluetooth a
    medio crear. Este puente es lo que evita que vuelva a pasar."""

    def test_iniciar_no_bloquea_y_entrega_progreso_y_resultado_final(self):
        root = tk.Tk()
        try:
            progresos = []
            resultados = []

            def funcion(progreso, preguntar):
                progreso("paso 1")
                respuesta = preguntar("¿continuar?")
                progreso("paso 2" if respuesta else "cancelado")
                return "listo" if respuesta else "cancelado"

            with mock.patch("neko_local.messagebox.askyesno", return_value=True):
                puente = neko_local._PuenteHiloGUI(root, funcion, progresos.append, resultados.append)

                inicio = time.monotonic()
                puente.iniciar()
                self.assertLess(time.monotonic() - inicio, 0.5)  # iniciar() no bloquea

                limite = time.monotonic() + 5
                while not resultados and time.monotonic() < limite:
                    root.update()
                    time.sleep(0.01)

            self.assertEqual(resultados, ["listo"])
            self.assertIn("paso 1", progresos)
            self.assertIn("paso 2", progresos)
        finally:
            root.destroy()

    def test_funcion_que_se_cuelga_no_impide_que_iniciar_retorne(self):
        # Deliberadamente NO usa un tk.Tk() real: este caso abandona un
        # hilo huerfano de proposito (documentado en _PuenteHiloGUI), y
        # dejar un hilo real todavia vivo (durmiendo) al momento de
        # destruir/crear otros interpretes Tcl en tests posteriores puede
        # disparar errores internos de Tcl ("async handler deleted by
        # the wrong thread") que abortan el PROCESO completo de tests,
        # no solo este test. Un root falso basta: la propiedad que se
        # prueba (iniciar() nunca bloquea, sin importar cuanto tarde
        # `funcion`) no depende de un event loop real.
        root_falso = mock.Mock()

        def funcion_colgada(progreso, preguntar):
            time.sleep(5)
            return "nunca_llega_aqui_a_tiempo"

        puente = neko_local._PuenteHiloGUI(root_falso, funcion_colgada, lambda t: None, lambda r: None)

        inicio = time.monotonic()
        puente.iniciar()
        self.assertLess(time.monotonic() - inicio, 0.5)
        root_falso.after.assert_called_once()


if __name__ == "__main__":
    unittest.main()
