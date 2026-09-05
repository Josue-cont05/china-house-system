"""
kitchen_ticket_times.py

Formato de horas en el papel de cocina (mismo comportamiento que
app/domain/sales/kitchen_ticket_times.py del backend, DUPLICADO
deliberadamente aqui). scripts_locales/ es un subsistema standalone que
nunca importa web_app.py ni app/* (ver comanda_presentacion.py,
script_comanda_cocina.py): NekoLocal.spec excluye "app" explicitamente
del paquete PyInstaller para no arrastrar Flask/Postgres/etc. a la PC
del socio, asi que un import de app.domain.sales.* rompería el build
frozen. Es una funcion pura y pequeña; mantenerla en dos sitios es mas
barato que romper esa separacion.

Si cambia la regla de horas en el backend, replicar el cambio aqui.
"""

from datetime import datetime

import pytz

VENEZUELA_TZ = pytz.timezone("America/Caracas")
FORMATO_ALMACENADO = "%Y-%m-%d %H:%M:%S"

ETIQUETA_HORA = "HORA"
ETIQUETA_PEDIDO = "PEDIDO"
ETIQUETA_AGREGADO = "AGREGADO"


def parsear_como_caracas(fecha_texto):
    dt_naive = datetime.strptime(fecha_texto, FORMATO_ALMACENADO)
    return VENEZUELA_TZ.localize(dt_naive)


def formatear_hora_visible(fecha_texto):
    """'2026-09-05 19:12:00' -> '7:12 PM' (sin cero a la izquierda).
    Cadena vacia si no hay fecha (nunca lanza)."""
    if not fecha_texto:
        return ""
    dt = parsear_como_caracas(fecha_texto)
    texto = dt.strftime("%I:%M %p")
    return texto.lstrip("0") or texto


def encabezado_horas_comanda(secuencia, es_reimpresion, hora_pedido_texto, hora_agregado_texto=None):
    """Lineas (etiqueta, valor_visible) para el encabezado de horas de
    una comanda de cocina impresa. Ver el modulo espejo en el backend
    (app/domain/sales/kitchen_ticket_times.py) para la explicacion
    completa de la regla; debe mantenerse identica aqui."""
    es_incremental = (secuencia or 0) > 0

    if not es_incremental and not es_reimpresion:
        return [(ETIQUETA_HORA, formatear_hora_visible(hora_pedido_texto))]

    lineas = [(ETIQUETA_PEDIDO, formatear_hora_visible(hora_pedido_texto))]
    if es_incremental:
        lineas.append((ETIQUETA_AGREGADO, formatear_hora_visible(hora_agregado_texto)))
    return lineas
