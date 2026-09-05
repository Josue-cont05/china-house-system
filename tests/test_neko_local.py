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

    def _correr_diagnostics(self, nekopos_ok=True):
        salida = []
        with mock.patch("builtins.print", side_effect=lambda *a: salida.append(" ".join(str(x) for x in a))):
            with mock.patch.object(neko_local, "nekopos_accesible", return_value=nekopos_ok):
                with mock.patch.object(
                    neko_local.print_queue_client, "evaluar_status",
                    return_value=(
                        neko_local.print_queue_client.ESTADO_CONECTADA,
                        {"pendientes": 0, "por_rol": {}},
                        None,
                    ),
                ) as mock_evaluar_status:
                    neko_local._mostrar_diagnostics()
        return "\n".join(salida), mock_evaluar_status

    def test_diagnostics_no_imprime_secretos_y_cubre_las_rutas_clave(self):
        texto, _ = self._correr_diagnostics()

        self.assertIn("frozen:", texto)
        self.assertIn("config_path:", texto)
        self.assertIn("state_dir:", texto)
        self.assertIn("logs_dir:", texto)
        self.assertNotIn("printer_fingerprint", texto)  # no vuelca la huella completa

    def test_diagnostics_incluye_nekopos_api_y_printing_api(self):
        texto, _ = self._correr_diagnostics()

        self.assertIn("NekoPOS API: OK", texto)
        self.assertIn("Printing API: OK", texto)
        self.assertIn("Pendientes:", texto)

    def test_diagnostics_reporta_error_de_printing_api_sin_crashear(self):
        salida = []
        with mock.patch("builtins.print", side_effect=lambda *a: salida.append(" ".join(str(x) for x in a))):
            with mock.patch.object(neko_local, "nekopos_accesible", return_value=True):
                with mock.patch.object(
                    neko_local.print_queue_client, "evaluar_status",
                    return_value=(neko_local.print_queue_client.ESTADO_ERROR_BACKEND, None, "HTTP 500"),
                ):
                    neko_local._mostrar_diagnostics()

        texto = "\n".join(salida)
        self.assertIn("Printing API: ERROR", texto)
        self.assertIn("NekoPOS API: OK", texto)  # no confunde uno con el otro

    def test_diagnostics_nunca_hace_claim(self):
        _texto, _mock_status = self._correr_diagnostics()
        with mock.patch.object(neko_local.print_queue_client, "reclamar") as mock_reclamar:
            with mock.patch.object(neko_local, "nekopos_accesible", return_value=True):
                with mock.patch.object(
                    neko_local.print_queue_client, "evaluar_status",
                    return_value=(neko_local.print_queue_client.ESTADO_CONECTADA, {"pendientes": 0, "por_rol": {}}, None),
                ):
                    with mock.patch("builtins.print"):
                        neko_local._mostrar_diagnostics()
        mock_reclamar.assert_not_called()

    def test_diagnostics_no_abre_com_ni_navegador(self):
        with mock.patch.object(neko_local, "nekopos_accesible", return_value=True):
            with mock.patch.object(
                neko_local.print_queue_client, "evaluar_status",
                return_value=(neko_local.print_queue_client.ESTADO_CONECTADA, {"pendientes": 0, "por_rol": {}}, None),
            ):
                with mock.patch.object(neko_local, "webbrowser") as mock_browser:
                    with mock.patch("builtins.print"):
                        neko_local._mostrar_diagnostics()
        mock_browser.open.assert_not_called()

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
        # print_dispatcher se importa a nivel de modulo en neko_local.py
        # (para poder leer su heartbeat desde la GUI), no de forma
        # perezosa dentro de main() -- por eso se mockea el atributo
        # neko_local.print_dispatcher.main directamente, en vez de
        # sys.modules (que solo afecta a un import diferido).
        with mock.patch.object(neko_local.print_dispatcher, "main", return_value=0) as mock_main:
            with mock.patch.object(neko_local, "NekoLocalApp") as MockApp:
                resultado = neko_local.main(["--print-dispatcher"])

        MockApp.assert_not_called()
        mock_main.assert_called_once_with([])
        self.assertEqual(resultado, 0)

    def test_print_dispatcher_reenvia_override_de_puerto(self):
        with mock.patch.object(neko_local.print_dispatcher, "main", return_value=0) as mock_main:
            neko_local.main(["--print-dispatcher", "--port", "COM9"])

        mock_main.assert_called_once_with(["--port", "COM9"])

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

    def _mock_cola_conectada(self):
        """Las dos comprobaciones nuevas (NekoPOS + Printing API) al
        inicio de _trabajo_deteccion: por defecto CONECTADA, para que
        estos tests sigan probando especificamente el flujo de
        Bluetooth/COM sin que la cola interfiera."""
        return (
            mock.patch("neko_local.nekopos_accesible", return_value=True),
            mock.patch(
                "neko_local.print_queue_client.evaluar_status",
                return_value=(neko_local.print_queue_client.ESTADO_CONECTADA, {"pendientes": 0, "por_rol": {}}, None),
            ),
        )

    def test_estado_ok_persiste_la_config(self):
        app = neko_local.NekoLocalApp()
        try:
            puerto = _puerto("COM6", "POS58")
            mock_nekopos, mock_status = self._mock_cola_conectada()
            with mock_nekopos, mock_status, \
                 mock.patch("neko_local.windows_bluetooth.evaluar_bluetooth", return_value=(True, True)), \
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
            mock_nekopos, mock_status = self._mock_cola_conectada()
            with mock_nekopos, mock_status, \
                 mock.patch("neko_local.windows_bluetooth.evaluar_bluetooth", return_value=(True, True)), \
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

    def test_nekopos_ok_pero_printing_api_falla_no_llega_a_bluetooth(self):
        """REGRESION del caso real: NekoPOS conectado + Printing API sin
        responder debe cortar el flujo ANTES del baile de Bluetooth/COM
        (guiar por Bluetooth no sirve si el problema real es la cola)."""
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch("neko_local.nekopos_accesible", return_value=True), \
                 mock.patch(
                     "neko_local.print_queue_client.evaluar_status",
                     return_value=(neko_local.print_queue_client.ESTADO_ERROR_BACKEND, None, "content-type inesperado: text/html"),
                 ), \
                 mock.patch("neko_local.windows_bluetooth.evaluar_bluetooth") as mock_bluetooth:
                diagnostico = app._trabajo_deteccion(progreso=lambda t: None, preguntar=mock.Mock())

            self.assertEqual(diagnostico.estado, printer_diagnostics.ESTADO_COLA_SIN_CONEXION)
            self.assertTrue(diagnostico.nekopos_ok)
            mock_bluetooth.assert_not_called()  # nunca llega al baile de Bluetooth/COM
        finally:
            app.root.destroy()

    def test_nekopos_sin_conexion_no_dispara_el_chequeo_de_cola(self):
        # Si NekoPOS mismo no responde, es un problema de internet en
        # general (ya cubierto por el estado "NekoPOS: sin conexion"
        # de la fila principal) -- no tiene sentido comprobar la cola
        # por separado ni cortar el flujo de Bluetooth por eso.
        app = neko_local.NekoLocalApp()
        try:
            puerto = _puerto("COM6", "POS58")
            with mock.patch("neko_local.nekopos_accesible", return_value=False), \
                 mock.patch("neko_local.print_queue_client.evaluar_status") as mock_status, \
                 mock.patch("neko_local.windows_bluetooth.evaluar_bluetooth", return_value=(True, True)), \
                 mock.patch("neko_local.port_detection.listar_puertos", return_value=[puerto]), \
                 mock.patch(
                     "neko_local.port_detection.ordenar_candidatos_por_probabilidad", return_value=[puerto]
                 ), \
                 mock.patch(
                     "neko_local.printer_diagnostics.probar_apertura",
                     return_value=printer_diagnostics.ResultadoPrueba("COM6", True, None),
                 ), \
                 mock.patch("neko_local.neko_config.guardar_config"):
                diagnostico = app._trabajo_deteccion(progreso=lambda t: None, preguntar=lambda t: True)

            mock_status.assert_not_called()
            self.assertEqual(diagnostico.estado, printer_diagnostics.ESTADO_OK)
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

    def test_estado_cola_sin_conexion_muestra_su_propia_pantalla(self):
        app = neko_local.NekoLocalApp()
        try:
            diagnostico = printer_diagnostics.construir_diagnostico(
                candidatos=[], resultados=[], estado=printer_diagnostics.ESTADO_COLA_SIN_CONEXION,
                nekopos_ok=True, printing_api_estado="ERROR_BACKEND", printing_api_detalle="HTTP 500",
            )
            app._ventana_progreso = mock.Mock()
            with mock.patch.object(app, "_mostrar_cola_sin_conexion") as mock_cola:
                app._al_terminar_deteccion(diagnostico)
            mock_cola.assert_called_once_with(diagnostico)
        finally:
            app.root.destroy()


