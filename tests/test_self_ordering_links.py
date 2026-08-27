import datetime
import unittest
from unittest import mock

from app.application.self_ordering import links as links_module
from app.application.self_ordering.links import (
    CanalSelfOrderingInvalido,
    ESTADO_LINK_ACTIVO,
    ESTADO_LINK_EXPIRADO,
    ESTADO_LINK_INEXISTENTE,
    ESTADO_LINK_REVOCADO,
    MesaSelfOrderingOcupada,
    OrdenSelfOrderingNoExiste,
    OrdenSelfOrderingRequerida,
    crear_self_order_link,
    obtener_o_crear_link_mesa,
    revocar_self_order_link,
    validar_self_order_link,
)
from app.infrastructure.database.self_ordering_links import SqlSelfOrderLinkRepository
from tests.support_env import TEST_DB, cleanup_test_db, import_web_app


web_app = import_web_app()
REAL_DATETIME = datetime.datetime


class SelfOrderingLinksTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cleanup_test_db()

    def setUp(self):
        web_app.init_db()
        self._clear_data()
        self.repository = SqlSelfOrderLinkRepository(web_app.get_connection, web_app.obtener_ultimo_id)

    def _clear_data(self):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        for table in ("self_order_request_items", "self_order_requests", "self_order_links", "orden_items", "ordenes"):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _fixed_now(self):
        return datetime.datetime(2026, 8, 25, 10, 0, 0)

    def _patch_default_now(self, fixed_now):
        class FakeDateTime(REAL_DATETIME):
            observed_tz = None

            @classmethod
            def now(cls, tz=None):
                cls.observed_tz = tz
                if tz is None:
                    return fixed_now
                return tz.localize(fixed_now)

            @classmethod
            def strptime(cls, date_string, date_format):
                return REAL_DATETIME.strptime(date_string, date_format)

        return mock.patch.object(links_module.datetime, "datetime", FakeDateTime), FakeDateTime

    def _create_order(self, referencia="mesa:1", estado="abierta", cierre_id=None):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ordenes (
                numero_orden, fecha_hora, fecha, tipo, referencia, cliente, estado, usuario_id, cierre_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "2026-08-25 10:00:00",
                "2026-08-25",
                "Mesa",
                referencia,
                "Cliente",
                estado,
                None,
                cierre_id,
            ),
        )
        orden_id = web_app.obtener_ultimo_id(cursor, "ordenes")
        conn.commit()
        conn.close()
        return orden_id

    def _insert_link(self, orden_id, token, mesa_clave=None, canal="mesa", estado="activo"):
        conn = web_app.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO self_order_links (
                orden_id, token, canal, estado, fecha_creacion, fecha_expiracion, mesa_clave
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (orden_id, token, canal, estado, "2026-08-25 10:00:00", None, mesa_clave),
        )
        link_id = web_app.obtener_ultimo_id(cursor, "self_order_links")
        conn.commit()
        conn.close()
        return link_id

    def test_creates_table_link_for_real_order(self):
        orden_id = self._create_order()

        link = crear_self_order_link(
            self.repository,
            canal="mesa",
            orden_id=orden_id,
            ahora_fn=self._fixed_now,
        )

        self.assertEqual(link.orden_id, orden_id)
        self.assertEqual(link.canal, "mesa")
        self.assertEqual(link.estado, "activo")
        self.assertEqual(link.fecha_creacion, "2026-08-25 10:00:00")

    def test_creates_link_without_injected_now_uses_caracas_time(self):
        patcher, fake_datetime = self._patch_default_now(REAL_DATETIME(2026, 8, 25, 11, 30, 0))
        with patcher:
            link = crear_self_order_link(self.repository, canal="pickup")

        self.assertEqual(link.fecha_creacion, "2026-08-25 11:30:00")
        self.assertEqual(fake_datetime.observed_tz.zone, "America/Caracas")

    def test_rejects_mesa_link_for_missing_order(self):
        with self.assertRaises(OrdenSelfOrderingRequerida):
            crear_self_order_link(
                self.repository,
                canal="mesa",
                orden_id=None,
                ahora_fn=self._fixed_now,
            )

    def test_rejects_mesa_link_for_unknown_order(self):
        with self.assertRaises(OrdenSelfOrderingNoExiste):
            crear_self_order_link(
                self.repository,
                canal="mesa",
                orden_id=9999,
                ahora_fn=self._fixed_now,
            )

    def test_creates_pickup_without_order(self):
        link = crear_self_order_link(
            self.repository,
            canal="pickup",
            orden_id=None,
            ahora_fn=self._fixed_now,
        )

        self.assertIsNone(link.orden_id)
        self.assertEqual(link.canal, "pickup")
        self.assertEqual(link.estado, "activo")

    def test_creates_delivery_without_order(self):
        link = crear_self_order_link(
            self.repository,
            canal="delivery",
            orden_id=None,
            ahora_fn=self._fixed_now,
        )

        self.assertIsNone(link.orden_id)
        self.assertEqual(link.canal, "delivery")
        self.assertEqual(link.estado, "activo")

    def test_creates_whatsapp_without_order(self):
        link = crear_self_order_link(
            self.repository,
            canal="whatsapp",
            orden_id=None,
            ahora_fn=self._fixed_now,
        )

        self.assertIsNone(link.orden_id)
        self.assertEqual(link.canal, "whatsapp")
        self.assertEqual(link.estado, "activo")

    def test_rejects_invalid_channel(self):
        with self.assertRaises(CanalSelfOrderingInvalido):
            crear_self_order_link(self.repository, canal="mostrador", ahora_fn=self._fixed_now)

    def test_generates_distinct_tokens_in_multiple_creations(self):
        tokens = {
            crear_self_order_link(self.repository, canal="pickup", ahora_fn=self._fixed_now).token
            for _ in range(5)
        }

        self.assertEqual(len(tokens), 5)

    def test_token_is_sufficiently_not_predictable(self):
        orden_id = self._create_order()

        link = crear_self_order_link(
            self.repository,
            canal="mesa",
            orden_id=orden_id,
            ahora_fn=self._fixed_now,
        )

        self.assertGreaterEqual(len(link.token), 32)
        self.assertNotEqual(link.token, str(orden_id))
        self.assertFalse(link.token.startswith(f"{orden_id}-"))
        self.assertFalse(link.token.isdigit())

    def test_active_token_is_valid(self):
        link = crear_self_order_link(self.repository, canal="pickup", ahora_fn=self._fixed_now)

        resultado = validar_self_order_link(self.repository, link.token, ahora_fn=self._fixed_now)

        self.assertTrue(resultado.valido)
        self.assertEqual(resultado.estado, ESTADO_LINK_ACTIVO)
        self.assertEqual(resultado.link.token, link.token)

    def test_missing_token_is_invalid(self):
        resultado = validar_self_order_link(self.repository, "no-existe", ahora_fn=self._fixed_now)

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.estado, ESTADO_LINK_INEXISTENTE)
        self.assertIsNone(resultado.link)

    def test_revoked_token_is_invalid(self):
        link = crear_self_order_link(self.repository, canal="pickup", ahora_fn=self._fixed_now)
        revocar_self_order_link(self.repository, link.token)

        resultado = validar_self_order_link(self.repository, link.token, ahora_fn=self._fixed_now)

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.estado, ESTADO_LINK_REVOCADO)

    def test_expired_token_is_invalid_without_mutating_link(self):
        link = crear_self_order_link(
            self.repository,
            canal="delivery",
            fecha_expiracion="2026-08-25 09:59:59",
            ahora_fn=self._fixed_now,
        )

        resultado = validar_self_order_link(self.repository, link.token, ahora_fn=self._fixed_now)
        persisted = self.repository.buscar_por_token(link.token)

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.estado, ESTADO_LINK_EXPIRADO)
        self.assertEqual(persisted.estado, ESTADO_LINK_ACTIVO)

    def test_default_validation_uses_caracas_time_for_expiration(self):
        patcher, fake_datetime = self._patch_default_now(REAL_DATETIME(2026, 8, 25, 12, 0, 0))
        link = crear_self_order_link(
            self.repository,
            canal="delivery",
            fecha_expiracion="2026-08-25 11:59:59",
            ahora_fn=self._fixed_now,
        )

        with patcher:
            resultado = validar_self_order_link(self.repository, link.token)

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.estado, ESTADO_LINK_EXPIRADO)
        self.assertEqual(fake_datetime.observed_tz.zone, "America/Caracas")

    def test_revokes_token(self):
        link = crear_self_order_link(self.repository, canal="whatsapp", ahora_fn=self._fixed_now)

        self.assertTrue(revocar_self_order_link(self.repository, link.token))

        persisted = self.repository.buscar_por_token(link.token)
        self.assertEqual(persisted.estado, ESTADO_LINK_REVOCADO)

    def test_regenerates_token_when_unique_collision_happens(self):
        crear_self_order_link(
            self.repository,
            canal="pickup",
            ahora_fn=self._fixed_now,
            token_generator=lambda: "token-repetido",
        )
        tokens = iter(("token-repetido", "token-nuevo-seguro-con-suficiente-entropia"))

        link = crear_self_order_link(
            self.repository,
            canal="pickup",
            ahora_fn=self._fixed_now,
            token_generator=lambda: next(tokens),
        )

        self.assertEqual(link.token, "token-nuevo-seguro-con-suficiente-entropia")

    def test_permanent_table_link_cannot_move_from_another_open_order(self):
        first_order = self._create_order(referencia="mesa:3")
        second_order = self._create_order(referencia="mesa:3")
        link = crear_self_order_link(
            self.repository,
            canal="mesa",
            orden_id=first_order,
            ahora_fn=self._fixed_now,
        )

        with self.assertRaises(MesaSelfOrderingOcupada):
            obtener_o_crear_link_mesa(self.repository, second_order, ahora_fn=self._fixed_now)

        persisted = self.repository.buscar_por_token(link.token)
        self.assertEqual(persisted.orden_id, first_order)

    def test_table_key_unique_collision_reuses_existing_permanent_link(self):
        orden_id = self._create_order(referencia="mesa:7")
        self._insert_link(orden_id, "token-mesa-siete", mesa_clave="mesa:7")

        link = crear_self_order_link(
            self.repository,
            canal="mesa",
            orden_id=orden_id,
            ahora_fn=self._fixed_now,
            token_generator=lambda: "token-nuevo-no-usado",
        )

        self.assertEqual(link.token, "token-mesa-siete")
        self.assertEqual(link.mesa_clave, "mesa:7")

    def test_adopts_historical_table_link_without_changing_token(self):
        orden_id = self._create_order(referencia="mesa:8")
        self._insert_link(orden_id, "token-historico", mesa_clave=None)

        link, creado = obtener_o_crear_link_mesa(self.repository, orden_id, ahora_fn=self._fixed_now)

        self.assertFalse(creado)
        self.assertEqual(link.token, "token-historico")
        self.assertEqual(link.mesa_clave, "mesa:8")
        self.assertEqual(self.repository.buscar_por_token("token-historico").mesa_clave, "mesa:8")


if __name__ == "__main__":
    unittest.main()
