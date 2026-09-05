"""Tests del dispatcher unificado (scripts_locales/print_dispatcher.py):
dedup local, ACK pendiente persistente, y la orquestacion de un job
(imprimir -> dedup -> ack / ack pendiente / fallo). Nunca abre COM ni
hace HTTP real: todo via dobles de prueba inyectados.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import print_dispatcher as dispatcher  # noqa: E402
import station_roles  # noqa: E402


class _ClienteFalso:
    def __init__(self, ack_ok=True, fallo_ok=True):
        self.ack_ok = ack_ok
        self.fallo_ok = fallo_ok
        self.acks_llamados = []
        self.fallos_llamados = []

    def confirmar(self, job_id, station_id, lease_token):
        self.acks_llamados.append((job_id, station_id, lease_token))
        return self.ack_ok

    def reportar_fallo(self, job_id, station_id, lease_token, error):
        self.fallos_llamados.append((job_id, station_id, lease_token, error))
        return self.fallo_ok


def _job(job_id=1, rol="COCINA", event_key="comanda-1-base", payload=None):
    return {
        "id": job_id,
        "event_key": event_key,
        "job_type": "comanda" if rol == "COCINA" else "recibo",
        "required_role": rol,
        "payload": payload or {"numero": 1, "items": ["1x Arroz"]},
        "lease_token": f"tok-{job_id}",
    }


class DedupLocalTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            __import__("neko_config"), "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_evento_nuevo_no_esta_marcado(self):
        dedup = dispatcher.DedupLocal("comandas_impresas.txt")
        self.assertFalse(dedup.contiene("comanda-1-base"))

    def test_marcar_y_verificar(self):
        dedup = dispatcher.DedupLocal("comandas_impresas.txt")
        dedup.marcar("comanda-1-base")
        self.assertTrue(dedup.contiene("comanda-1-base"))

    def test_persiste_entre_instancias(self):
        dispatcher.DedupLocal("comandas_impresas.txt").marcar("comanda-1-base")
        nueva_instancia = dispatcher.DedupLocal("comandas_impresas.txt")
        self.assertTrue(nueva_instancia.contiene("comanda-1-base"))

    def test_marcar_dos_veces_no_duplica_en_archivo(self):
        dedup = dispatcher.DedupLocal("comandas_impresas.txt")
        dedup.marcar("comanda-1-base")
        dedup.marcar("comanda-1-base")
        import neko_config

        contenido = neko_config.state_dir().joinpath("comandas_impresas.txt").read_text(encoding="utf-8")
        self.assertEqual(contenido.count("comanda-1-base"), 1)


class PendientesAckTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            __import__("neko_config"), "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_vacio_al_inicio(self):
        self.assertEqual(dispatcher.PendientesAck().listar(), [])

    def test_agregar_y_listar(self):
        pendientes = dispatcher.PendientesAck()
        pendientes.agregar(1, "st1", "tok1", "comanda-1-base")
        self.assertEqual(len(pendientes.listar()), 1)
        self.assertEqual(pendientes.listar()[0]["job_id"], 1)

    def test_agregar_el_mismo_job_dos_veces_no_duplica(self):
        pendientes = dispatcher.PendientesAck()
        pendientes.agregar(1, "st1", "tok1", "comanda-1-base")
        pendientes.agregar(1, "st1", "tok1", "comanda-1-base")
        self.assertEqual(len(pendientes.listar()), 1)

    def test_quitar_elimina_solo_ese_job(self):
        pendientes = dispatcher.PendientesAck()
        pendientes.agregar(1, "st1", "tok1", "e1")
        pendientes.agregar(2, "st1", "tok2", "e2")
        pendientes.quitar(1)
        restantes = pendientes.listar()
        self.assertEqual(len(restantes), 1)
        self.assertEqual(restantes[0]["job_id"], 2)

    def test_persiste_entre_instancias(self):
        dispatcher.PendientesAck().agregar(1, "st1", "tok1", "e1")
        self.assertEqual(len(dispatcher.PendientesAck().listar()), 1)


class ReintentarPendientesAckTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            __import__("neko_config"), "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_confirma_pendientes_exitosos_y_los_quita(self):
        pendientes = dispatcher.PendientesAck()
        pendientes.agregar(1, "st1", "tok1", "e1")
        cliente = _ClienteFalso(ack_ok=True)

        restantes = dispatcher.reintentar_pendientes_ack(cliente, pendientes)

        self.assertEqual(restantes, 0)
        self.assertEqual(pendientes.listar(), [])
        self.assertEqual(cliente.acks_llamados, [(1, "st1", "tok1")])

    def test_pendientes_que_siguen_fallando_permanecen(self):
        pendientes = dispatcher.PendientesAck()
        pendientes.agregar(1, "st1", "tok1", "e1")
        cliente = _ClienteFalso(ack_ok=False)

        restantes = dispatcher.reintentar_pendientes_ack(cliente, pendientes)

        self.assertEqual(restantes, 1)
        self.assertEqual(len(pendientes.listar()), 1)

    def test_sin_pendientes_no_llama_al_cliente(self):
        pendientes = dispatcher.PendientesAck()
        cliente = _ClienteFalso()

        restantes = dispatcher.reintentar_pendientes_ack(cliente, pendientes)

        self.assertEqual(restantes, 0)
        self.assertEqual(cliente.acks_llamados, [])


class ProcesarUnJobTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            __import__("neko_config"), "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()
        self.dedup_cocina = dispatcher.DedupLocal("comandas_impresas.txt")
        self.dedup_recibos = dispatcher.DedupLocal("facturas_impresas.txt")
        self.pendientes_ack = dispatcher.PendientesAck()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_impresion_y_ack_exitosos(self):
        cliente = _ClienteFalso(ack_ok=True)
        imprimir = mock.Mock()

        resultado = dispatcher.procesar_un_job(
            cliente, _job(), imprimir, self.dedup_cocina, self.dedup_recibos, self.pendientes_ack, "st1"
        )

        self.assertEqual(resultado, "impreso")
        imprimir.assert_called_once()
        self.assertTrue(self.dedup_cocina.contiene("comanda-1-base"))
        self.assertEqual(cliente.acks_llamados, [(1, "st1", "tok-1")])

    def test_evento_ya_en_dedup_no_reimprime_solo_reconfirma_ack(self):
        # Simula: se imprimio en un ciclo anterior pero el proceso se
        # reinicio antes de que el ACK se confirmara.
        self.dedup_cocina.marcar("comanda-1-base")
        cliente = _ClienteFalso(ack_ok=True)
        imprimir = mock.Mock()

        resultado = dispatcher.procesar_un_job(
            cliente, _job(), imprimir, self.dedup_cocina, self.dedup_recibos, self.pendientes_ack, "st1"
        )

        self.assertEqual(resultado, "ack_confirmado_sin_reimprimir")
        imprimir.assert_not_called()

    def test_fallo_de_impresion_reporta_fallo_no_confirma_ack(self):
        cliente = _ClienteFalso()
        imprimir = mock.Mock(side_effect=RuntimeError("puerto ocupado"))

        resultado = dispatcher.procesar_un_job(
            cliente, _job(), imprimir, self.dedup_cocina, self.dedup_recibos, self.pendientes_ack, "st1"
        )

        self.assertEqual(resultado, "fallo_impresion")
        self.assertFalse(self.dedup_cocina.contiene("comanda-1-base"))
        self.assertEqual(cliente.acks_llamados, [])
        self.assertEqual(len(cliente.fallos_llamados), 1)

    def test_impresion_ok_pero_ack_falla_queda_pendiente_sin_reimprimir(self):
        cliente = _ClienteFalso(ack_ok=False)
        imprimir = mock.Mock()

        resultado = dispatcher.procesar_un_job(
            cliente, _job(), imprimir, self.dedup_cocina, self.dedup_recibos, self.pendientes_ack, "st1"
        )

        self.assertEqual(resultado, "ack_pendiente")
        # CRITICO (mision seccion 21/65): el evento SI quedo marcado
        # como impreso localmente (no se reimprime), y el pendiente de
        # ACK quedo anotado para reintentar.
        self.assertTrue(self.dedup_cocina.contiene("comanda-1-base"))
        self.assertEqual(len(self.pendientes_ack.listar()), 1)
        imprimir.assert_called_once()

    def test_job_de_recibo_usa_el_dedup_de_facturas_no_el_de_comandas(self):
        cliente = _ClienteFalso(ack_ok=True)
        imprimir = mock.Mock()
        job_recibo = _job(job_id=5, rol="RECIBO_MESA", event_key="5-base")

        dispatcher.procesar_un_job(
            cliente, job_recibo, imprimir, self.dedup_cocina, self.dedup_recibos, self.pendientes_ack, "st1"
        )

        self.assertTrue(self.dedup_recibos.contiene("5-base"))
        self.assertFalse(self.dedup_cocina.contiene("5-base"))


class ImprimirPorRolTest(unittest.TestCase):
    def test_cocina_llama_a_comanda_presentacion(self):
        with mock.patch("print_dispatcher.imprimir_comanda") as mock_comanda:
            dispatcher._imprimir_por_rol(_job(rol="COCINA"), "COM6", 9600)
        mock_comanda.assert_called_once()

    def test_recibo_llama_a_factura_presentacion_no_a_comanda(self):
        job_recibo = _job(
            rol="RECIBO_MESA",
            payload={
                "numero": 1, "cliente": "Cliente", "tipo": "Mesa", "referencia": "Mesa 1",
                "fecha_hora": "2026-09-05 19:00:00", "items": [], "subtotal": 5.0,
                "descuento": 0, "delivery": 0, "total": 5.0, "total_bs": 200.0, "cobrada": False,
            },
        )
        with mock.patch("print_dispatcher.imprimir_comanda") as mock_comanda:
            with mock.patch("print_dispatcher.imprimir_factura") as mock_factura:
                dispatcher._imprimir_por_rol(job_recibo, "COM6", 9600)
        mock_comanda.assert_not_called()
        mock_factura.assert_called_once()


class EjecutarUnCicloTest(unittest.TestCase):
    """Regresion del caso real "Cola: sin conexion": ejecutar_un_ciclo()
    debe distinguir 'cola vacia' (CONECTADA, sin job) de 'no se pudo
    hablar con la cola' (SIN_CONEXION/ERROR_BACKEND), y NUNCA debe
    llamar a procesar_un_job() (imprimir/beep/ack) cuando la cola no
    esta usable -- mision seccion 14/16-19."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            __import__("neko_config"), "config_dir", return_value=Path(self._tmpdir.name) / "NekoWok"
        )
        self._patch.start()
        self.estado = dispatcher.EstadoDispatcher("COM6", 9600)
        self.dedup_cocina = dispatcher.DedupLocal("comandas_impresas.txt")
        self.dedup_recibos = dispatcher.DedupLocal("facturas_impresas.txt")
        self.pendientes_ack = dispatcher.PendientesAck()
        self.cliente = _ClienteFalso()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def _ciclo(self, evaluar_claim_fn):
        return dispatcher.ejecutar_un_ciclo(
            self.estado, "st1", ("COCINA",), self.cliente,
            self.dedup_cocina, self.dedup_recibos, self.pendientes_ack,
            evaluar_claim_fn=evaluar_claim_fn,
        )

    def test_conectada_sin_trabajos_no_imprime_nada(self):
        # Mision seccion 16: backend OK, status 200, sin pendientes.
        evaluar = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_CONECTADA, None, None))
        with mock.patch("print_dispatcher._imprimir_por_rol") as mock_imprimir:
            resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "sin_trabajos")
        self.assertEqual(heartbeat, dispatcher.print_queue_client.ESTADO_CONECTADA)
        mock_imprimir.assert_not_called()

    def test_conectada_con_trabajo_lo_procesa(self):
        job = {"id": 1, "event_key": "comanda-1-base", "job_type": "comanda", "required_role": "COCINA", "lease_token": "tok", "payload": {}}
        evaluar = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_CONECTADA, job, None))
        with mock.patch("print_dispatcher._imprimir_por_rol") as mock_imprimir:
            resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "trabajo_procesado")
        mock_imprimir.assert_called_once()
        self.assertEqual(self.cliente.acks_llamados, [(1, "st1", "tok")])

    def test_sin_conexion_no_reclama_no_imprime_no_suena(self):
        # Mision seccion 17: connection error.
        evaluar = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_SIN_CONEXION, None, "timeout"))
        with mock.patch("print_dispatcher._imprimir_por_rol") as mock_imprimir:
            resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "sin_conexion")
        self.assertEqual(heartbeat, dispatcher.print_queue_client.ESTADO_SIN_CONEXION)
        mock_imprimir.assert_not_called()
        self.assertEqual(self.cliente.acks_llamados, [])
        self.assertGreater(espera, 0)

    def test_error_backend_http_500_no_marca_conectado_no_reclama(self):
        # Mision seccion 18: HTTP 500 -- no debe tratarse como conectado.
        evaluar = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_ERROR_BACKEND, None, "HTTP 500"))
        with mock.patch("print_dispatcher._imprimir_por_rol") as mock_imprimir:
            resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "error_backend")
        mock_imprimir.assert_not_called()

    def test_json_invalido_se_trata_como_error_backend_no_claim(self):
        # Mision seccion 19: HTTP 200 pero respuesta invalida (el bug
        # real: pagina HTML de login en vez de JSON).
        evaluar = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_ERROR_BACKEND, None, "content-type inesperado: text/html"))
        with mock.patch("print_dispatcher._imprimir_por_rol") as mock_imprimir:
            resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "error_backend")
        mock_imprimir.assert_not_called()

    def test_backoff_aumenta_con_fallos_de_conexion_consecutivos(self):
        evaluar = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_SIN_CONEXION, None, "timeout"))
        esperas = []
        for _ in range(len(dispatcher.BACKOFF_CONEXION_SEG) + 2):
            _resultado, espera, _hb = self._ciclo(evaluar)
            esperas.append(espera)

        self.assertEqual(esperas[: len(dispatcher.BACKOFF_CONEXION_SEG)], list(dispatcher.BACKOFF_CONEXION_SEG))
        # Tope: no sigue creciendo indefinidamente.
        self.assertEqual(esperas[-1], dispatcher.BACKOFF_CONEXION_SEG[-1])

    def test_recuperacion_reinicia_el_backoff(self):
        sin_conexion = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_SIN_CONEXION, None, "timeout"))
        self._ciclo(sin_conexion)
        self._ciclo(sin_conexion)
        self.assertGreater(self.estado.fallos_conexion_consecutivos, 0)

        conectada = mock.Mock(return_value=(dispatcher.print_queue_client.ESTADO_CONECTADA, None, None))
        self._ciclo(conectada)
        self.assertEqual(self.estado.fallos_conexion_consecutivos, 0)

    def test_no_hace_claim_en_absoluto_si_hay_acks_pendientes(self):
        self.pendientes_ack.agregar(1, "st1", "tok1", "e1")
        self.cliente.ack_ok = False
        evaluar = mock.Mock()

        resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "ack_pendiente")
        evaluar.assert_not_called()

    def test_circuito_abierto_tras_max_fallos_de_impresion_no_reclama(self):
        self.estado.fallos_impresion_consecutivos = dispatcher.MAX_FALLOS_CONSECUTIVOS
        evaluar = mock.Mock()

        with mock.patch("print_dispatcher.resolver_puerto_worker", return_value=(None, None)):
            resultado, espera, heartbeat = self._ciclo(evaluar)

        self.assertEqual(resultado, "circuito_abierto")
        evaluar.assert_not_called()


class HeartbeatTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.ruta = Path(self._tmpdir.name) / "heartbeat.json"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_sin_heartbeat_previo_devuelve_none(self):
        self.assertIsNone(dispatcher.leer_heartbeat(ruta=self.ruta))

    def test_escribir_y_leer(self):
        dispatcher.escribir_heartbeat("CONECTADA", ruta=self.ruta)
        datos = dispatcher.leer_heartbeat(ruta=self.ruta)
        self.assertEqual(datos["estado_cola"], "CONECTADA")
        self.assertIn("actualizado_en", datos)

    def test_escrituras_sucesivas_actualizan_el_timestamp(self):
        dispatcher.escribir_heartbeat("CONECTADA", ruta=self.ruta)
        primero = dispatcher.leer_heartbeat(ruta=self.ruta)["actualizado_en"]
        dispatcher.escribir_heartbeat("SIN_CONEXION", ruta=self.ruta)
        segundo = dispatcher.leer_heartbeat(ruta=self.ruta)
        self.assertEqual(segundo["estado_cola"], "SIN_CONEXION")
        self.assertGreaterEqual(segundo["actualizado_en"], primero)

    def test_archivo_corrupto_no_lanza(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text("no es json{", encoding="utf-8")
        self.assertIsNone(dispatcher.leer_heartbeat(ruta=self.ruta))

    def test_directorio_inexistente_no_lanza_al_escribir(self):
        ruta_rara = Path(self._tmpdir.name) / "sub" / "otro" / "heartbeat.json"
        dispatcher.escribir_heartbeat("CONECTADA", ruta=ruta_rara)
        self.assertTrue(ruta_rara.exists())


if __name__ == "__main__":
    unittest.main()
