"""
script_comanda_cocina.py

Worker local de impresion de comandas de cocina de Neko Wok. Es el UNICO
proceso responsable de:

- hacer polling de /ordenes_cocina cada 3 segundos;
- decidir, por `evento_impresion`, que comanda ya fue impresa;
- persistir esa deduplicacion en disco (comandas_impresas.txt) para que
  reiniciar el script o Windows no reimprima comandas ya impresas;
- decidir el puerto serie a usar (COM6 en una PC puede ser COM8 en otra, o
  cambiar tras un reemparejamiento Bluetooth) y pasarselo explicito a la
  capa de presentacion - ver PUERTO mas abajo.

La impresion en si (formato, ESC/POS, BluetoothPrinter) vive en
comanda_presentacion.py, migrada tal cual desde el diseno fisicamente
aprobado en NekoPrinterTest. Este worker NO decide que items son nuevos:
cada evento de /ordenes_cocina ya es un lote (una orden_comanda) que trae
unicamente los items de ese envio - eso lo resuelve el backend de NekoPOS,
no este script.

PUERTO:
- Uso normal (via Neko Local, o manual sin argumentos): se lee la
  configuracion local guardada por Neko Local (neko_config.py) y se
  localiza el puerto vigente, incluso si cambio de numero de COM
  (port_detection.py). Si no hay impresora configurada, o hay ambiguedad,
  el worker lo indica claramente y no arranca el polling.
- Override de diagnostico: `python script_comanda_cocina.py --port COM6`
  fuerza ese puerto sin consultar la configuracion, util para probar en
  desarrollo sin pasar por el asistente de Neko Local.

INSTANCIA UNICA: antes de empezar a hacer polling, este worker toma un
mutex de Windows con nombre fijo (single_instance.py). Si ya hay un worker
corriendo (lanzado por Neko Local o manualmente), este segundo proceso lo
detecta, muestra un mensaje y termina limpiamente sin tocar el primero.

Ejecutar como servicio: python script_comanda_cocina.py
"""

import argparse
import time
from pathlib import Path

import requests

import neko_config
import port_detection
from bluetooth_printer import PrinterError
from comanda_presentacion import imprimir_comanda
from single_instance import SingleInstanceLock

URL_COCINA = f"{neko_config.NEKOPOS_BASE_URL}/ordenes_cocina"

NOMBRE_MUTEX_COCINA = "NekoWok_ComandaCocinaWorker"

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


def procesar_comanda(orden, puerto, baudrate=9600):
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
        imprimir_comanda(orden, puerto, baudrate=baudrate)
    except PrinterError as e:
        print(f"ERROR imprimiendo comanda (evento {evento_impresion}): {e}")
        return
    except Exception as e:
        print(f"ERROR inesperado imprimiendo comanda (evento {evento_impresion}): {e}")
        return

    print(f"[COCINA] impresion OK: {evento_impresion}")
    impresos.add(evento_impresion)
    guardar_impreso(evento_impresion)


def ejecutar_polling(puerto, baudrate=9600):
    global impresos

    impresos = cargar_impresos()
    print(f"Script de comandas iniciado. {len(impresos)} eventos previos cargados.")
    print(f"[COCINA] usando puerto={puerto} baudrate={baudrate}")

    while True:
        try:
            print("Buscando comandas...")
            ordenes = obtener_comandas()

            for orden in ordenes:
                procesar_comanda(orden, puerto, baudrate=baudrate)

        except Exception as e:
            print(f"ERROR general: {e}")

        time.sleep(3)


def resolver_puerto_worker(override_port):
    """Decide el puerto a usar al arrancar. Si `override_port` viene dado
    (--port), se usa directamente sin tocar la configuracion. Si no,
    resuelve contra la configuracion local, actualizandola si la huella
    encontro la impresora en un nuevo COM. Devuelve (puerto, baudrate) o
    (None, None) si no se puede resolver (y ya imprimio por que)."""
    if override_port:
        print(f"[COCINA] Puerto forzado por --port: {override_port}")
        return override_port, neko_config.DEFAULT_BAUDRATE

    config = neko_config.cargar_config()
    resultado = port_detection.resolver_puerto(config)

    if resultado.status == "ok":
        return resultado.port, config.get("baudrate", neko_config.DEFAULT_BAUDRATE)

    if resultado.status == "rematched":
        neko_config.guardar_config(resultado.config)
        print(f"[COCINA] La impresora cambio de puerto; ahora en {resultado.port}.")
        return resultado.port, resultado.config.get("baudrate", neko_config.DEFAULT_BAUDRATE)

    if resultado.status == "sin_configurar":
        print(
            "[COCINA] No hay impresora configurada todavia. "
            "Abre Neko Local y usa 'Configurar impresora'."
        )
        return None, None

    if resultado.status == "ambiguous":
        print(
            "[COCINA] Varios puertos coinciden con la impresora guardada; "
            "no se puede elegir automaticamente. Reconfigura desde Neko Local."
        )
        return None, None

    print(
        "[COCINA] No se encontro la impresora configurada (puerto guardado "
        "ausente y ninguna coincidencia por huella). Reconfigura desde Neko Local."
    )
    return None, None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Worker de impresion de comandas de cocina.")
    parser.add_argument("--port", default=None, help="Override manual de puerto (ej. COM6)")
    args = parser.parse_args(argv)

    puerto, baudrate = resolver_puerto_worker(args.port)
    if puerto is None:
        return 1

    lock = SingleInstanceLock(NOMBRE_MUTEX_COCINA)
    if not lock.acquire():
        print("[COCINA] Ya hay un worker de comandas en ejecucion en esta computadora. Cerrando.")
        return 0

    try:
        ejecutar_polling(puerto, baudrate=baudrate)
    finally:
        lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
