import unittest

from app.domain.sales.item_builder import (
    ErrorConstruccionItem,
    construir_items_orden,
)
from app.domain.sales.item_descriptions import deserializar_indicacion
import web_app


def config_neko():
    return {
        "combos_personales": web_app.COMBOS_PERSONALES,
        "acompanantes_combo": web_app.ACOMPANANTES_COMBO,
        "bebidas_combo": web_app.BEBIDAS_COMBO,
        "combos_cantidad_acompanantes": web_app.COMBOS_CANTIDAD_ACOMPANANTES,
        "promociones_neko": web_app.PROMOCIONES_NEKO,
        "promociones_con_pollo": web_app.PROMOCIONES_CON_POLLO,
        "pollos_promocion": web_app.POLLOS_PROMOCION,
        "arroces_promocion": web_app.ARROCES_PROMOCION,
        "promo_extra_lumpias_nombre": web_app.PROMO_EXTRA_LUMPIAS_NOMBRE,
        "promo_extra_lumpias_precio": web_app.PROMO_EXTRA_LUMPIAS_PRECIO,
    }


class ItemBuilderTest(unittest.TestCase):
    def test_builds_simple_product_without_indication_or_extra_items(self):
        resultado = construir_items_orden(
            producto_nombre="Neko Dúo Triple",
            producto_precio=9.0,
            categoria_nombre="Neko Dúo",
            **config_neko(),
        )

        self.assertEqual(resultado.item_principal.producto, "Neko Dúo Triple")
        self.assertEqual(resultado.item_principal.precio, 9.0)
        self.assertEqual(resultado.item_principal.indicacion, "")
        self.assertEqual(resultado.items_extra, ())
        self.assertEqual(resultado.precio_total, 9.0)

    def test_preserves_original_product_name_without_stripping(self):
        resultado = construir_items_orden(
            producto_nombre="  Producto con espacios  ",
            producto_precio=4.0,
            categoria_nombre="Favoritos de Neko",
            **config_neko(),
        )

        self.assertEqual(resultado.item_principal.producto, "  Producto con espacios  ")

    def test_builds_refresco_with_normalized_indication(self):
        resultado = construir_items_orden(
            producto_nombre="Refresco 1 Lt",
            producto_precio=1.2,
            categoria_nombre="Bebidas",
            sabor="coca cola",
            **config_neko(),
        )

        self.assertEqual(resultado.item_principal.indicacion, "Sabor: Coca Cola")
        self.assertEqual(resultado.precio_total, 1.2)

    def test_builds_combo_with_acompanantes_and_bebida_json(self):
        resultado = construir_items_orden(
            producto_nombre="Neko Combo 2",
            producto_precio=6.0,
            categoria_nombre="Neko Combos",
            acompanantes=["Pollo BBQ", "Lumpia"],
            bebida="Frescolita",
            **config_neko(),
        )

        datos = deserializar_indicacion(resultado.item_principal.indicacion)
        self.assertEqual(datos["tipo"], "combo")
        self.assertEqual(datos["producto"], "combo2")
        self.assertEqual(datos["acompanantes"], ["Pollo BBQ", "Lumpia"])
        self.assertEqual(datos["bebida"], "Frescolita")
        self.assertEqual(resultado.precio_total, 6.0)

    def test_builds_promocion_with_extra_lumpias_and_total_price(self):
        resultado = construir_items_orden(
            producto_nombre="Familiar",
            producto_precio=20.0,
            categoria_nombre="Promociones Neko",
            pollo="Pollo BBQ/Agridulce",
            arroces=["Triple"],
            sabores=["chinotto"],
            extra_lumpias="1",
            **config_neko(),
        )

        datos = deserializar_indicacion(resultado.item_principal.indicacion)
        self.assertEqual(datos["tipo"], "promocion")
        self.assertEqual(datos["producto"], "familiar")
        self.assertEqual(datos["pollo"], "Pollo BBQ/Agridulce")
        self.assertEqual(datos["arroces"], ["Triple"])
        self.assertEqual(datos["bebidas"], ["Chinotto"])
        self.assertEqual(len(resultado.items_extra), 1)
        self.assertEqual(resultado.items_extra[0].producto, "Promo extra: Ración de Lumpias")
        self.assertEqual(resultado.items_extra[0].precio, 3.0)
        self.assertEqual(resultado.items_extra[0].indicacion, "Agregado con: Familiar")
        self.assertEqual(resultado.precio_total, 23.0)

    def test_rejects_invalid_combo_configuration(self):
        with self.assertRaises(ErrorConstruccionItem) as ctx:
            construir_items_orden(
                producto_nombre="Neko Combo 1",
                producto_precio=5.3,
                categoria_nombre="Neko Combos",
                acompanantes=["No existe"],
                bebida="Coca Cola",
                **config_neko(),
            )

        self.assertEqual(
            ctx.exception.mensaje,
            "Debes seleccionar todos los acompañantes validos para este combo",
        )
        self.assertEqual(ctx.exception.status_code, 200)

    def test_rejects_invalid_combo_bebida(self):
        with self.assertRaises(ErrorConstruccionItem) as ctx:
            construir_items_orden(
                producto_nombre="Neko Combo 1",
                producto_precio=5.3,
                categoria_nombre="Neko Combos",
                acompanantes=["Pollo BBQ"],
                bebida="Malta",
                **config_neko(),
            )

        self.assertEqual(ctx.exception.mensaje, "Debes seleccionar una bebida valida para este combo")

    def test_rejects_invalid_promocion_configuration(self):
        with self.assertRaises(ErrorConstruccionItem) as ctx:
            construir_items_orden(
                producto_nombre="Familiar",
                producto_precio=20.0,
                categoria_nombre="Promociones Neko",
                pollo="Pollo BBQ",
                arroces=["Triple"],
                sabores=[],
                **config_neko(),
            )

        self.assertEqual(ctx.exception.mensaje, "Debes seleccionar todos los sabores de refresco")

    def test_rejects_invalid_required_pollo_for_promocion(self):
        with self.assertRaises(ErrorConstruccionItem) as ctx:
            construir_items_orden(
                producto_nombre="Familiar",
                producto_precio=20.0,
                categoria_nombre="Promociones Neko",
                pollo="Pollo Inventado",
                arroces=["Triple"],
                sabores=["Chinotto"],
                **config_neko(),
            )

        self.assertEqual(
            ctx.exception.mensaje,
            "Debes seleccionar un tipo de pollo valido para esta promocion",
        )

    def test_rejects_invalid_extra_lumpias_value(self):
        with self.assertRaises(ErrorConstruccionItem) as ctx:
            construir_items_orden(
                producto_nombre="Familiar",
                producto_precio=20.0,
                categoria_nombre="Promociones Neko",
                pollo="Pollo BBQ",
                arroces=["Triple"],
                sabores=["Chinotto"],
                extra_lumpias="si",
                **config_neko(),
            )

        self.assertEqual(ctx.exception.mensaje, "La selecci\u00f3n del extra de lumpias no es valida")

    def test_rejects_legacy_delivery_product_with_http_status_hint(self):
        with self.assertRaises(ErrorConstruccionItem) as ctx:
            construir_items_orden(
                producto_nombre="Delivery 3",
                producto_precio=3.0,
                categoria_nombre="Delivery",
                **config_neko(),
            )

        self.assertEqual(
            ctx.exception.mensaje,
            "El delivery ahora se registra desde el campo Delivery de la orden.",
        )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
