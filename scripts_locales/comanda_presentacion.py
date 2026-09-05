"""
comanda_presentacion.py

Capa de presentacion de comandas de cocina para Neko Wok, migrada tal cual
desde C:\\NekoPrinterTest\\comandas_cocina.py (commit ea890bf, fisicamente
aprobado): impresora POS58 por Bluetooth SPP (COM6, 9600 baudios, ESC/POS,
codepage 16 / cp1252, ~32 columnas), via BluetoothPrinter.

Este modulo SOLO imprime: no hace polling, no decide deduplicacion ni que
items son nuevos. Recibe un evento de /ordenes_cocina (una orden_comanda,
segun el diseno actual de NekoPOS) y aplica el mismo formato ya validado
fisicamente en NekoPrinterTest. `imprimir_comanda(orden)` imprime
exactamente `orden["items"]`, sin reconstruir ni comparar contra otras
comandas: esa separacion en lotes ya la hace el backend.

El worker responsable de polling + deduplicacion persistente es
script_comanda_cocina.py, en este mismo directorio.
"""

import re
from collections import defaultdict
from pathlib import Path

import winsound

from bluetooth_printer import BluetoothPrinter, PrinterError, PrinterConnectionError

# Resuelto desde la ubicacion de este archivo, no desde el working directory,
# para que funcione sin importar desde donde se ejecute el servicio.
BASE_DIR = Path(__file__).resolve().parent
LOGO_MINI_PATH = BASE_DIR / "mini_logo_neko_thermal_01.png"

# Ancho maximo del logo en px. Ajustable aqui sin tocar BluetoothPrinter.
LOGO_MAX_WIDTH_PX = 200

# Desplazamiento horizontal del logo hacia la derecha, en px, aplicado
# dentro del propio raster ESC/POS (no son espacios de texto: a ~384 px de
# ancho util / 32 columnas, 1 caracter ~ 12 px, por lo que 48 px equivalen
# a 4 columnas de texto normal). Ajustable para corregir el centrado visual
# reportado en la impresora fisica.
LOGO_OFFSET_X_PX = 96

# Ancho maximo (en caracteres) para el que se permite tamano doble sin riesgo
# de overflow en una impresora de 32 columnas (32 / 2 = 16 columnas en doble).
_ANCHO_MAXIMO_DOBLE = 16


def quitar_prefijo_cantidad_visual(texto):
    texto = (texto or "").strip()

    while True:
        limpio = re.sub(r"^1x\s+(\d+x\s+.+)$", r"\1", texto, flags=re.IGNORECASE)
        if limpio == texto:
            return texto
        texto = limpio.strip()


def separar_cantidad_producto(texto):
    texto = quitar_prefijo_cantidad_visual(texto)
    match = re.match(r"^(\d+)x\s+(.+)$", texto, flags=re.IGNORECASE)

    if match:
        cantidad = int(match.group(1))
        producto = match.group(2).strip()
        return max(cantidad, 1), producto

    return 1, texto.strip()


def agrupar_items(items):
    grupos = defaultdict(int)

    for item in items:
        cantidad, producto = separar_cantidad_producto(item)
        if producto:
            grupos[producto] += cantidad

    return grupos


def numero_comanda_visible(numero, secuencia):
    """Encabezado visible de la comanda a partir de `numero` (numero_orden)
    y `secuencia` (posicion del lote dentro de esa orden, tal como llega en
    el payload de /ordenes_cocina).

    IMPORTANTE: `orden_comandas.secuencia` es 0-INDEXADA en la BD real
    (confirmado en app/infrastructure/database/kitchen_comandas.py,
    _reservar_secuencia_comanda: el primer lote de una orden recibe
    secuencia=0, el segundo secuencia=1, el tercero secuencia=2, etc. -
    ver tests/test_self_ordering_routes.py,
    test_mixed_manual_and_self_ordering_batches_share_one_sequence_by_item_id,
    que verifica [0, 1, 2, 3] para 4 lotes consecutivos). Por eso el primer
    lote (secuencia=0) NO lleva sufijo, y desde el segundo lote en adelante
    el sufijo es la propia secuencia, sin restar nada:

    secuencia=0 (1er envio, o legacy/ausente) -> "<numero>"      "COMANDA #33"
    secuencia=1 (2do envio)                   -> "<numero>.1"    "COMANDA #33.1"
    secuencia=2 (3er envio)                   -> "<numero>.2"    "COMANDA #33.2"
    secuencia=3 (4to envio)                   -> "<numero>.3"    "COMANDA #33.3"

    `secuencia` NO se calcula aqui: siempre viene del backend (columna
    orden_comandas.secuencia via /ordenes_cocina), este modulo solo la
    formatea.
    """
    try:
        secuencia_int = int(secuencia)
    except (TypeError, ValueError):
        secuencia_int = 0

    if secuencia_int <= 0:
        return str(numero)
    return f"{numero}.{secuencia_int}"


def _imprimir_destacado(printer, texto, ancho_maximo_doble=_ANCHO_MAXIMO_DOBLE):
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


