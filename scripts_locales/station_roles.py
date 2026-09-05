"""
station_roles.py

Roles y perfiles de estacion de impresion (mismo contrato que
app/domain/sales/print_queue.py del backend, DUPLICADO deliberadamente
aqui -- ver kitchen_ticket_times.py para la explicacion completa de por
que scripts_locales/ nunca importa app/*: NekoLocal.spec excluye "app"
del paquete PyInstaller).

Si cambian los roles/perfiles en el backend, replicar el cambio aqui.
"""

ROL_COCINA = "COCINA"
ROL_RECIBO_MESA = "RECIBO_MESA"
ROL_RECIBO_PICKUP = "RECIBO_PICKUP"
ROL_RECIBO_DELIVERY = "RECIBO_DELIVERY"

ROLES_VALIDOS = frozenset({ROL_COCINA, ROL_RECIBO_MESA, ROL_RECIBO_PICKUP, ROL_RECIBO_DELIVERY})

PERFIL_TODO = "TODO"
PERFIL_COCINA = "COCINA"
PERFIL_SALON = "SALON"
PERFIL_PERSONALIZADO = "PERSONALIZADO"

PERFILES_ROLES = {
    PERFIL_TODO: (ROL_COCINA, ROL_RECIBO_MESA, ROL_RECIBO_PICKUP, ROL_RECIBO_DELIVERY),
    PERFIL_COCINA: (ROL_COCINA, ROL_RECIBO_PICKUP, ROL_RECIBO_DELIVERY),
    PERFIL_SALON: (ROL_RECIBO_MESA,),
}

# Etiquetas amigables para la UI (el socio elige un perfil, nunca roles
# sueltos uno por uno -- eso queda en "Configuracion avanzada").
ETIQUETAS_PERFIL = {
    PERFIL_TODO: "Todo — una sola impresora",
    PERFIL_COCINA: "Cocina",
    PERFIL_SALON: "Salón",
    PERFIL_PERSONALIZADO: "Personalizado / avanzado",
}


def roles_por_perfil(perfil, roles_personalizados=None):
    if perfil == PERFIL_PERSONALIZADO:
        return tuple(roles_personalizados or ())
    roles = PERFILES_ROLES.get(perfil)
    if roles is None:
        raise ValueError(f"Perfil desconocido: {perfil!r}")
    return roles


def roles_validos(roles):
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
