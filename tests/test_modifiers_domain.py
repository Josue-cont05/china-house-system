import unittest

from app.domain.sales.item_builder import ErrorConstruccionItem
from app.domain.sales.item_descriptions import (
    serializar_indicacion,
    texto_descripcion_modificador_cocina,
    texto_descripcion_modificador_factura,
    texto_descripcion_modificador_orden,
)
from app.domain.sales.modifiers import (
    GrupoModificador,
    OpcionModificador,
    validar_seleccion_modificadores,
)


def opcion(id, nombre, activa=True, disponible=True, precio_adicional=0.0, orden=0):
    return OpcionModificador(
        id=id,
        nombre=nombre,
        activa=activa,
        disponible=disponible,
        precio_adicional=precio_adicional,
        orden=orden,
    )


def grupo(
    id,
    nombre,
    opciones,
    activo=True,
    obligatorio=True,
    seleccion_multiple=False,
    minimo=1,
    maximo=1,
    orden=0,
):
    return GrupoModificador(
        id=id,
        nombre=nombre,
        activo=activo,
        obligatorio=obligatorio,
        seleccion_multiple=seleccion_multiple,
        minimo=minimo,
        maximo=maximo,
        orden=orden,
        opciones=tuple(opciones),
    )


def grupos_jugo_natural():
    sabor = grupo(
        1,
        "Sabor",
        [opcion(10, "Fresa"), opcion(11, "Mora"), opcion(12, "Guanabana"), opcion(13, "Parchita")],
    )
    azucar = grupo(
        2,
        "Azucar",
        [
            opcion(20, "Con azucar"),
            opcion(21, "Sin azucar"),
            opcion(22, "Bajo de azucar"),
            opcion(23, "Mucha azucar"),
        ],
    )
    return [sabor, azucar]


