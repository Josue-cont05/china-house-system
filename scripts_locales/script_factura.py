import sys
import time
from pathlib import Path

import requests
import win32print


BASE_URL = "https://china-house-system-3be6.onrender.com"
URL_FACTURAS = f"{BASE_URL}/facturas_pendientes"
URL_TASA = f"{BASE_URL}/api/tasa"
URL_DESACTIVAR = f"{BASE_URL}/desactivar_factura"
TASA_FALLBACK = 515

BASE_DIR = Path(__file__).resolve().parent
ARCHIVO_IMPRESAS = BASE_DIR / "facturas_impresas.txt"

ESC_POS_INICIALIZAR = b"\x1b\x40"
ESC_POS_AVANCE = b"\n\n\n\n"
ESC_POS_CORTE = b"\x1d\x56\x00"

session_http = requests.Session()
impresos = set()
eventos_duplicados_reportados = set()


def cargar_impresos():
    impresos_cargados = set()

    if not ARCHIVO_IMPRESAS.exists():
        return impresos_cargados

    try:
        with ARCHIVO_IMPRESAS.open("r", encoding="utf-8") as archivo:
            for linea in archivo:
                evento_impresion = linea.strip()
                if evento_impresion:
                    impresos_cargados.add(evento_impresion)
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo cargar {ARCHIVO_IMPRESAS}: {e}")

    return impresos_cargados


def guardar_impreso(evento_impresion):
    try:
        with ARCHIVO_IMPRESAS.open("a", encoding="utf-8") as archivo:
            archivo.write(str(evento_impresion) + "\n")
        return True
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo guardar factura impresa en {ARCHIVO_IMPRESAS}: {e}")
        return False


def a_float(valor, default=0.0):
    try:
        if valor is None:
            return default
        texto = str(valor).strip().replace(",", ".")
        if texto == "":
            return default
        return float(texto)
    except Exception:
        return default


def texto_parcial_respuesta(respuesta, limite=220):
    try:
        texto = respuesta.text or ""
    except Exception:
        return ""
    texto = texto.replace("\n", " ").replace("\r", " ").strip()
    return texto[:limite]


def obtener_tasa():
    inicio = time.perf_counter()

    try:
        respuesta = session_http.get(URL_TASA, timeout=5)
        duracion = time.perf_counter() - inicio

        if respuesta.status_code != 200:
            print(
                f"ADVERTENCIA: Error obteniendo tasa desde API: HTTP {respuesta.status_code} "
                f"en {duracion:.2f}s. Respuesta: {texto_parcial_respuesta(respuesta)}"
            )
            print(f"ADVERTENCIA: Usando tasa fallback SOLO como emergencia: {TASA_FALLBACK}")
            return TASA_FALLBACK

        try:
            datos = respuesta.json()
        except Exception as e:
            print(f"ADVERTENCIA: /api/tasa no devolvio JSON valido en {duracion:.2f}s: {e}")
            print(f"ADVERTENCIA: Respuesta: {texto_parcial_respuesta(respuesta)}")
            print(f"ADVERTENCIA: Usando tasa fallback SOLO como emergencia: {TASA_FALLBACK}")
            return TASA_FALLBACK

        if not datos.get("ok"):
            print(f"ADVERTENCIA: /api/tasa respondio error en {duracion:.2f}s: {datos}")
            print(f"ADVERTENCIA: Usando tasa fallback SOLO como emergencia: {TASA_FALLBACK}")
            return TASA_FALLBACK

        tasa = a_float(datos.get("tasa"))
        if tasa <= 0:
            print(f"ADVERTENCIA: /api/tasa devolvio tasa invalida en {duracion:.2f}s: {datos}")
            print(f"ADVERTENCIA: Usando tasa fallback SOLO como emergencia: {TASA_FALLBACK}")
            return TASA_FALLBACK

        print(f"Tasa obtenida desde API: {tasa:g} en {duracion:.2f}s")
        return tasa

    except Exception as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: Error consultando /api/tasa en {duracion:.2f}s: {e}")
        print(f"ADVERTENCIA: Usando tasa fallback SOLO como emergencia: {TASA_FALLBACK}")
        return TASA_FALLBACK


