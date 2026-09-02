import unittest

from app.domain.sales.order_states import (
    orden_archivada,
    orden_cerrada,
    puede_editar_indicacion_item,
    puede_eliminar_orden,
    puede_modificar_orden,
)


class SalesOrderStatesTest(unittest.TestCase):
    def test_order_is_archived_when_cierre_id_is_present(self):
        self.assertFalse(orden_archivada(None))
        self.assertTrue(orden_archivada(1))
        self.assertTrue(orden_archivada(0))

    def test_order_is_closed_only_for_cerrada_state(self):
        for estado in ("abierta", "en cocina", "listo"):
            with self.subTest(estado=estado):
                self.assertFalse(orden_cerrada(estado))
        self.assertTrue(orden_cerrada("cerrada"))

    def test_general_modification_allows_non_closed_unarchived_orders(self):
        for estado in ("abierta", "en cocina", "listo"):
            with self.subTest(estado=estado):
                self.assertTrue(puede_modificar_orden(estado, None, False))

    def test_general_modification_blocks_archived_orders(self):
        for estado in ("abierta", "en cocina", "listo", "cerrada"):
            with self.subTest(estado=estado):
                self.assertFalse(puede_modificar_orden(estado, 99, True))

    def test_general_modification_blocks_closed_without_emergency(self):
        self.assertFalse(puede_modificar_orden("cerrada", None, False))

    def test_general_modification_allows_closed_with_emergency(self):
        self.assertTrue(puede_modificar_orden("cerrada", None, True))

    def test_item_note_editing_allows_only_open_kitchen_or_closed_emergency(self):
        self.assertTrue(puede_editar_indicacion_item("abierta", None, False))
        self.assertTrue(puede_editar_indicacion_item("en cocina", None, False))
        self.assertFalse(puede_editar_indicacion_item("listo", None, False))
        self.assertFalse(puede_editar_indicacion_item("cerrada", None, False))
        self.assertTrue(puede_editar_indicacion_item("cerrada", None, True))

    def test_item_note_editing_blocks_archived_orders_even_with_emergency(self):
        for estado in ("abierta", "en cocina", "listo", "cerrada"):
            with self.subTest(estado=estado):
                self.assertFalse(puede_editar_indicacion_item(estado, 99, True))

    def test_order_deletion_allows_only_open_or_kitchen_unarchived_orders(self):
        self.assertTrue(puede_eliminar_orden("abierta", None))
        self.assertTrue(puede_eliminar_orden("en cocina", None))
        self.assertFalse(puede_eliminar_orden("listo", None))
        self.assertFalse(puede_eliminar_orden("cerrada", None))

    def test_order_deletion_blocks_archived_orders(self):
        for estado in ("abierta", "en cocina", "listo", "cerrada"):
            with self.subTest(estado=estado):
                self.assertFalse(puede_eliminar_orden(estado, 99))


if __name__ == "__main__":
    unittest.main()
