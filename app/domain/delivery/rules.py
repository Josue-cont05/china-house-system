"""
rules.py (dominio)

Reglas puras del dominio Delivery/repartidores: sin cursor, sin Flask,
sin SQL. Los estados de conductor de una orden Delivery
(ASSIGNED_INTERNAL / NEEDS_DRIVER / EXTERNAL) viven aqui como
constantes unicas -- ver mision "Delivery" (asignacion de conductor).
"""

ESTADO_DELIVERY_ASIGNADO_INTERNO = "ASSIGNED_INTERNAL"
ESTADO_DELIVERY_NECESITA_CONDUCTOR = "NEEDS_DRIVER"
ESTADO_DELIVERY_EXTERNO = "EXTERNAL"


def normalizar_nombre_repartidor(nombre):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del repartidor es obligatorio.")
    return nombre[:120]