def obtener_facturas():
    inicio = time.perf_counter()

    try:
        respuesta = session_http.get(URL_FACTURAS, timeout=8)
        duracion = time.perf_counter() - inicio

        if respuesta.status_code != 200:
            print(
                f"ADVERTENCIA: Error API facturas: HTTP {respuesta.status_code} en {duracion:.2f}s. "
                f"Respuesta: {texto_parcial_respuesta(respuesta)}"
            )
            return []

        try:
            facturas = respuesta.json()
        except Exception as e:
            print(f"ADVERTENCIA: Respuesta de facturas no es JSON en {duracion:.2f}s: {e}")
            print(f"ADVERTENCIA: Respuesta: {texto_parcial_respuesta(respuesta)}")
            return []

        if not isinstance(facturas, list):
            print(f"ADVERTENCIA: Respuesta de facturas no es una lista en {duracion:.2f}s: {facturas}")
            return []

        print(f"Facturas recibidas: {len(facturas)} en {duracion:.2f}s")
        return facturas

    except Exception as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: Error conexion facturas en {duracion:.2f}s: {e}")
        return []


def preparar_bytes_impresion(texto):
    contenido = texto.encode("cp850", errors="replace")
    return ESC_POS_INICIALIZAR + contenido + ESC_POS_AVANCE + ESC_POS_CORTE


def imprimir(texto):
    inicio = time.perf_counter()
    hprinter = None
    doc_iniciado = False
    pagina_iniciada = False

    try:
        try:
            printer_name = win32print.GetDefaultPrinter()
            print(f"Usando impresora: {printer_name}")
        except Exception as e:
            print(f"ERROR GetDefaultPrinter: {e}")
            return False

        datos = preparar_bytes_impresion(texto)
        print(f"Bytes enviados a impresora: {len(datos)}")

        try:
            hprinter = win32print.OpenPrinter(printer_name)
        except Exception as e:
            print(f"ERROR OpenPrinter para '{printer_name}': {e}")
            return False

        try:
            win32print.StartDocPrinter(hprinter, 1, ("Factura", None, "RAW"))
            doc_iniciado = True
        except Exception as e:
            print(f"ERROR StartDocPrinter: {e}")
            return False

        try:
            win32print.StartPagePrinter(hprinter)
            pagina_iniciada = True
        except Exception as e:
            print(f"ERROR StartPagePrinter: {e}")
            return False

        try:
            escritos = win32print.WritePrinter(hprinter, datos)
            if escritos is not None:
                print(f"WritePrinter reporto bytes escritos: {escritos}")
        except Exception as e:
            print(f"ERROR WritePrinter: {e}")
            return False

        try:
            win32print.EndPagePrinter(hprinter)
            pagina_iniciada = False
        except Exception as e:
            print(f"ERROR EndPagePrinter: {e}")
            return False

        try:
            win32print.EndDocPrinter(hprinter)
            doc_iniciado = False
        except Exception as e:
            print(f"ERROR EndDocPrinter: {e}")
            return False

        duracion = time.perf_counter() - inicio
        print(f"Impresion enviada en {duracion:.2f}s")
        return True

    finally:
        if hprinter is not None:
            if pagina_iniciada:
                try:
                    win32print.EndPagePrinter(hprinter)
                except Exception as e:
                    print(f"ADVERTENCIA cerrando pagina de impresion: {e}")
            if doc_iniciado:
                try:
                    win32print.EndDocPrinter(hprinter)
                except Exception as e:
                    print(f"ADVERTENCIA cerrando documento de impresion: {e}")
            try:
                win32print.ClosePrinter(hprinter)
            except Exception as e:
                print(f"ADVERTENCIA ClosePrinter: {e}")


def desactivar_factura(factura_id):
    inicio = time.perf_counter()

    try:
        respuesta = session_http.get(f"{URL_DESACTIVAR}/{factura_id}", timeout=8)
        duracion = time.perf_counter() - inicio

        try:
            datos = respuesta.json()
        except Exception:
            datos = None

        if respuesta.status_code == 200 and isinstance(datos, dict) and datos.get("ok"):
            print(f"Factura {factura_id} desactivada en {duracion:.2f}s")
            return True

        if datos is not None:
            print(
                f"ADVERTENCIA: No se pudo desactivar factura {factura_id} en {duracion:.2f}s: "
                f"HTTP {respuesta.status_code} {datos}"
            )
        else:
            print(
                f"ADVERTENCIA: No se pudo desactivar factura {factura_id} en {duracion:.2f}s: "
                f"HTTP {respuesta.status_code}. Respuesta: {texto_parcial_respuesta(respuesta)}"
            )
        return False

    except Exception as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: No se pudo desactivar factura {factura_id} en {duracion:.2f}s: {e}")
        return False