class ComprobarColaDeNuevoTest(unittest.TestCase):
    """Autorreparacion segura (mision seccion 11): reiniciar SOLO el
    dispatcher propio si esta muerto, nunca tocar Bluetooth/COM/Windows."""

    def test_dispatcher_muerto_se_reinicia_antes_de_comprobar(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=False), \
                 mock.patch.object(app.gestor_dispatcher, "iniciar") as mock_iniciar, \
                 mock.patch("neko_local.neko_config.tiene_impresora_configurada", return_value=True), \
                 mock.patch(
                     "neko_local.resolver_y_persistir_puerto",
                     return_value=SimpleNamespace(status="ok", port="COM6"),
                 ), \
                 mock.patch.object(app, "_lanzar_diagnostico") as mock_lanzar:
                app._comprobar_cola_de_nuevo()

            mock_iniciar.assert_called_once_with("COM6")
            mock_lanzar.assert_called_once()
        finally:
            app.root.destroy()

    def test_dispatcher_activo_no_se_reinicia(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=True), \
                 mock.patch.object(app.gestor_dispatcher, "iniciar") as mock_iniciar, \
                 mock.patch.object(app, "_lanzar_diagnostico") as mock_lanzar:
                app._comprobar_cola_de_nuevo()

            mock_iniciar.assert_not_called()
            mock_lanzar.assert_called_once()
        finally:
            app.root.destroy()

    def test_sin_impresora_configurada_no_intenta_reiniciar(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=False), \
                 mock.patch.object(app.gestor_dispatcher, "iniciar") as mock_iniciar, \
                 mock.patch("neko_local.neko_config.tiene_impresora_configurada", return_value=False), \
                 mock.patch.object(app, "_lanzar_diagnostico") as mock_lanzar:
                app._comprobar_cola_de_nuevo()

            mock_iniciar.assert_not_called()
            mock_lanzar.assert_called_once()
        finally:
            app.root.destroy()


