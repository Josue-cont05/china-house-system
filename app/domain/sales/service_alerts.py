"""
service_alerts.py

Alertas operativas de servicio para la pantalla DESPACHO (mision
"pantalla operativa de despacho + alertas de bebidas"). Deliberadamente
SEPARADO de print_jobs (app/domain/sales/print_queue.py): esto no es un
trabajo de impresion, es una notificacion visual+sonora para quien
despacha en salon quando llegan items nuevos que requieren su atencion.

Reglas de negocio (no relajar sin decision explicita):

- SOLO ordenes tipo Mesa generan estas alertas (Pick Up/Delivery no).
- SOLO cuando el pedido YA fue enviado inicialmente y se agregan items
  DESPUES -- el mismo criterio que Printing 2.0 ya usa para distinguir
  "incremental" (secuencia > 0 en orden_comandas), asi que un mesonero
  agregando productos y un cliente por self-ordering agregando
  productos producen exactamente la misma clase de alerta (mismo hook,
  ver app/infrastructure/database/kitchen_comandas.py::crear_comanda_en_cursor).
- SOLO los items NUEVOS de ese lote que esten clasificados para
  atencion de despacho (categorias.requiere_atencion_despacho=1),
  nunca el pedido completo ni items que ya iban en el envio inicial.
- Un evento POR LOTE incremental (varios items juntos = una sola
  alerta), no uno por item.
"""

import re

TIPO_BEBIDA_ADICIONAL = "bebida_adicional"

ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_ATENDIDA = "ATENDIDA"

# Mismo patron de prefijo de cantidad ("2x Nombre") que ya usan
# comanda_presentacion.py/item_builder.py en sus propias copias locales
# -- una utilidad de formato tan pequena no amerita compartir modulo,
# pero se documenta aqui por que se repite.
_PATRON_CANTIDAD = re.compile(r"^(\d+)\s*x\s+(.+)$", re.IGNORECASE)


def separar_cantidad(texto):
    """'2x Coca-Cola' -> (2, 'Coca-Cola'). Sin prefijo -> (1, texto)."""
    texto = (texto or "").strip()
    match = _PATRON_CANTIDAD.match(texto)
    if match:
        return max(int(match.group(1)), 1), match.group(2).strip()
    return 1, texto


def agrupar_items_alerta(nombres_crudos):
    """Lista de nombres de producto (pueden traer prefijo 'Nx ') ->
    lista ordenada de strings "Nx Nombre" con cantidades sumadas por
    nombre (mismo nombre en dos lineas distintas se combina en una)."""
    conteo = {}
    orden = []
    for nombre_crudo in nombres_crudos:
        cantidad, nombre = separar_cantidad(nombre_crudo)
        if not nombre:
            continue
        if nombre not in conteo:
            conteo[nombre] = 0
            orden.append(nombre)
        conteo[nombre] += cantidad
    return [f"{conteo[nombre]}x {nombre}" for nombre in orden]


def debe_evaluar_alerta(tipo_orden, secuencia):
    """True si este lote de cocina PODRIA generar una alerta de
    servicio: solo Mesa, solo si es un envio incremental (secuencia > 0
    -- el mismo criterio que ya usa Printing 2.0 para HORA/PEDIDO/
    AGREGADO en el ticket, ver kitchen_ticket_times.py). El primer envio
    de una mesa (secuencia 0) nunca genera alerta, sin importar que
    productos traiga: esos ya eran parte del pedido inicial."""
    es_incremental = (secuencia or 0) > 0
    es_mesa = str(tipo_orden or "").strip().lower() == "mesa"
    return es_incremental and es_mesa
