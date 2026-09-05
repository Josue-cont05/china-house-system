"""
factura_presentacion.py

Impresion del RECIBO DEL CLIENTE de Neko Wok, migrada tal cual desde
C:\\NekoPrinterTest\\facturas_cliente.py (commit ea890bf, fisicamente
aprobado). No se imprime la palabra "FACTURA" en ningun lado, pese al
nombre historico del archivo origen.

Reutiliza bluetooth_printer.py (ESC/POS, codepage 16 / cp1252, wrapping
por palabras, logo raster) sin tocarlo ni duplicarlo.

Este modulo SOLO imprime: NO calcula logica comercial. Todos los precios,
totales, descuentos y el monto de delivery deben venir YA calculados por
NekoPOS/backend (ver app/domain/sales/receipts.py) antes de llegar aqui.
Tampoco inventa montos: si un item no trae 'total', se imprime sin precio
(nunca se multiplica precio_unitario x cantidad). NO decide el puerto
(COM6 en una PC puede ser COM8 en otra): `port`/`baudrate` llegan
explicitos, resueltos por el worker a partir de la configuracion local de
Neko Local (neko_config.py/port_detection.py), igual que
comanda_presentacion.py.

El recibo del cliente es deliberadamente simple: por producto solo
muestra cantidad + nombre + total (sin detalles/ingredientes/observacion,
que son informacion de preparacion propia de la comanda de cocina) y
nunca imprime el metodo de pago (aceptado por compatibilidad, pero
ignorado al imprimir).

`cobrada` (bool) llega en el contrato para distinguir una cuenta
provisional de un recibo con snapshot de cobro, pero por ahora NO cambia
el diseño impreso (no se decidio agregar un rotulo "PROVISIONAL" en esta
fase) - queda disponible para diferenciarlo visualmente mas adelante si
se decide.

Uso basico:

    from factura_presentacion import imprimir_factura

    imprimir_factura(
        numero=42,
        cliente="Gabriela",
        tipo="DELIVERY",
        referencia="Los Robles",
        fecha_hora="04/09/2026 20:47",
        items=[{"cantidad": 2, "nombre": "Neko Combo 2", "total": 16.0}],
        subtotal=21.50,
        delivery=2.00,
        total=23.50,
        total_bs=4935.00,
        port="COM6",
    )
"""

from __future__ import annotations

from pathlib import Path

from bluetooth_printer import BluetoothPrinter

# Resuelto desde la ubicacion de este archivo, no desde el working directory,
# para que funcione sin importar desde donde se ejecute el servicio.
BASE_DIR = Path(__file__).resolve().parent

# Logo GRANDE ya validado fisicamente (distinto del mini logo de comandas).
LOGO_GRANDE_PATH = BASE_DIR / "logo_neko_thermal.png"
LOGO_MAX_WIDTH_PX = 272  # 340 px - 20%

# Ancho imprimible real de una POS58 de 58 mm. El logo se centra
# matematicamente dentro de este ancho fisico (canvas_width de
# print_image()), no con "espacios" de texto ni offsets manuales.
PAPEL_IMPRIMIBLE_PX = 384

# Ancho maximo (en caracteres) para el que se permite tamano doble sin
# riesgo de overflow en una impresora de 32 columnas (32 / 2 = 16 en doble).
_ANCHO_MAXIMO_DOBLE = 16

# GS ! n con n=0x01: doble ALTO manteniendo el ancho normal (no es el mismo
# "doble" de set_size(), que duplica alto y ancho). Es el nivel de enfasis
# usado para el agradecimiento principal. Se envia como bytes crudos
# ESC/POS via send_bytes() (API ya publica de BluetoothPrinter), sin
# necesidad de tocar bluetooth_printer.py.
_GS_DOBLE_ALTO = b"\x1d\x21\x01"
_GS_TAMANO_NORMAL = b"\x1d\x21\x00"

