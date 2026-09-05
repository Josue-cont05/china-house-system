"""
script_factura.py

Worker local de impresion de recibos de cliente de Neko Wok. Es el UNICO
proceso responsable de:

- hacer polling de /facturas_pendientes;
- decidir, por `evento_impresion`, que recibo ya fue impreso;
- persistir esa deduplicacion en disco (facturas_impresas.txt) para que
  reiniciar el script o Windows no reimprima recibos ya impresos;
- confirmar la impresion via /desactivar_factura despues de imprimir con
  exito (nunca antes);
- decidir el puerto serie a usar (config local de Neko Local, o --port de
  diagnostico), igual que script_comanda_cocina.py.

Esta worker NO calcula dinero: no consulta /api/tasa, no convierte
USD->Bs, no reconstruye precios ni descuentos. El contrato de
/facturas_pendientes (ver app/domain/sales/receipts.py, la unica
autoridad financiera) ya trae todo resuelto: subtotal, descuento,
delivery, total y total_bs. Esta worker solo lo pasa tal cual a
factura_presentacion.py.

Ubicacion de facturas_impresas.txt: se mantiene junto al script
(scripts_locales/facturas_impresas.txt), igual que antes de esta
migracion, para no ampliar el alcance de este bloque. Al empaquetar Neko
Local se evaluara moverla a %LOCALAPPDATA%\\NekoWok\\ junto a config.json.

PUERTO:
- Uso normal (via Neko Local, o manual sin argumentos): lee la
  configuracion local guardada por Neko Local y localiza el puerto
  vigente, incluso si cambio de numero de COM.
- Override de diagnostico: `python script_factura.py --port COM6`.

INSTANCIA UNICA: mutex de Windows con nombre propio (distinto del de
cocina), para que cocina y recibos puedan correr a la vez sin bloquearse
entre si, pero nunca dos workers de recibos simultaneos.

Ejecutar como servicio: python script_factura.py
"""

import argparse
import time
from pathlib import Path

import requests

import neko_config
import port_detection
from bluetooth_printer import PrinterError
from factura_presentacion import imprimir_factura
from single_instance import SingleInstanceLock

URL_FACTURAS = f"{neko_config.NEKOPOS_BASE_URL}/facturas_pendientes"
URL_DESACTIVAR = f"{neko_config.NEKOPOS_BASE_URL}/desactivar_factura"

NOMBRE_MUTEX_FACTURAS = "NekoWok_FacturaWorker"

BASE_DIR = Path(__file__).resolve().parent
ARCHIVO_IMPRESAS = BASE_DIR / "facturas_impresas.txt"

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


def texto_parcial_respuesta(respuesta, limite=220):
    try:
        texto = respuesta.text or ""
    except Exception:
        return ""
    texto = texto.replace("\n", " ").replace("\r", " ").strip()
    return texto[:limite]


def obtener_facturas():
    inicio = time.perf_counter()

    try:
        respuesta = session_http.get(URL_FACTURAS, timeout=3)
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

        if facturas:
            print(f"Facturas recibidas: {len(facturas)} en {duracion:.2f}s")
        return facturas

    except requests.exceptions.Timeout as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: Render lento buscando facturas en {duracion:.2f}s: {e}")
        return []
    except Exception as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: Error conexion facturas en {duracion:.2f}s: {e}")
        return []


def desactivar_factura(factura_id):
    inicio = time.perf_counter()

    try:
        respuesta = session_http.get(f"{URL_DESACTIVAR}/{factura_id}", timeout=2)
        duracion = time.perf_counter() - inicio

        try:
            datos = respuesta.json()
        except Exception:
            datos = None

        if respuesta.status_code == 200 and isinstance(datos, dict) and datos.get("ok"):
            print(f"Factura {factura_id} desactivada")
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

    except requests.exceptions.Timeout as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: Render lento desactivando factura {factura_id} en {duracion:.2f}s: {e}")
        return False
    except Exception as e:
        duracion = time.perf_counter() - inicio
        print(f"ADVERTENCIA: No se pudo desactivar factura {factura_id} en {duracion:.2f}s: {e}")
        return False


