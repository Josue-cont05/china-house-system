"""Tests de app/infrastructure/database/print_queue.py: creacion
idempotente de jobs, claim atomico (incluida una carrera real con
hilos), ack, fail, y expiracion de lease. Usa su propia base SQLite
privada (no la compartida) para no interferir con otros modulos de test.
"""

import os
import tempfile
import threading
import unittest

from app.infrastructure.database.print_queue import (
    ESTADO_PENDING,
    RESULTADO_LEASE_INVALIDO,
    RESULTADO_NO_ENCONTRADO,
    RESULTADO_OK,
    RESULTADO_OK_IDEMPOTENTE,
    SqlPrintQueueRepository,
    crear_job_en_cursor,
    crear_tabla_print_jobs,
)
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_print_queue_infra_{os.getpid()}.db"
)


class PrintQueueInfraTest(unittest.TestCase):
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
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM print_jobs")
        conn.commit()
        conn.close()
        self.repo = SqlPrintQueueRepository(web_app.get_connection)

    def _crear_job(self, event_key, required_role="COCINA", job_type="comanda", fecha="2026-09-05 19:00:00", payload=None):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        creado = crear_job_en_cursor(
            cursor, event_key=event_key, job_type=job_type, required_role=required_role,
            payload=payload or {"x": 1}, fecha=fecha,
        )
        conn.commit()
        conn.close()
        return creado

    def _estado_job(self, event_key):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM print_jobs WHERE event_key=?", (event_key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


class CrearJobTest(PrintQueueInfraTest):
    def test_crea_un_job_nuevo(self):
        self.assertTrue(self._crear_job("evt-1"))
        self.assertEqual(self._estado_job("evt-1"), ESTADO_PENDING)

    def test_llamada_repetida_con_mismo_event_key_no_duplica(self):
        self.assertTrue(self._crear_job("evt-1"))
        self.assertFalse(self._crear_job("evt-1"))

        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM print_jobs WHERE event_key=?", ("evt-1",))
        cantidad = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(cantidad, 1)

    def test_event_keys_distintos_crean_jobs_distintos(self):
        self.assertTrue(self._crear_job("evt-1"))
        self.assertTrue(self._crear_job("evt-2"))

    def test_payload_se_guarda_y_se_recupera_completo(self):
        self._crear_job("evt-1", payload={"items_crudos": [["Arroz", ""]], "numero": 33})
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE print_jobs SET status='PENDING' WHERE event_key=?", ("evt-1",)
        )
        conn.commit()
        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:30",
        )
        conn.close()
        self.assertEqual(job["payload"]["numero"], 33)
        self.assertEqual(job["payload"]["items_crudos"], [["Arroz", ""]])


