"""Tests de station_roles.py (scripts_locales): espejo local (sin
Flask/DB) de app/domain/sales/print_queue.py para roles y perfiles."""

import sys
import unittest
from pathlib import Path

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import station_roles  # noqa: E402


class RolesPorPerfilTest(unittest.TestCase):
    def test_todo_tiene_los_cuatro_roles(self):
        self.assertEqual(
            set(station_roles.roles_por_perfil(station_roles.PERFIL_TODO)),
            set(station_roles.ROLES_VALIDOS),
        )

    def test_cocina_no_incluye_recibo_mesa(self):
        roles = set(station_roles.roles_por_perfil(station_roles.PERFIL_COCINA))
        self.assertIn(station_roles.ROL_COCINA, roles)
        self.assertNotIn(station_roles.ROL_RECIBO_MESA, roles)

    def test_salon_solo_recibo_mesa(self):
        self.assertEqual(
            set(station_roles.roles_por_perfil(station_roles.PERFIL_SALON)),
            {station_roles.ROL_RECIBO_MESA},
        )

    def test_personalizado_usa_los_roles_dados(self):
        self.assertEqual(
            station_roles.roles_por_perfil(
                station_roles.PERFIL_PERSONALIZADO, roles_personalizados=["COCINA"]
            ),
            ("COCINA",),
        )

    def test_perfil_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            station_roles.roles_por_perfil("INVENTADO")

    def test_todas_las_etiquetas_tienen_texto(self):
        for perfil in (
            station_roles.PERFIL_TODO,
            station_roles.PERFIL_COCINA,
            station_roles.PERFIL_SALON,
            station_roles.PERFIL_PERSONALIZADO,
        ):
            self.assertTrue(station_roles.ETIQUETAS_PERFIL[perfil])


class RolesValidosTest(unittest.TestCase):
    def test_roles_conocidos_pasan(self):
        self.assertEqual(
            station_roles.roles_validos(["COCINA", "RECIBO_MESA"]), ("COCINA", "RECIBO_MESA")
        )

    def test_rol_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            station_roles.roles_validos(["ROL_INVENTADO"])

    def test_vacio(self):
        self.assertEqual(station_roles.roles_validos([]), ())
        self.assertEqual(station_roles.roles_validos(None), ())


if __name__ == "__main__":
    unittest.main()
