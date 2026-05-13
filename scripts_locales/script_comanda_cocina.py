import re
import time
from collections import defaultdict

import requests
import win32print
import winsound

URL_COCINA = "https://china-house-system-3be6.onrender.com/ordenes_cocina"

impresos = set()


def imprimir(texto):
    printer_name = win32print.GetDefaultPrinter()
    print("Usando impresora:", printer_name)

    hprinter = win32print.OpenPrinter(printer_name)

    try:
        win32print.StartDocPrinter(hprinter, 1, ("Comanda", None, "RAW"))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, texto.encode("cp850", errors="replace"))
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)


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


def imprimir_comanda(orden):
    print("IMPRIMIENDO COMANDA:", orden)

    winsound.Beep(1000, 300)

    usuario = orden.get("usuario", "-") or "-"
    numero = orden.get("numero")
    referencia = orden.get("referencia", "-") or "-"
    cliente = orden.get("cliente", "-") or "-"
    tipo = orden.get("tipo", "-") or "-"
    estado = orden.get("estado", "") or ""

    encabezado_reimpresion = ""
    if orden.get("reimpresion_token"):
        encabezado_reimpresion = "***** REIMPRESION DE COCINA *****\n\n"

    texto = (
        "\n"
        "========================\n"
        "      CHINA HOUSE\n"
        "========================\n\n"
        f"{encabezado_reimpresion}"
        f"ORDEN #{numero}\n"
        f"MESONERA: {str(usuario).upper()}\n\n"
        f"TIPO: {tipo}\n"
        f"CLIENTE: {cliente}\n"
        f"REF: {referencia}\n"
    )

    if estado:
        texto += f"ESTADO: {str(estado).upper()}\n"

    texto += "------------------------\n\n"

    items_agrupados = agrupar_items(orden.get("items", []))

    for producto, cantidad in items_agrupados.items():
        texto += f"{cantidad}x {producto}\n"

    texto += "\n------------------------\n\n\n"

    imprimir(texto)


while True:
    try:
        print("Buscando comandas...")

        res = requests.get(URL_COCINA, timeout=10)

        if res.status_code == 200:
            ordenes = res.json()

            for o in ordenes:
                key = o.get("evento_impresion") or f"cocina_{o['id']}"

                if key not in impresos:
                    imprimir_comanda(o)
                    impresos.add(key)
        else:
            print("Error API:", res.status_code)

    except Exception as e:
        print("Error:", e)

    time.sleep(3)