class ConsultarColaAsyncTest(unittest.TestCase):
    """Mision 'Cola: sin conexion': estados claros y separados de
    NekoPOS (seccion 6/7 de esa mision)."""

    def test_conectada_sin_pendientes_dice_conectada(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(
                neko_local.print_queue_client, "evaluar_status",
                return_value=(neko_local.print_queue_client.ESTADO_CONECTADA, {"pendientes": 0, "por_rol": {}}, None),
            ):
                app._consultar_cola_async(("COCINA",))
            self.assertEqual(app._var_cola.get(), "conectada")
        finally:
            app.root.destroy()

    def test_conectada_con_pendientes_muestra_el_numero(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(
                neko_local.print_queue_client, "evaluar_status",
                return_value=(neko_local.print_queue_client.ESTADO_CONECTADA, {"pendientes": 4, "por_rol": {}}, None),
            ):
                app._consultar_cola_async(("COCINA",))
            self.assertEqual(app._var_cola.get(), "4 pendientes")
        finally:
            app.root.destroy()

    def test_sin_conexion_nunca_dice_conectada(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(
                neko_local.print_queue_client, "evaluar_status",
                return_value=(neko_local.print_queue_client.ESTADO_SIN_CONEXION, None, "timeout"),
            ):
                app._consultar_cola_async(("COCINA",))
            self.assertEqual(app._var_cola.get(), "sin conexión")
        finally:
            app.root.destroy()

    def test_error_backend_es_distinto_de_sin_conexion(self):
        # REGRESION: antes, cualquier fallo (incluida la pagina de login
        # devuelta en vez de JSON) se veia identico a "sin internet".
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(
                neko_local.print_queue_client, "evaluar_status",
                return_value=(neko_local.print_queue_client.ESTADO_ERROR_BACKEND, None, "HTTP 500"),
            ):
                app._consultar_cola_async(("COCINA",))
            self.assertEqual(app._var_cola.get(), "error del servidor")
        finally:
            app.root.destroy()


class TextoEstadoImpresionTest(unittest.TestCase):
    def test_proceso_muerto_dice_detenida(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=False):
                self.assertEqual(app._texto_estado_impresion(), "Detenida")
        finally:
            app.root.destroy()

    def test_proceso_vivo_sin_heartbeat_previo_dice_activa(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=True), \
                 mock.patch.object(neko_local.print_dispatcher, "leer_heartbeat", return_value=None):
                self.assertEqual(app._texto_estado_impresion(), "Activa")
        finally:
            app.root.destroy()

    def test_proceso_vivo_con_heartbeat_reciente_dice_activa(self):
        app = neko_local.NekoLocalApp()
        try:
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=True), \
                 mock.patch.object(
                     neko_local.print_dispatcher, "leer_heartbeat",
                     return_value={"actualizado_en": time.time(), "estado_cola": "CONECTADA"},
                 ):
                self.assertEqual(app._texto_estado_impresion(), "Activa")
        finally:
            app.root.destroy()

    def test_proceso_vivo_con_heartbeat_obsoleto_dice_sin_respuesta(self):
        # Mision seccion 13: proceso vivo pero dejo de avanzar (colgado).
        app = neko_local.NekoLocalApp()
        try:
            hace_mucho = time.time() - (neko_local.print_dispatcher.HEARTBEAT_OBSOLETO_SEG + 30)
            with mock.patch.object(type(app.gestor_dispatcher), "activo", new_callable=mock.PropertyMock, return_value=True), \
                 mock.patch.object(
                     neko_local.print_dispatcher, "leer_heartbeat",
                     return_value={"actualizado_en": hace_mucho, "estado_cola": "CONECTADA"},
                 ):
                self.assertEqual(app._texto_estado_impresion(), "Activa (sin respuesta)")
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
