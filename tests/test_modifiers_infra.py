import os
import tempfile
import unittest

from app.infrastructure.database.modifiers import (
    alternar_activa_opcion_modificador,
    alternar_activo_grupo_modificador,
    alternar_disponible_opcion_modificador,
    asociar_grupo_a_producto,
    crear_grupo_modificador,
    crear_opcion_modificador,
    crear_tablas_modificadores,
    desasociar_grupo_de_producto,
    listar_grupos_de_producto,
    listar_grupos_de_producto_admin,
    listar_grupos_modificadores_admin,
    listar_grupos_por_producto_ids,
    listar_opciones_de_grupo_admin,
)
from tests.support_env import import_web_app

web_app = import_web_app()

_PRIVATE_DB_PATH = os.path.join(
    tempfile.gettempdir(), f"neko_pos_test_modifiers_infra_{os.getpid()}.db"
)


class ModifiersInfraTest(unittest.TestCase):
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
        web_app.init_db()
        crear_tablas_modificadores(web_app.get_connection, web_app.pk_autoincrement_sql)
        self._clear_data()

    def _conn(self):
        return web_app.get_connection()

    def _clear_data(self):
        conn = self._conn()
        cursor = conn.cursor()
        for table in (
            "productos",
            "categorias",
            "producto_grupos_modificadores",
            "opciones_modificador",
            "grupos_modificadores",
        ):
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _create_product(self, nombre, precio=1.0):
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO productos (nombre, precio, activo) VALUES (?, ?, 1)", (nombre, precio))
        producto_id = web_app.obtener_ultimo_id(cursor, "productos")
        conn.commit()
        conn.close()
        return producto_id

    def _crear_grupo_jugo(self, cursor, **kwargs):
        defaults = dict(nombre="Sabor", obligatorio=True, seleccion_multiple=False, minimo=1, maximo=1, orden=0)
        defaults.update(kwargs)
        return crear_grupo_modificador(cursor, web_app.obtener_ultimo_id, **defaults)

    def test_create_group_and_options_then_list_for_product(self):
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural", 2.0)

        grupo_id = self._crear_grupo_jugo(cursor)
        crear_opcion_modificador(cursor, web_app.obtener_ultimo_id, grupo_id=grupo_id, nombre="Fresa", orden=0)
        crear_opcion_modificador(cursor, web_app.obtener_ultimo_id, grupo_id=grupo_id, nombre="Mora", orden=1)
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        conn.commit()

        grupos = listar_grupos_de_producto(cursor, producto_id)
        conn.close()

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].nombre, "Sabor")
        self.assertEqual([o.nombre for o in grupos[0].opciones], ["Fresa", "Mora"])

    def test_inactive_group_excluded_from_order_taking_list(self):
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural")
        grupo_id = self._crear_grupo_jugo(cursor)
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        alternar_activo_grupo_modificador(cursor, grupo_id, False)
        conn.commit()

        grupos = listar_grupos_de_producto(cursor, producto_id)
        conn.close()

        self.assertEqual(grupos, [])

    def test_inactive_option_excluded_but_group_still_listed(self):
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural")
        grupo_id = self._crear_grupo_jugo(cursor)
        opcion_id = crear_opcion_modificador(cursor, web_app.obtener_ultimo_id, grupo_id=grupo_id, nombre="Fresa")
        crear_opcion_modificador(cursor, web_app.obtener_ultimo_id, grupo_id=grupo_id, nombre="Mora")
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        alternar_activa_opcion_modificador(cursor, opcion_id, False)
        conn.commit()

        grupos = listar_grupos_de_producto(cursor, producto_id)
        conn.close()

        self.assertEqual(len(grupos), 1)
        self.assertEqual([o.nombre for o in grupos[0].opciones], ["Mora"])

    def test_sold_out_option_still_listed_but_flagged_unavailable(self):
        """Mora agotada sigue apareciendo (para que el POS pueda
        mostrarla como agotada), pero con disponible=False -- la
        validacion de dominio es quien la rechaza, no el repositorio."""
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural")
        grupo_id = self._crear_grupo_jugo(cursor)
        opcion_id = crear_opcion_modificador(cursor, web_app.obtener_ultimo_id, grupo_id=grupo_id, nombre="Mora")
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        alternar_disponible_opcion_modificador(cursor, opcion_id, False)
        conn.commit()

        grupos = listar_grupos_de_producto(cursor, producto_id)
        conn.close()

        self.assertEqual(len(grupos[0].opciones), 1)
        self.assertFalse(grupos[0].opciones[0].disponible)

    def test_disassociating_group_removes_it_from_product_without_deleting_group(self):
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural")
        grupo_id = self._crear_grupo_jugo(cursor)
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        conn.commit()

        desasociar_grupo_de_producto(cursor, producto_id, grupo_id)
        conn.commit()

        grupos_producto = listar_grupos_de_producto(cursor, producto_id)
        grupos_admin = listar_grupos_modificadores_admin(cursor)
        conn.close()

        self.assertEqual(grupos_producto, [])
        self.assertEqual(len(grupos_admin), 1)  # el grupo sigue existiendo, solo se desasocio

    def test_listar_grupos_por_producto_ids_batches_multiple_products(self):
        conn = self._conn()
        cursor = conn.cursor()
        jugo_id = self._create_product("Jugo Natural")
        cerveza_id = self._create_product("Cerveza Polar")

        grupo_sabor = self._crear_grupo_jugo(cursor)
        crear_opcion_modificador(cursor, web_app.obtener_ultimo_id, grupo_id=grupo_sabor, nombre="Fresa")
        asociar_grupo_a_producto(cursor, jugo_id, grupo_sabor)
        conn.commit()

        mapa = listar_grupos_por_producto_ids(cursor, [jugo_id, cerveza_id])
        conn.close()

        self.assertIn(jugo_id, mapa)
        self.assertNotIn(cerveza_id, mapa)
        self.assertEqual(mapa[jugo_id][0].nombre, "Sabor")

    def test_listar_grupos_por_producto_ids_empty_list_returns_empty_dict(self):
        conn = self._conn()
        cursor = conn.cursor()
        self.assertEqual(listar_grupos_por_producto_ids(cursor, []), {})
        conn.close()

    def test_admin_listing_includes_inactive_groups_and_tracks_product_association(self):
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural")
        grupo_id = self._crear_grupo_jugo(cursor)
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        alternar_activo_grupo_modificador(cursor, grupo_id, False)
        conn.commit()

        grupos_admin = listar_grupos_modificadores_admin(cursor)
        opciones_admin = listar_opciones_de_grupo_admin(cursor, grupo_id)
        asociaciones = listar_grupos_de_producto_admin(cursor, producto_id)
        conn.close()

        self.assertEqual(len(grupos_admin), 1)
        self.assertEqual(grupos_admin[0][2], 0)  # columna activo
        self.assertEqual(opciones_admin, [])
        self.assertEqual(len(asociaciones), 1)

    def test_associating_same_group_twice_does_not_duplicate(self):
        conn = self._conn()
        cursor = conn.cursor()
        producto_id = self._create_product("Jugo Natural")
        grupo_id = self._crear_grupo_jugo(cursor)
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        asociar_grupo_a_producto(cursor, producto_id, grupo_id)
        conn.commit()

        asociaciones = listar_grupos_de_producto_admin(cursor, producto_id)
        conn.close()

        self.assertEqual(len(asociaciones), 1)


if __name__ == "__main__":
    unittest.main()
