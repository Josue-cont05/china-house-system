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


if __name__ == "__main__":
    unittest.main()