class ReclamarJobTest(PrintQueueInfraTest):
    def test_sin_jobs_devuelve_none(self):
        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.assertIsNone(job)

    def test_reclama_el_unico_job_disponible(self):
        self._crear_job("evt-1", required_role="COCINA")
        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.assertIsNotNone(job)
        self.assertEqual(job["event_key"], "evt-1")

    def test_rol_incompatible_no_reclama_nada(self):
        self._crear_job("evt-1", required_role="RECIBO_MESA")
        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.assertIsNone(job)

    def test_segunda_estacion_no_puede_reclamar_el_mismo_job_secuencial(self):
        """Dos llamadas secuenciales contra el MISMO job pendiente:
        la primera lo reclama, la segunda no debe obtener nada (el
        UPDATE condicional re-evalua el estado, ya LEASED)."""
        self._crear_job("evt-1")

        job_a = self.repo.reclamar_job(
            roles=("COCINA",), station_id="PC-A", lease_token="tok-a",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        job_b = self.repo.reclamar_job(
            roles=("COCINA",), station_id="PC-B", lease_token="tok-b",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )

        self.assertIsNotNone(job_a)
        self.assertIsNone(job_b)

    def test_carrera_real_con_hilos_solo_una_estacion_gana(self):
        """Concurrencia real (dos conexiones/hilos distintos, no solo
        llamadas secuenciales) contra UN solo job: exactamente una debe
        ganarlo. Esto es lo que prueba que el UPDATE condicional es
        realmente atomico y no un SELECT+UPDATE separado."""
        self._crear_job("evt-race")
        resultados = []
        barrera = threading.Barrier(2)

        def intentar_reclamar(station_id):
            barrera.wait()
            job = self.repo.reclamar_job(
                roles=("COCINA",), station_id=station_id, lease_token=f"tok-{station_id}",
                lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
            )
            resultados.append(job)

        hilos = [
            threading.Thread(target=intentar_reclamar, args=("PC-A",)),
            threading.Thread(target=intentar_reclamar, args=("PC-B",)),
        ]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=10)

        ganadores = [j for j in resultados if j is not None]
        self.assertEqual(len(ganadores), 1)

    def test_prioriza_cocina_sobre_recibos(self):
        self._crear_job("evt-recibo", required_role="RECIBO_MESA", fecha="2026-09-05 18:00:00")
        self._crear_job("evt-cocina", required_role="COCINA", fecha="2026-09-05 19:00:00")

        job = self.repo.reclamar_job(
            roles=("COCINA", "RECIBO_MESA"), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.assertEqual(job["event_key"], "evt-cocina")

    def test_fifo_dentro_del_mismo_rol(self):
        self._crear_job("evt-viejo", required_role="COCINA", fecha="2026-09-05 18:00:00")
        self._crear_job("evt-nuevo", required_role="COCINA", fecha="2026-09-05 19:00:00")

        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.assertEqual(job["event_key"], "evt-viejo")

    def test_job_printed_nunca_vuelve_a_salir(self):
        self._crear_job("evt-1")
        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.repo.confirmar_ack(job_id=job["id"], station_id="st1", lease_token="tok1", fecha="2026-09-05 19:00:10")

        job_de_nuevo = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st2", lease_token="tok2",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:20",
        )
        self.assertIsNone(job_de_nuevo)

    def test_lease_vigente_bloquea_reclamo(self):
        self._crear_job("evt-1")
        self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        job_b = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st2", lease_token="tok2",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:02:00",  # antes de que expire
        )
        self.assertIsNone(job_b)

    def test_lease_vencido_libera_el_job_automaticamente(self):
        self._crear_job("evt-1")
        self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:01:00", ahora_texto="2026-09-05 19:00:00",
        )
        # "ahora" ya paso el lease_expires_at de la primera reclamacion.
        job_b = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st2", lease_token="tok2",
            lease_expires_texto="2026-09-05 19:10:00", ahora_texto="2026-09-05 19:05:00",
        )
        self.assertIsNotNone(job_b)
        self.assertEqual(job_b["event_key"], "evt-1")


class ConfirmarAckTest(PrintQueueInfraTest):
    def _reclamar(self, event_key="evt-1", station_id="st1", lease_token="tok1"):
        self._crear_job(event_key)
        return self.repo.reclamar_job(
            roles=("COCINA",), station_id=station_id, lease_token=lease_token,
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )

    def test_ack_correcto(self):
        job = self._reclamar()
        resultado = self.repo.confirmar_ack(
            job_id=job["id"], station_id="st1", lease_token="tok1", fecha="2026-09-05 19:00:05"
        )
        self.assertEqual(resultado, RESULTADO_OK)
        self.assertEqual(self._estado_job("evt-1"), "PRINTED")

    def test_ack_repetido_idempotente(self):
        job = self._reclamar()
        self.repo.confirmar_ack(job_id=job["id"], station_id="st1", lease_token="tok1", fecha="2026-09-05 19:00:05")
        resultado = self.repo.confirmar_ack(
            job_id=job["id"], station_id="st1", lease_token="tok1", fecha="2026-09-05 19:00:07"
        )
        self.assertEqual(resultado, RESULTADO_OK_IDEMPOTENTE)

    def test_token_incorrecto_rechazado(self):
        job = self._reclamar()
        resultado = self.repo.confirmar_ack(
            job_id=job["id"], station_id="st1", lease_token="token-equivocado", fecha="2026-09-05 19:00:05"
        )
        self.assertEqual(resultado, RESULTADO_LEASE_INVALIDO)
        self.assertEqual(self._estado_job("evt-1"), "LEASED")

    def test_station_incorrecta_rechazada(self):
        job = self._reclamar()
        resultado = self.repo.confirmar_ack(
            job_id=job["id"], station_id="otra-estacion", lease_token="tok1", fecha="2026-09-05 19:00:05"
        )
        self.assertEqual(resultado, RESULTADO_LEASE_INVALIDO)

    def test_job_inexistente(self):
        resultado = self.repo.confirmar_ack(job_id=999999, station_id="st1", lease_token="tok1", fecha="x")
        self.assertEqual(resultado, RESULTADO_NO_ENCONTRADO)

    def test_printed_at_y_printed_by_station_quedan_guardados(self):
        job = self._reclamar()
        self.repo.confirmar_ack(job_id=job["id"], station_id="st1", lease_token="tok1", fecha="2026-09-05 19:00:05")
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT printed_at, printed_by_station FROM print_jobs WHERE id=?", (job["id"],))
        printed_at, printed_by = cursor.fetchone()
        conn.close()
        self.assertEqual(printed_at, "2026-09-05 19:00:05")
        self.assertEqual(printed_by, "st1")


