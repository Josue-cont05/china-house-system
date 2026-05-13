import os
import re
import time

import requests
import win32print


BASE_URL = "https://china-house-system-3be6.onrender.com"
URL_FACTURAS = f"{BASE_URL}/facturas_pendientes"
URL_DESACTIVAR = f"{BASE_URL}/desactivar_factura/"
URL_TASA = f"{BASE_URL}/cambiar_tasa"
ARCHIVO_IMPRESAS = "facturas_impresas.txt"


def cargar_impresos():
    impresos = set()

    if not os.path.exists(ARCHIVO_IMPRESAS):
        return impresos

    try:
        with open(ARCHIVO_IMPRESAS, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                factura_id = linea.strip()
                if factura_id:
                    impresos.add(factura_id)
    except Exception as e:
        print("⚠️ No se pudo cargar archivo de impresas:", e)

    return impresos


def guardar_impreso(factura_id):
    try:
        with open(ARCHIVO_IMPRESAS, "a", encoding="utf-8") as archivo:
            archivo.write(str(factura_id) + "\n")
    except Exception as e:
        print("⚠️ No se pudo guardar factura impresa:", e)


impresos = cargar_impresos()


# 🔥 OBTENER TASA REAL DEL SISTEMA (MEJORADO)
def obtener_tasa():
    try:
        res = requests.get(URL_TASA, timeout=5)

        if res.status_code != 200:
            print("⚠️ Error obteniendo tasa:", res.status_code)
            return None

        texto = res.text

        match = re.search(r"<b>(.*?)</b>", texto)

        if match:
            tasa = float(match.group(1))
            print(f"💱 Tasa obtenida: {tasa}")
            return tasa
        else:
            print("⚠️ No se encontró tasa en HTML")
            return None

    except Exception as e:
        print("❌ Error obteniendo tasa:", e)
        return None


# 🖨️ FUNCIÓN DE IMPRESIÓN
def imprimir(texto):
    printer_name = win32print.GetDefaultPrinter()
    print("🖨️ Usando impresora:", printer_name)

    hprinter = None

    try:
        hprinter = win32print.OpenPrinter(printer_name)

        win32print.StartDocPrinter(hprinter, 1, ("Factura", None, "RAW"))
        win32print.StartPagePrinter(hprinter)

        win32print.WritePrinter(hprinter, texto.encode("cp850", errors="replace"))

        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
        return True

    except Exception as e:
        print("❌ Error imprimiendo:", e)
        return False

    finally:
        if hprinter is not None:
            try:
                win32print.ClosePrinter(hprinter)
            except Exception:
                pass


def desactivar_factura(factura_id):
    try:
        res = requests.get(URL_DESACTIVAR + str(factura_id), timeout=5)
        if res.status_code == 200:
            print(f"✅ Factura {factura_id} desactivada")
        else:
            print(f"⚠️ No se pudo desactivar factura {factura_id}: {res.status_code}")
    except Exception as e:
        print("⚠️ No se pudo desactivar factura:", e)


# 🧾 FACTURA
def imprimir_factura(orden):
    print("🧾 IMPRIMIENDO FACTURA:", orden)

    tasa = obtener_tasa()

    if not tasa:
        print("⚠️ Usando tasa por defecto: 515")
        tasa = 515

    total_usd = orden.get("total", 0)
    total_bs = round(total_usd * tasa, 2)

    usuario = orden.get("usuario") or "N/A"

    texto = (
        "\n"
        "========================\n"
        "      CHINA HOUSE\n"
        "========================\n\n"
        f"FACTURA - ORDEN #{orden['numero']}\n"
        f"MESONERA: {usuario.upper()}\n\n"
        f"TIPO: {orden['tipo']}\n"
        f"CLIENTE: {orden['cliente']}\n"
        "------------------------\n\n"
    )

    # 🔥 ITEMS CONVERTIDOS A BS
    for item in orden["items"]:
        try:
            nombre, precio = item.split(" - $")
            precio = float(precio)
            precio_bs = round(precio * tasa, 2)
            texto += f"{nombre} - Bs {precio_bs}\n"
        except Exception:
            texto += f"{item}\n"

    texto += "\n------------------------\n"
    texto += f"TOTAL: Bs {total_bs}\n"
    texto += "------------------------\n\n\n"

    return imprimir(texto)


# 🔄 LOOP PRINCIPAL (ROBUSTO)
while True:
    try:
        print("🔄 Buscando facturas...")

        try:
            res = requests.get(URL_FACTURAS, timeout=5)
        except Exception as e:
            print("❌ Error conexión:", e)
            time.sleep(2)
            continue

        if res.status_code != 200:
            print("⚠️ Error API:", res.status_code)
            time.sleep(2)
            continue

        try:
            facturas = res.json()
        except Exception:
            print("❌ RESPUESTA NO JSON:")
            print(res.text)
            time.sleep(2)
            continue

        for f in facturas:
            factura_id = str(f["id"])
            evento_impresion = str(f.get("evento_impresion") or factura_id)

            if evento_impresion in impresos:
                print(f"⏭️ Evento {evento_impresion} ya impreso, desactivando pendiente")
                desactivar_factura(factura_id)
                continue

            impresa_correctamente = imprimir_factura(f)

            if impresa_correctamente:
                impresos.add(evento_impresion)
                guardar_impreso(evento_impresion)
                desactivar_factura(factura_id)
            else:
                print(f"⚠️ Evento {evento_impresion} no se marcó como impreso porque falló la impresión")

    except Exception as e:
        print("❌ Error general:", e)

    time.sleep(3)
