MESAS_PERMITIDAS = tuple(range(1, 13))
MESA_CLAVES_PERMITIDAS = tuple(f"mesa:{numero}" for numero in MESAS_PERMITIDAS)


class MesaSelfOrderingInvalida(ValueError):
    pass


def normalizar_mesa_clave(valor) -> str:
    texto = str(valor or "").strip().lower()
    if texto not in MESA_CLAVES_PERMITIDAS:
        raise MesaSelfOrderingInvalida("Mesa invalida. Selecciona una mesa del 1 al 12.")
    return texto


def etiqueta_mesa(mesa_clave) -> str:
    clave = normalizar_mesa_clave(mesa_clave)
    return f"Mesa {clave.split(':', 1)[1]}"


def opciones_mesa_html() -> str:
    return "\n".join(
        f'<option value="mesa:{numero}">Mesa {numero}</option>'
        for numero in MESAS_PERMITIDAS
    )