# Banco de mensajes de agradecimiento. La eleccion es DETERMINISTA por
# numero de orden (ver _elegir_mensaje): la misma orden siempre produce el
# mismo mensaje, aunque se reimprima. No se usa random.
MENSAJES_AGRADECIMIENTO = [
    "Tu compra nos ayuda a seguir creciendo y mejorando cada día.",
    "Gracias por elegirnos para ponerle algo rico a tu día.",
    "Cada pedido nos ayuda a seguir construyendo este sueño llamado Neko Wok.",
    "Gracias por dejarnos ser parte de tu comida de hoy.",
    "Esperamos que disfrutes este pedido tanto como nosotros disfrutamos preparándolo.",
    "Tu apoyo nos inspira a seguir mejorando plato a plato.",
    "Hoy cocinamos para ti. Gracias por confiar en Neko Wok.",
    "Un pedido más, una razón más para seguir haciendo las cosas cada vez mejor.",
    "Gracias por apoyar a Neko Wok. Aquí seguimos cocinando con ganas para ti.",
    "Que este pedido te saque aunque sea una sonrisa. Gracias por elegir Neko.",
]


def _elegir_mensaje(numero_orden):
    """Selecciona un mensaje del banco de forma deterministica segun el
    numero de orden (numero_orden % len(MENSAJES_AGRADECIMIENTO)). La misma
    orden conserva siempre el mismo mensaje, incluso en una reimpresion.
    """
    try:
        indice = int(numero_orden) % len(MENSAJES_AGRADECIMIENTO)
    except (TypeError, ValueError):
        indice = 0
    return MENSAJES_AGRADECIMIENTO[indice]


def _money(valor):
    """Formatea un monto USD con 2 decimales y simbolo $, tolerando None."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    return f"${numero:.2f}"


def _formatear_bs(valor):
    """Formatea un monto en bolivares ya calculado (no se convierte nada
    aqui): separador de miles '.' y decimal ',', prefijo 'Bs ' (ej. 3619.75
    -> 'Bs 3.619,75'). Tolerante a None/no numerico -> 'Bs 0,00'."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    texto = f"{numero:,.2f}"  # ej. "3,619.75" (miles=',' decimal='.')
    texto = texto.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"Bs {texto}"


def _es_vacio(valor):
    """True si un valor de campo debe tratarse como ausente: None, cadena
    vacia o "-" (convencion ya usada en comanda_presentacion.py para 'sin
    dato')."""
    if valor is None:
        return True
    texto = str(valor).strip()
    return texto == "" or texto == "-"


def _destacado(printer, texto, ancho_maximo_doble=_ANCHO_MAXIMO_DOBLE):
    """Imprime una linea corta en negrita, en tamano doble si cabe sin
    desbordar (~16 columnas); si es mas larga, cae a negrita en tamano
    normal para evitar overflow. No toca la alineacion vigente.
    """
    texto = (texto or "").strip()
    if not texto:
        return

    printer.set_bold(True)
    if len(texto) <= ancho_maximo_doble:
        printer.set_size("double")
        printer.print_line(texto)
        printer.set_size("normal")
    else:
        printer.print_line(texto)
    printer.set_bold(False)


def _imprimir_realzado(printer, texto):
    """Imprime texto en negrita y doble ALTO (ancho normal): un nivel de
    enfasis por encima del texto normal, usado para el agradecimiento
    principal. Aplica wrapping por palabras (nunca parte palabras) si el
    texto no cabe en una sola linea. No toca la alineacion vigente.
    """
    texto = (texto or "").strip()
    if not texto:
        return
    printer.set_bold(True)
    printer.send_bytes(_GS_DOBLE_ALTO)
    for linea in printer.wrap_text(texto):
        printer.print_line(linea)
    printer.send_bytes(_GS_TAMANO_NORMAL)
    printer.set_bold(False)


