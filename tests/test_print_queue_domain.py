"""Tests de app/domain/sales/print_queue.py: roles, perfiles, mapeo
tipo de orden -> rol de recibo. Puro, sin base de datos."""

import unittest

from app.domain.sales.print_queue import (
    PERFIL_COCINA,
    PERFIL_PERSONALIZADO,
    PERFIL_SALON,
    PERFIL_TODO,
    ROL_COCINA,
    ROL_RECIBO_DELIVERY,
    ROL_RECIBO_MESA,
    ROL_RECIBO_PICKUP,
    ROLES_VALIDOS,
    TipoOrdenDesconocido,
    rol_recibo_por_tipo_orden,
    roles_por_perfil,
    roles_validos,
)


class RolReciboPorTipoOrdenTest(unittest.TestCase):
    def test_mesa(self):
        self.assertEqual(rol_recibo_por_tipo_orden("Mesa"), ROL_RECIBO_MESA)

    def test_delivery(self):
        self.assertEqual(rol_recibo_por_tipo_orden("Delivery"), ROL_RECIBO_DELIVERY)

    def test_para_llevar_es_pickup(self):
        # El <option> visible dice "Pick Up" pero value="Para llevar":
        # ese es el valor REAL guardado en ordenes.tipo.
        self.assertEqual(rol_recibo_por_tipo_orden("Para llevar"), ROL_RECIBO_PICKUP)

    def test_case_insensitive(self):
        self.assertEqual(rol_recibo_por_tipo_orden("mesa"), ROL_RECIBO_MESA)
        self.assertEqual(rol_recibo_por_tipo_orden("DELIVERY"), ROL_RECIBO_DELIVERY)
        self.assertEqual(rol_recibo_por_tipo_orden("para llevar"), ROL_RECIBO_PICKUP)

    def test_tipo_pick_up_literal_no_es_valido(self):
        # "Pick Up" (el texto visible) NO es el valor real; si algo
        # cambiara rio arriba y empezara a llegar asi, no debe adivinar.
        with self.assertRaises(TipoOrdenDesconocido):
            rol_recibo_por_tipo_orden("Pick Up")

    def test_tipo_desconocido_lanza(self):
        with self.assertRaises(TipoOrdenDesconocido):
            rol_recibo_por_tipo_orden("otro")

    def test_tipo_vacio_lanza(self):
        with self.assertRaises(TipoOrdenDesconocido):
            rol_recibo_por_tipo_orden("")

    def test_tipo_none_lanza(self):
        with self.assertRaises(TipoOrdenDesconocido):
            rol_recibo_por_tipo_orden(None)


class RolesValidosTest(unittest.TestCase):
    def test_todos_los_roles_conocidos_pasan(self):
        self.assertEqual(
            roles_validos(["COCINA", "RECIBO_MESA", "RECIBO_PICKUP", "RECIBO_DELIVERY"]),
            ("COCINA", "RECIBO_MESA", "RECIBO_PICKUP", "RECIBO_DELIVERY"),
        )

    def test_rol_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            roles_validos(["COCINA", "ROL_INVENTADO"])

    def test_quita_duplicados_preservando_orden(self):
        self.assertEqual(roles_validos(["COCINA", "COCINA", "RECIBO_MESA"]), ("COCINA", "RECIBO_MESA"))

    def test_lista_vacia(self):
        self.assertEqual(roles_validos([]), ())

    def test_none(self):
        self.assertEqual(roles_validos(None), ())

    def test_ignora_strings_vacios(self):
        self.assertEqual(roles_validos(["COCINA", "", "  "]), ("COCINA",))

    def test_no_es_sql_injectable_solo_compara_contra_enum(self):
        with self.assertRaises(ValueError):
            roles_validos(["COCINA'; DROP TABLE print_jobs; --"])


class RolesPorPerfilTest(unittest.TestCase):
    def test_todo_tiene_los_cuatro_roles(self):
        self.assertEqual(set(roles_por_perfil(PERFIL_TODO)), set(ROLES_VALIDOS))

    def test_cocina_no_incluye_recibo_mesa(self):
        roles = set(roles_por_perfil(PERFIL_COCINA))
        self.assertIn(ROL_COCINA, roles)
        self.assertIn(ROL_RECIBO_PICKUP, roles)
        self.assertIn(ROL_RECIBO_DELIVERY, roles)
        self.assertNotIn(ROL_RECIBO_MESA, roles)

    def test_salon_solo_recibo_mesa(self):
        self.assertEqual(set(roles_por_perfil(PERFIL_SALON)), {ROL_RECIBO_MESA})

    def test_personalizado_usa_los_roles_dados(self):
        self.assertEqual(
            set(roles_por_perfil(PERFIL_PERSONALIZADO, roles_personalizados=[ROL_COCINA])),
            {ROL_COCINA},
        )

    def test_personalizado_sin_roles_es_vacio(self):
        self.assertEqual(roles_por_perfil(PERFIL_PERSONALIZADO), ())

    def test_perfil_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            roles_por_perfil("INVENTADO")


if __name__ == "__main__":
    unittest.main()