def parsear_item_factura(item):
    item = str(item or "").strip()

    if " - $" not in item:
        print(f"ADVERTENCIA: Item sin precio reconocible: {item}")
        return item, None

    nombre, precio_texto = item.rsplit(" - $", 1)
    nombre = nombre.strip()
    precio = a_float(precio_texto, None)

    if precio is None:
        print(f"ADVERTENCIA: Precio no reconocido en item: {item}")
        return item, None

    return nombre, precio


def construir_texto_factura(orden, tasa):
    total_usd = a_float(orden.get("total"))
    total_bs = round(total_usd * tasa, 2)
    usuario = orden.get("usuario") or "N/A"
    numero = orden.get("numero") or orden.get("id") or "-"
    tipo = orden.get("tipo") or "-"
    cliente = orden.get("cliente") or "-"
    items = orden.get("items") or []

    texto = (
        "\n"
        "========================\n"
        "      CHINA HOUSE\n"
        "========================\n\n"
        f"FACTURA - ORDEN #{numero}\n"
        f"MESONERA: {str(usuario).upper()}\n\n"
        f"TIPO: {tipo}\n"
        f"CLIENTE: {cliente}\n"
        "------------------------\n\n"
    )

    if not items:
        print(f"ADVERTENCIA: Factura {orden.get('id')} viene sin items")
        texto += "Sin items\n"
    else:
        for item in items:
            nombre, precio_usd = parsear_item_factura(item)
            if precio_usd is None:
                texto += f"{nombre}\n"
                continue

            precio_bs = round(precio_usd * tasa, 2)
            texto += f"{nombre} - Bs {precio_bs}\n"

    texto += "\n------------------------\n"
    texto += f"TOTAL: Bs {total_bs}\n"
    texto += "------------------------\n\n\n"

    return texto


def construir_ticket_prueba():
    return (
        "\n"
        "========================\n"
        "      CHINA HOUSE\n"
        "========================\n"
        "PRUEBA DE IMPRESION\n"
        "Si puedes leer esto, la impresora funciona.\n"
        "========================\n"
    )


def imprimir_factura(orden):
    factura_id = orden.get("id")
    print(f"IMPRIMIENDO FACTURA: {factura_id}")

    tasa = obtener_tasa()
    texto = construir_texto_factura(orden, tasa)
    return imprimir(texto)


def procesar_factura(factura):
    factura_id = factura.get("id")
    if factura_id is None:
        print(f"ADVERTENCIA: Factura sin id, se omite: {factura}")
        return

    evento_impresion = str(factura.get("evento_impresion") or factura_id)

    if evento_impresion in impresos:
        if evento_impresion not in eventos_duplicados_reportados:
            print(f"Evento {evento_impresion} ya impreso, desactivando pendiente")
            eventos_duplicados_reportados.add(evento_impresion)
        desactivar_factura(factura_id)
        return

    impresa_correctamente = imprimir_factura(factura)

    if impresa_correctamente:
        impresos.add(evento_impresion)
        guardar_impreso(evento_impresion)
        desactivar_factura(factura_id)
    else:
        print(
            f"ADVERTENCIA: Evento {evento_impresion} no se marco como impreso "
            "porque fallo la impresion"
        )


def ejecutar_modo_prueba():
    print("Ejecutando prueba de impresion RAW...")
    ok = imprimir(construir_ticket_prueba())
    if ok:
        print("Prueba enviada correctamente al spooler de Windows.")
        return 0
    print("La prueba de impresion fallo. Revisa cola, driver, puerto o impresora.")
    return 1


def ejecutar_loop_facturas():
    global impresos

    impresos = cargar_impresos()

    while True:
        try:
            print("Buscando facturas...")
            facturas = obtener_facturas()

            for factura in facturas:
                procesar_factura(factura)

        except Exception as e:
            print(f"ERROR general: {e}")

        time.sleep(3)


def main():
    if "--test-print" in sys.argv:
        return ejecutar_modo_prueba()

    ejecutar_loop_facturas()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