def _campo(printer, etiqueta, valor):
    """Imprime 'ETIQUETA: valor' con wrapping por palabras (nunca parte
    palabras); etiqueta en negrita, valor en peso normal. No imprime nada
    si el valor esta vacio (None, "" o "-").
    """
    if _es_vacio(valor):
        return
    valor = str(valor).strip()

    lineas = printer.wrap_text(f"{etiqueta} {valor}")
    if not lineas:
        return

    prefijo = etiqueta + " "
    primera, resto = lineas[0], lineas[1:]

    printer.set_bold(True)
    printer.print_text(prefijo)
    printer.set_bold(False)
    if primera.startswith(prefijo):
        printer.print_line(primera[len(prefijo):])
    else:
        printer.print_line(primera)

    for linea in resto:
        printer.print_line(linea)


def _linea_monto(printer, etiqueta, valor_texto):
    """Imprime 'Etiqueta:  monto' en una sola linea, con el monto alineado
    al margen derecho mediante relleno de espacios (no via comandos ESC/POS
    de alineacion, para poder combinar etiqueta izquierda + monto derecha
    en la misma linea). Si no cabe, cae a dos lineas (etiqueta y monto)."""
    ancho = printer.chars_per_line
    espacio = ancho - len(etiqueta) - len(valor_texto)
    if espacio < 1:
        printer.print_line(etiqueta)
        printer.align("right")
        printer.print_line(valor_texto)
        printer.align("left")
        return
    printer.print_line(etiqueta + " " * espacio + valor_texto)


def _imprimir_item(printer, item):
    """Imprime un item como una sola linea 'cantidad x NOMBRE   monto' (o
    dos lineas si no cabe en 32 columnas, via _linea_monto). El recibo del
    cliente NO imprime detalles/ingredientes/acompanantes/observaciones del
    producto (esa informacion de preparacion sigue existiendo solo en la
    comanda de cocina); si el item los trae en su estructura, se ignoran.

    Esta capa es solo presentacion: si el item no trae 'total' ya
    calculado, NO se inventa un monto (nunca se multiplica
    precio_unitario x cantidad) -- se imprime solo 'cantidad x NOMBRE',
    sin precio.
    """
    cantidad = item.get("cantidad", 1) or 1
    nombre = str(item.get("nombre", "") or "").strip()
    if not nombre:
        return

    etiqueta = f"{cantidad} x {nombre}"
    total_item = item.get("total")

    printer.align("left")
    printer.set_bold(True)
    if total_item is None:
        printer.print_wrapped(etiqueta)
    else:
        _linea_monto(printer, etiqueta, _money(total_item))
    printer.set_bold(False)