def _imprimir_campo(printer, etiqueta, valor, valor_en_negrita=False):
    """Imprime 'ETIQUETA: valor' respetando wrapping por palabras (nunca
    parte palabras). La etiqueta siempre va en negrita; el valor va en
    negrita solo si valor_en_negrita=True (para resaltar REF en DELIVERY
    o CLIENTE en PICK UP); si no, va en peso normal. No imprime nada si
    el valor esta vacio.
    """
    valor = (valor or "").strip()
    if not valor:
        return

    if valor_en_negrita:
        printer.set_bold(True)
        printer.print_wrapped(f"{etiqueta} {valor}")
        printer.set_bold(False)
        return

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


def _imprimir_item(printer, item):
    """Imprime un item conservando su contenido exacto: no reinterpreta
    combos, conserva saltos de linea internos ya presentes, y aplica
    wrapping por palabras (sin partir palabras) a cada linea interna que
    supere el ancho util del papel.
    """
    item_limpio = quitar_prefijo_cantidad_visual(item)
    if not item_limpio:
        return

    for linea in item_limpio.split("\n"):
        printer.print_wrapped(linea)

    printer.feed(1)  # separacion visual entre items, igual que actualmente


def imprimir_comanda(orden):
    print("IMPRIMIENDO COMANDA:", orden)

    winsound.Beep(1000, 300)

    usuario = orden.get("usuario", "-") or "-"
    numero = orden.get("numero")
    secuencia = orden.get("secuencia")
    reimpresion = bool(orden.get("reimpresion_token"))
    print(
        f"[COCINA] numero={numero} secuencia={secuencia} "
        f"comanda_id={orden.get('comanda_id')} reimpresion={reimpresion}"
    )
    # La reimpresion es el acumulado de TODA la orden (ver backend:
    # obtener_items_enviados_de_orden), no un lote puntual - por eso
    # siempre muestra el numero base, nunca "<numero>.<secuencia>".
    numero_visible = str(numero) if reimpresion else numero_comanda_visible(numero, secuencia)
    print(f"[COCINA] numero_visible={numero_visible}")
    referencia = orden.get("referencia", "-") or "-"
    cliente = orden.get("cliente", "-") or "-"
    tipo = orden.get("tipo", "-") or "-"
    estado = orden.get("estado", "") or ""

    tipo_norm = str(tipo).strip().upper()
    referencia_valida = referencia not in (None, "", "-")

    # Si tipo == MESA, la referencia ya se destaca debajo de "MESA" (punto 5
    # mas abajo); en ese caso no se repite como "REF: ..." en datos normales.
    mostrar_ref_normal = referencia_valida and tipo_norm != "MESA"

    with BluetoothPrinter(port="COM6", baudrate=9600) as printer:
        # 1. Logo centrado, desplazado a la derecha LOGO_OFFSET_X_PX px
        # (compensacion de centrado visual reportada en la impresora fisica)
        printer.print_image(
            str(LOGO_MINI_PATH), max_width=LOGO_MAX_WIDTH_PX, offset_x=LOGO_OFFSET_X_PX
        )

        # 3. Bloque de reimpresion, muy visible, antes de los datos
        if reimpresion:
            printer.align("center")
            _imprimir_destacado(printer, "REIMPRESION")
            _imprimir_destacado(printer, "DE COCINA")
            printer.feed(1)

        # 2. Comanda resaltada
        printer.align("center")
        _imprimir_destacado(printer, f"COMANDA #{numero_visible}")

        # 4. Tipo centrado y muy visible (aplica a MESA, DELIVERY, PICK UP, etc.)
        printer.align("center")
        _imprimir_destacado(printer, tipo_norm)

        # 5. Si es MESA, la referencia (identificacion de mesa) tambien
        #    se destaca debajo, ademas de aparecer en los datos normales.
        if tipo_norm == "MESA" and referencia_valida:
            _imprimir_destacado(printer, str(referencia))

        printer.feed(1)
        printer.align("left")

        # 7. Datos normales (etiqueta en negrita; valor normal salvo casos
        # especiales: REF completa en negrita en DELIVERY, CLIENTE completo
        # en negrita en PICK UP). Todos con wrapping por palabras.
        _imprimir_campo(printer, "SERVICIO:", str(usuario).upper())
        _imprimir_campo(
            printer, "CLIENTE:", cliente, valor_en_negrita=(tipo_norm == "PICK UP")
        )
        if mostrar_ref_normal:
            _imprimir_campo(
                printer, "REF:", referencia, valor_en_negrita=(tipo_norm == "DELIVERY")
            )
        _imprimir_campo(printer, "ESTADO:", str(estado).upper() if estado else "")

        # 8. Separador
        printer.print_line("-" * 32)

        # 9. Items (contenido exacto, sin interpretar combos)
        for item in orden.get("items", []):
            _imprimir_item(printer, item)

        # 10. Separador final + avance para sujetar/cortar manualmente
        printer.print_line("-" * 32)
        printer.feed(1)