class LiberarJobTest(PrintQueueInfraTest):
    def _reclamar(self, event_key="evt-1"):
        self._crear_job(event_key)
        return self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )

    def test_fallo_no_marca_printed_y_vuelve_a_pending(self):
        job = self._reclamar()
        resultado = self.repo.liberar_job(
            job_id=job["id"], station_id="st1", lease_token="tok1",
            error_sanitizado="puerto ocupado", fecha="2026-09-05 19:00:05",
        )
        self.assertEqual(resultado, RESULTADO_OK)
        self.assertEqual(self._estado_job("evt-1"), ESTADO_PENDING)

    def test_job_liberado_vuelve_a_ser_elegible(self):
        job = self._reclamar()
        self.repo.liberar_job(
            job_id=job["id"], station_id="st1", lease_token="tok1",
            error_sanitizado="puerto ocupado", fecha="2026-09-05 19:00:05",
        )
        job_recuperado = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st2", lease_token="tok2",
            lease_expires_texto="2026-09-05 19:10:00", ahora_texto="2026-09-05 19:00:10",
        )
        self.assertIsNotNone(job_recuperado)
        self.assertEqual(job_recuperado["event_key"], "evt-1")

    def test_attempt_count_se_incrementa_en_cada_reclamo(self):
        job = self._reclamar()
        self.repo.liberar_job(
            job_id=job["id"], station_id="st1", lease_token="tok1",
            error_sanitizado="x", fecha="2026-09-05 19:00:05",
        )
        self.repo.reclamar_job(
            roles=("COCINA",), station_id="st2", lease_token="tok2",
            lease_expires_texto="2026-09-05 19:10:00", ahora_texto="2026-09-05 19:00:10",
        )
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT attempt_count, last_error FROM print_jobs WHERE id=?", (job["id"],))
        attempt_count, last_error = cursor.fetchone()
        conn.close()
        self.assertEqual(attempt_count, 2)  # 1er reclamo + 2do reclamo
        self.assertEqual(last_error, "x")

    def test_lease_invalido_no_libera(self):
        job = self._reclamar()
        resultado = self.repo.liberar_job(
            job_id=job["id"], station_id="st1", lease_token="token-equivocado",
            error_sanitizado="x", fecha="2026-09-05 19:00:05",
        )
        self.assertEqual(resultado, RESULTADO_LEASE_INVALIDO)
        self.assertEqual(self._estado_job("evt-1"), "LEASED")

    def test_job_inexistente(self):
        resultado = self.repo.liberar_job(
            job_id=999999, station_id="st1", lease_token="tok1", error_sanitizado="x", fecha="x"
        )
        self.assertEqual(resultado, RESULTADO_NO_ENCONTRADO)


class ContarPendientesTest(PrintQueueInfraTest):
    def test_cuenta_por_rol(self):
        self._crear_job("evt-1", required_role="COCINA")
        self._crear_job("evt-2", required_role="COCINA")
        self._crear_job("evt-3", required_role="RECIBO_MESA")

        conteo = self.repo.contar_pendientes_por_rol(("COCINA", "RECIBO_MESA"), "2026-09-05 19:00:00")
        self.assertEqual(conteo, {"COCINA": 2, "RECIBO_MESA": 1})

    def test_no_cuenta_jobs_printed(self):
        self._crear_job("evt-1", required_role="COCINA")
        job = self.repo.reclamar_job(
            roles=("COCINA",), station_id="st1", lease_token="tok1",
            lease_expires_texto="2026-09-05 19:05:00", ahora_texto="2026-09-05 19:00:00",
        )
        self.repo.confirmar_ack(job_id=job["id"], station_id="st1", lease_token="tok1", fecha="2026-09-05 19:00:05")

        conteo = self.repo.contar_pendientes_por_rol(("COCINA",), "2026-09-05 19:00:10")
        self.assertEqual(conteo, {"COCINA": 0})

    def test_roles_vacios(self):
        self.assertEqual(self.repo.contar_pendientes_por_rol((), "2026-09-05 19:00:00"), {})


if __name__ == "__main__":
    unittest.main()