def imprimir_factura(
    numero,
    cliente,
    tipo,
    referencia,
    fecha_hora,
    items,
    subtotal,
    port,
    descuento=0,
    delivery=0,
    total=0,
    metodo_pago=None,
    total_bs=None,
    mensaje=None,
    cobrada=None,
    baudrate=9600,
):
    """Imprime el recibo del cliente. Todos los montos ya deben venir
    calculados por el llamador (este modulo no calcula logica comercial).
    `port`/`baudrate` los decide quien llama (el worker, a partir de la
    configuracion local de Neko Local) - esta plantilla no tiene un
    puerto por defecto propio.

    tipo determina que linea de referencia se muestra:
      MESA     -> "Mesa: <referencia>" (sin linea "Tipo:")
      DELIVERY -> "Tipo: DELIVERY" + "Ref: <referencia>"
      PICK UP  -> "Tipo: PICK UP", sin linea de referencia
      otro     -> "Tipo: <tipo>" + "Ref: <referencia>" si hay (fallback)

    Campos vacios (None, "" o "-") se omiten por completo, nunca se
    imprimen como "Cliente: None" o "Ref:".

    En MESA se omiten ademas, solo ahi, las lineas "BUEN PROVECHO" y
    "¡QUE LO DISFRUTES!" del cierre (DELIVERY y PICK UP las conservan).

    metodo_pago se acepta por compatibilidad de la API pero NUNCA se
    imprime en el recibo del cliente (decision de producto): se ignora
    por completo dentro de esta funcion. `cobrada` se acepta para dejarlo
    disponible en el contrato pero tampoco cambia el diseño impreso.
    """
    tipo_norm = str(tipo).strip().upper() if tipo else ""

    with BluetoothPrinter(port=port, baudrate=baudrate) as printer:
        # Logo grande (LOGO_MAX_WIDTH_PX), no el mini logo de comandas,
        # centrado matematicamente dentro del ancho fisico imprimible real
        # (PAPEL_IMPRIMIBLE_PX), no con offsets/espacios de texto.
        printer.print_image(
            str(LOGO_GRANDE_PATH),
            max_width=LOGO_MAX_WIDTH_PX,
            canvas_width=PAPEL_IMPRIMIBLE_PX,
        )

        # Orden + fecha/hora: encabezado discreto (negrita, tamano normal),
        # centrado, sin competir visualmente con TOTAL ni el logo.
        printer.align("center")
        printer.set_bold(True)
        printer.print_line(f"ORDEN #{numero}")
        printer.set_bold(False)
        printer.print_line(str(fecha_hora or "").strip())
        printer.feed(1)

        # Datos del cliente/pedido: etiqueta segun tipo, sin duplicar y
        # sin imprimir campos vacios. MESA no imprime "Tipo:" (solo
        # Cliente/Mesa); DELIVERY y PICK UP si muestran "Tipo:".
        printer.align("left")
        _campo(printer, "Cliente:", cliente)
        if tipo_norm != "MESA":
            _campo(printer, "Tipo:", tipo_norm)
        if tipo_norm == "MESA":
            _campo(printer, "Mesa:", referencia)
        elif tipo_norm not in ("PICK UP", "PICKUP"):
            _campo(printer, "Ref:", referencia)

        printer.feed(1)
        printer.print_line("-" * 32)

        # Productos: solo cantidad + nombre + total (sin detalles/observacion).
        for item in items or []:
            _imprimir_item(printer, item)

        printer.print_line("-" * 32)

        # Totales: solo se imprimen los campos que aplican.
        printer.align("left")
        _linea_monto(printer, "Subtotal:", _money(subtotal))
        if descuento:
            _linea_monto(printer, "Descuento:", "-" + _money(descuento))
        if delivery:
            _linea_monto(printer, "Delivery:", _money(delivery))

        # TOTAL: el dato economico mas destacado (negrita + tamano doble),
        # palabra y monto en lineas separadas.
        printer.feed(1)
        printer.align("center")
        _destacado(printer, "TOTAL")
        _destacado(printer, _money(total))

        # Total en Bs (si viene informado): centrado, negrita, pero en
        # tamano normal -- mas discreto que el TOTAL en USD, sin competir
        # visualmente con el. Esta capa no calcula la conversion: solo
        # formatea el valor ya calculado que llega en total_bs.
        if total_bs is not None:
            printer.set_bold(True)
            printer.print_line(_formatear_bs(total_bs))
            printer.set_bold(False)

        printer.feed(1)
        printer.print_line("-" * 32)

        # Mensaje de cierre: agradecimiento en MAYUSCULAS, negrita y doble
        # alto (realzado), centrado. No altera el dato original de cliente,
        # solo lo convierte a mayusculas para la impresion.
        printer.align("center")
        if not _es_vacio(cliente):
            _imprimir_realzado(
                printer, f"GRACIAS POR TU COMPRA, {str(cliente).strip().upper()}"
            )
        else:
            _imprimir_realzado(printer, "GRACIAS POR TU COMPRA")
        printer.feed(1)

        texto_mensaje = mensaje if mensaje is not None else _elegir_mensaje(numero)
        printer.print_wrapped(texto_mensaje)
        printer.feed(1)

        # BUEN PROVECHO / QUE LO DISFRUTES se omiten solo en MESA (a pedido).
        if tipo_norm != "MESA":
            _destacado(printer, "BUEN PROVECHO")
            _destacado(printer, "¡QUE LO DISFRUTES!")
            printer.feed(1)

        printer.print_line("    Neko Wok")
        printer.print_wrapped("Hecho con wok y cariño.")

        printer.feed(4)