def procesar_factura(factura, puerto, baudrate=9600):
    factura_id = factura.get("id")
    if factura_id is None:
        print(f"ADVERTENCIA: Factura sin id, se omite: {factura}")
        return

    evento_impresion = str(factura.get("evento_impresion") or factura_id)

    if evento_impresion in impresos:
        if evento_impresion not in eventos_duplicados_reportados:
            print(f"[FACTURA] evento ya impreso, desactivando pendiente: {evento_impresion}")
            eventos_duplicados_reportados.add(evento_impresion)
        # El evento ya se imprimio fisicamente antes; si seguimos viendolo
        # es porque /desactivar_factura fallo en su momento. Reintentamos
        # SOLO la desactivacion, nunca la impresion.
        desactivar_factura(factura_id)
        return

    print(f"[FACTURA] evento recibido: evento={evento_impresion} factura_id={factura_id}")
    print(f"[FACTURA] enviando a impresora: {evento_impresion}")

    try:
        imprimir_factura(
            numero=factura.get("numero"),
            cliente=factura.get("cliente"),
            tipo=factura.get("tipo"),
            referencia=factura.get("referencia"),
            fecha_hora=factura.get("fecha_hora"),
            items=factura.get("items") or [],
            subtotal=factura.get("subtotal"),
            descuento=factura.get("descuento"),
            delivery=factura.get("delivery"),
            total=factura.get("total"),
            total_bs=factura.get("total_bs"),
            cobrada=factura.get("cobrada"),
            port=puerto,
            baudrate=baudrate,
        )
    except PrinterError as e:
        print(f"ERROR imprimiendo factura (evento {evento_impresion}): {e}")
        return
    except Exception as e:
        print(f"ERROR inesperado imprimiendo factura (evento {evento_impresion}): {e}")
        return

    print(f"[FACTURA] impresion OK: {evento_impresion}")
    impresos.add(evento_impresion)
    guardar_impreso(evento_impresion)

    if not desactivar_factura(factura_id):
        print(
            f"ADVERTENCIA: factura {factura_id} ya se imprimio pero no se pudo desactivar "
            "todavia; se reintentara la desactivacion en el proximo poll (no se reimprimira)."
        )


def resolver_puerto_worker(override_port):
    """Decide el puerto a usar al arrancar. Si `override_port` viene dado
    (--port), se usa directamente sin tocar la configuracion. Si no,
    resuelve contra la configuracion local, actualizandola si la huella
    encontro la impresora en un nuevo COM. Devuelve (puerto, baudrate) o
    (None, None) si no se puede resolver (y ya imprimio por que)."""
    if override_port:
        print(f"[FACTURA] Puerto forzado por --port: {override_port}")
        return override_port, neko_config.DEFAULT_BAUDRATE

    config = neko_config.cargar_config()
    resultado = port_detection.resolver_puerto(config)

    if resultado.status == "ok":
        return resultado.port, config.get("baudrate", neko_config.DEFAULT_BAUDRATE)

    if resultado.status == "rematched":
        neko_config.guardar_config(resultado.config)
        print(f"[FACTURA] La impresora cambio de puerto; ahora en {resultado.port}.")
        return resultado.port, resultado.config.get("baudrate", neko_config.DEFAULT_BAUDRATE)

    if resultado.status == "sin_configurar":
        print(
            "[FACTURA] No hay impresora configurada todavia. "
            "Abre Neko Local y usa 'Configurar impresora'."
        )
        return None, None

    if resultado.status == "ambiguous":
        print(
            "[FACTURA] Varios puertos coinciden con la impresora guardada; "
            "no se puede elegir automaticamente. Reconfigura desde Neko Local."
        )
        return None, None

    print(
        "[FACTURA] No se encontro la impresora configurada (puerto guardado "
        "ausente y ninguna coincidencia por huella). Reconfigura desde Neko Local."
    )
    return None, None


def ejecutar_polling(puerto, baudrate=9600):
    global impresos

    impresos = cargar_impresos()
    print(f"Script de facturas iniciado. {len(impresos)} eventos previos cargados.")
    print(f"[FACTURA] usando puerto={puerto} baudrate={baudrate}")

    while True:
        try:
            facturas = obtener_facturas()

            for factura in facturas:
                procesar_factura(factura, puerto, baudrate=baudrate)

            if facturas:
                continue

            print("Buscando facturas...")

        except Exception as e:
            print(f"ERROR general: {e}")

        time.sleep(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Worker de impresion de recibos de cliente.")
    parser.add_argument("--port", default=None, help="Override manual de puerto (ej. COM6)")
    args = parser.parse_args(argv)

    puerto, baudrate = resolver_puerto_worker(args.port)
    if puerto is None:
        return 1

    lock = SingleInstanceLock(NOMBRE_MUTEX_FACTURAS)
    if not lock.acquire():
        print("[FACTURA] Ya hay un worker de recibos en ejecucion en esta computadora. Cerrando.")
        return 0

    try:
        ejecutar_polling(puerto, baudrate=baudrate)
    finally:
        lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
