"""
script_comanda_cocina.py

Worker local de impresion de comandas de cocina de Neko Wok. Es el UNICO
proceso responsable de:

- hacer polling de /ordenes_cocina cada 3 segundos;
- decidir, por `evento_impresion`, que comanda ya fue impresa;
- persistir esa deduplicacion en disco (comandas_impresas.txt) para que
  reiniciar el script o Windows no reimprima comandas ya impresas.

La impresion en si (formato, ESC/POS, BluetoothPrinter COM6/9600) vive en
comanda_presentacion.py, migrada tal cual desde el diseno fisicamente
aprobado en NekoPrinterTest. Este worker NO decide que items son nuevos:
cada evento de /ordenes_cocina ya es un lote (una orden_comanda) que trae
unicamente los items de ese envio - eso lo resuelve el backend de NekoPOS,
no este script.

Ejecutar como servicio: python script_comanda_cocina.py
"""

import time
from pathlib import Path

import requests

from bluetooth_printer import PrinterError
from comanda_presentacion import imprimir_comanda

URL_COCINA = "https://neko-wok-system.onrender.com/ordenes_cocina"

# Resuelto desde la ubicacion de este archivo, no desde el working directory,
# para que funcione sin importar desde donde se ejecute el servicio.
BASE_DIR = Path(__file__).resolve().parent
ARCHIVO_IMPRESAS = BASE_DIR / "comandas_impresas.txt"

impresos = set()


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
        print(f"ADVERTENCIA: No se pudo guardar comanda impresa en {ARCHIVO_IMPRESAS}: {e}")
        return False


def obtener_comandas():
    try:
        respuesta = requests.get(URL_COCINA, timeout=10)
    except requests.exceptions.Timeout as e:
        print(f"ADVERTENCIA: Render lento consultando /ordenes_cocina: {e}")
        return []
    except Exception as e:
        print(f"ADVERTENCIA: Error de conexion consultando /ordenes_cocina: {e}")
        return []

    if respuesta.status_code != 200:
        print(f"ADVERTENCIA: /ordenes_cocina respondio HTTP {respuesta.status_code}")
        return []

    try:
        ordenes = respuesta.json()
    except Exception as e:
        print(f"ADVERTENCIA: /ordenes_cocina no devolvio JSON valido: {e}")
        return []

    if not isinstance(ordenes, list):
        print(f"ADVERTENCIA: /ordenes_cocina no devolvio una lista: {ordenes}")
        return []

    return ordenes


def procesar_comanda(orden):
    evento_impresion = orden.get("evento_impresion") or f"cocina_{orden.get('id')}"
    es_reimpresion = bool(orden.get("reimpresion_token"))

    if es_reimpresion:
        print(f"[COCINA] reimpresion recibida: evento={evento_impresion} comanda_id={orden.get('comanda_id')}")
    else:
        print(f"[COCINA] evento recibido: evento={evento_impresion} comanda_id={orden.get('comanda_id')}")

    if evento_impresion in impresos:
        print(f"[COCINA] evento ya impreso, se omite: {evento_impresion}")
        return

    print(f"[COCINA] enviando a impresora: {evento_impresion}")

    try:
        imprimir_comanda(orden)
    except PrinterError as e:
        print(f"ERROR imprimiendo comanda (evento {evento_impresion}): {e}")
        return
    except Exception as e:
        print(f"ERROR inesperado imprimiendo comanda (evento {evento_impresion}): {e}")
        return

    print(f"[COCINA] impresion OK: {evento_impresion}")
    impresos.add(evento_impresion)
    guardar_impreso(evento_impresion)


def ejecutar_polling():
    global impresos

    impresos = cargar_impresos()
    print(f"Script de comandas iniciado. {len(impresos)} eventos previos cargados.")

    while True:
        try:
            print("Buscando comandas...")
            ordenes = obtener_comandas()

            for orden in ordenes:
                procesar_comanda(orden)

        except Exception as e:
            print(f"ERROR general: {e}")

        time.sleep(3)


if __name__ == "__main__":
    ejecutar_polling()
