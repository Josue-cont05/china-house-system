"""
print_queue.py

Reglas puras (sin base de datos) de la cola central de impresion:

- que roles existen y que perfiles de estacion los agrupan;
- a que rol de RECIBO corresponde un tipo de orden (Mesa/Delivery/Para
  llevar);
- validacion de roles (nunca confiar en strings arbitrarios del cliente).

Esto es deliberadamente independiente de web_app.py y de
app/infrastructure/*: se puede usar tanto desde las rutas Flask como
desde el flujo de self-ordering (una capa mas baja que no puede
importar web_app.py) sin crear una dependencia circular.
"""

ROL_COCINA = "COCINA"
ROL_RECIBO_MESA = "RECIBO_MESA"
ROL_RECIBO_PICKUP = "RECIBO_PICKUP"
ROL_RECIBO_DELIVERY = "RECIBO_DELIVERY"

ROLES_VALIDOS = frozenset({ROL_COCINA, ROL_RECIBO_MESA, ROL_RECIBO_PICKUP, ROL_RECIBO_DELIVERY})

# Perfiles amigables para la UI de Neko Local (mision de roles, seccion
# 10): el socio elige un perfil, nunca roles sueltos uno por uno (eso
# queda en "Configuracion avanzada").
PERFIL_TODO = "TODO"
PERFIL_COCINA = "COCINA"
PERFIL_SALON = "SALON"
PERFIL_PERSONALIZADO = "PERSONALIZADO"

PERFILES_ROLES = {
    PERFIL_TODO: frozenset({ROL_COCINA, ROL_RECIBO_MESA, ROL_RECIBO_PICKUP, ROL_RECIBO_DELIVERY}),
    PERFIL_COCINA: frozenset({ROL_COCINA, ROL_RECIBO_PICKUP, ROL_RECIBO_DELIVERY}),
    PERFIL_SALON: frozenset({ROL_RECIBO_MESA}),
}

# job_type: solo para diagnostico/logs (que presentacion usar ya lo
# decide required_role: COCINA -> comanda_presentacion, RECIBO_* ->
# factura_presentacion). No es la fuente de verdad de enrutamiento.
TIPO_JOB_COMANDA = "comanda"
TIPO_JOB_RECIBO = "recibo"

# Mapeo tipo de orden -> rol de RECIBO (mision seccion 7: "no mezclar el
# tipo de orden con el tipo de papel"). OJO: el valor real guardado en
# ordenes.tipo para Pick Up es literalmente "Para llevar" (el <option>
# visible dice "Pick Up", pero su value="Para llevar" - ver el formulario
# de /crear_orden). Comparacion case-insensitive porque el resto del
# proyecto ya trata `tipo` asi en varios lugares (self_ordering_ui.py).
_TIPO_A_ROL_RECIBO = {
    "mesa": ROL_RECIBO_MESA,
    "delivery": ROL_RECIBO_DELIVERY,
    "para llevar": ROL_RECIBO_PICKUP,
}


class TipoOrdenDesconocido(ValueError):
    """El tipo de orden no coincide con ninguno de los 3 tipos conocidos
    (Mesa/Delivery/Para llevar). No se adivina un rol: se levanta esto
    para que el llamador decida (loguear y no crear el job es preferible
    a enrutar un recibo al rol equivocado)."""


def rol_recibo_por_tipo_orden(tipo):
    clave = str(tipo or "").strip().lower()
    rol = _TIPO_A_ROL_RECIBO.get(clave)
    if rol is None:
        raise TipoOrdenDesconocido(f"Tipo de orden desconocido para recibo: {tipo!r}")
    return rol


def roles_validos(roles):
    """Valida una coleccion de roles contra ROLES_VALIDOS. Devuelve una
    tupla (sin duplicados, orden preservado) si todos son validos;
    levanta ValueError con el detalle si alguno no lo es. Nunca confia
    en strings arbitrarios del cliente (mision seccion 49)."""
    vistos = []
    desconocidos = []
    for rol in roles or []:
        rol = str(rol).strip()
        if not rol:
            continue
        if rol not in ROLES_VALIDOS:
            desconocidos.append(rol)
            continue
        if rol not in vistos:
            vistos.append(rol)
    if desconocidos:
        raise ValueError(f"Roles desconocidos: {desconocidos}")
    return tuple(vistos)


def roles_por_perfil(perfil, roles_personalizados=None):
    """Roles resultantes de elegir `perfil` en la UI. Para
    PERFIL_PERSONALIZADO, `roles_personalizados` (ya validados por
    roles_validos()) se usa tal cual."""
    if perfil == PERFIL_PERSONALIZADO:
        return tuple(roles_personalizados or ())
    roles = PERFILES_ROLES.get(perfil)
    if roles is None:
        raise ValueError(f"Perfil desconocido: {perfil!r}")
    return tuple(sorted(roles))
