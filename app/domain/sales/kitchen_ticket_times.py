"""
kitchen_ticket_times.py

Formato de horas en el papel de cocina (mision "HORAS DE COCINA"):
cocina necesita ver a que hora entro una comanda para saber cuanto
tiempo lleva pendiente, usando SIEMPRE la hora historica en que la
orden fue enviada a cocina - nunca la hora en que fisicamente salio el
papel (eso puede ser minutos u horas despues, p. ej. tras un apagon).

Independiente de web_app.py a proposito (mismo motivo que
print_queue.py): el timestamp ya llega como texto "YYYY-MM-DD HH:MM:SS"
en hora de Venezuela (ver web_app.ahora_venezuela() /
orden_comandas.fecha_creacion, la fuente real de este texto) - este
modulo solo lo interpreta para mostrarlo, nunca genera timestamps ni
compara contra "ahora".

VENEZUELA_TZ se duplica deliberadamente aqui (en vez de importarlo de
web_app.py) para no crear una dependencia del dominio hacia el modulo
de la aplicacion: es una constante geografica fija, no configuracion.
"""

from datetime import datetime

import pytz

VENEZUELA_TZ = pytz.timezone("America/Caracas")
FORMATO_ALMACENADO = "%Y-%m-%d %H:%M:%S"

ETIQUETA_HORA = "HORA"
ETIQUETA_PEDIDO = "PEDIDO"
ETIQUETA_AGREGADO = "AGREGADO"


def parsear_como_caracas(fecha_texto):
    """Interpreta `fecha_texto` (ya en hora de Venezuela, naive) como un
    datetime consciente de zona horaria America/Caracas. No hace
    conversion de zona (el texto YA esta en esa zona) - localiza."""
    dt_naive = datetime.strptime(fecha_texto, FORMATO_ALMACENADO)
    return VENEZUELA_TZ.localize(dt_naive)


def formatear_hora_visible(fecha_texto):
    """'2026-09-05 19:12:00' -> '7:12 PM' (sin cero a la izquierda). Cadena
    vacia si no hay fecha (nunca lanza por un dato faltante: un ticket
    sin hora historica disponible simplemente omite esa linea)."""
    if not fecha_texto:
        return ""
    dt = parsear_como_caracas(fecha_texto)
    texto = dt.strftime("%I:%M %p")
    return texto.lstrip("0") or texto


def encabezado_horas_comanda(secuencia, es_reimpresion, hora_pedido_texto, hora_agregado_texto=None):
    """Lineas (etiqueta, valor_visible) para el encabezado de horas de
    una comanda de cocina impresa (base, incremental o reimpresion).

    Regla (unifica los ejemplos de la mision):
    - Primer lote (secuencia<=0) y NO es reimpresion: una sola linea
      "HORA: <hora_pedido>" (el pedido y el envio son el mismo evento).
    - Cualquier otro caso (incremental, o cualquier reimpresion): linea
      "PEDIDO: <hora_pedido>" (siempre la hora historica original de
      envio a cocina, nunca la hora actual). Si ademas es incremental
      (secuencia>0), se agrega "AGREGADO: <hora_agregado>" (la hora de
      ESE lote especifico, nunca la del lote anterior ni la actual).

    `hora_pedido_texto`/`hora_agregado_texto` son las cadenas crudas
    "YYYY-MM-DD HH:MM:SS" tal como vienen en el payload del job (nunca
    se recalculan aqui - ver seccion 41 de la mision: el worker/backend
    nunca reemplaza la hora historica con datetime.now()).
    """
    es_incremental = (secuencia or 0) > 0

    if not es_incremental and not es_reimpresion:
        return [(ETIQUETA_HORA, formatear_hora_visible(hora_pedido_texto))]

    lineas = [(ETIQUETA_PEDIDO, formatear_hora_visible(hora_pedido_texto))]
    if es_incremental:
        lineas.append((ETIQUETA_AGREGADO, formatear_hora_visible(hora_agregado_texto)))
    return lineas