class ValidarSeleccionModificadoresTest(unittest.TestCase):
    def test_valid_selection_returns_groups_and_zero_extra_price(self):
        grupos_resultado, extra = validar_seleccion_modificadores(
            grupos_jugo_natural(), {1: ["Parchita"], 2: ["Sin azucar"]}
        )

        self.assertEqual(
            grupos_resultado,
            [
                {"grupo_id": 1, "nombre": "Sabor", "opciones": ["Parchita"]},
                {"grupo_id": 2, "nombre": "Azucar", "opciones": ["Sin azucar"]},
            ],
        )
        self.assertEqual(extra, 0.0)

    def test_required_group_missing_raises(self):
        with self.assertRaises(ErrorConstruccionItem):
            validar_seleccion_modificadores(grupos_jugo_natural(), {1: ["Parchita"]})

    def test_unknown_option_raises(self):
        with self.assertRaises(ErrorConstruccionItem):
            validar_seleccion_modificadores(
                grupos_jugo_natural(), {1: ["Durian"], 2: ["Sin azucar"]}
            )

    def test_inactive_option_rejected(self):
        grupos = [
            grupo(1, "Sabor", [opcion(10, "Fresa", activa=False), opcion(11, "Mora")]),
        ]
        with self.assertRaises(ErrorConstruccionItem):
            validar_seleccion_modificadores(grupos, {1: ["Fresa"]})

    def test_sold_out_option_rejected(self):
        grupos = [
            grupo(1, "Sabor", [opcion(10, "Fresa"), opcion(11, "Mora", disponible=False)]),
        ]
        with self.assertRaises(ErrorConstruccionItem):
            validar_seleccion_modificadores(grupos, {1: ["Mora"]})

    def test_product_stays_available_when_only_one_option_sold_out(self):
        """Mora agotada -> Jugo Natural sigue disponible, pero Mora no se
        puede elegir; cualquier otro sabor activo si."""
        grupos = [
            grupo(1, "Sabor", [opcion(10, "Fresa"), opcion(11, "Mora", disponible=False)]),
        ]
        grupos_resultado, _ = validar_seleccion_modificadores(grupos, {1: ["Fresa"]})
        self.assertEqual(grupos_resultado[0]["opciones"], ["Fresa"])

    def test_inactive_group_is_ignored_not_required(self):
        grupos = [
            grupo(1, "Sabor", [opcion(10, "Fresa")], activo=False),
        ]
        grupos_resultado, extra = validar_seleccion_modificadores(grupos, {})
        self.assertEqual(grupos_resultado, [])
        self.assertEqual(extra, 0.0)

    def test_optional_group_can_be_skipped(self):
        grupos = [
            grupo(1, "Extra", [opcion(10, "Hielo")], obligatorio=False, minimo=0),
        ]
        grupos_resultado, extra = validar_seleccion_modificadores(grupos, {})
        self.assertEqual(grupos_resultado, [])
        self.assertEqual(extra, 0.0)

    def test_single_selection_group_rejects_multiple_values(self):
        with self.assertRaises(ErrorConstruccionItem):
            validar_seleccion_modificadores(
                grupos_jugo_natural(), {1: ["Fresa", "Mora"], 2: ["Sin azucar"]}
            )

    def test_multiple_selection_group_within_max_is_accepted(self):
        grupos = [
            grupo(
                1,
                "Toppings",
                [opcion(10, "Perlas", precio_adicional=0.5), opcion(11, "Jalea", precio_adicional=0.3)],
                obligatorio=False,
                seleccion_multiple=True,
                minimo=0,
                maximo=2,
            ),
        ]
        grupos_resultado, extra = validar_seleccion_modificadores(grupos, {1: ["Perlas", "Jalea"]})
        self.assertEqual(grupos_resultado[0]["opciones"], ["Perlas", "Jalea"])
        self.assertEqual(extra, 0.8)

    def test_exceeding_maximum_raises(self):
        grupos = [
            grupo(
                1,
                "Toppings",
                [opcion(10, "Perlas"), opcion(11, "Jalea"), opcion(12, "Boba")],
                obligatorio=False,
                seleccion_multiple=True,
                minimo=0,
                maximo=1,
            ),
        ]
        with self.assertRaises(ErrorConstruccionItem):
            validar_seleccion_modificadores(grupos, {1: ["Perlas", "Jalea"]})

    def test_option_with_surcharge_adds_to_price(self):
        grupos = [
            grupo(
                1,
                "Tamano",
                [opcion(10, "Grande", precio_adicional=1.0)],
                obligatorio=True,
                minimo=1,
                maximo=1,
            ),
        ]
        grupos_resultado, extra = validar_seleccion_modificadores(grupos, {1: ["Grande"]})
        self.assertEqual(extra, 1.0)


class ModificadorIndicacionTest(unittest.TestCase):
    def _indicacion_jugo(self):
        return serializar_indicacion(
            {
                "tipo": "modificador",
                "grupos": [
                    {"grupo_id": 1, "nombre": "Sabor", "opciones": ["Parchita"]},
                    {"grupo_id": 2, "nombre": "Azucar", "opciones": ["Sin azucar"]},
                ],
            }
        )

    def test_orden_text_lists_each_selected_option(self):
        texto = texto_descripcion_modificador_orden(self._indicacion_jugo())
        self.assertEqual(texto, "• Parchita\n• Sin azucar")

    def test_cocina_text_lists_each_selected_option(self):
        texto = texto_descripcion_modificador_cocina(self._indicacion_jugo())
        self.assertEqual(texto, "    - Parchita\n    - Sin azucar")

    def test_factura_text_lists_each_selected_option(self):
        texto = texto_descripcion_modificador_factura(self._indicacion_jugo())
        self.assertEqual(texto, "• Parchita\n• Sin azucar")

    def test_returns_empty_for_non_modifier_indicacion(self):
        self.assertEqual(texto_descripcion_modificador_orden(""), "")
        self.assertEqual(texto_descripcion_modificador_orden("Sabor: Fresa"), "")
        self.assertEqual(
            texto_descripcion_modificador_orden(serializar_indicacion({"tipo": "combo"})), ""
        )


if __name__ == "__main__":
    unittest.main()
