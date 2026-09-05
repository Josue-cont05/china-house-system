"""
printer_diagnostics.py

Motor de diagnostico y reparacion guiada de la impresora POS58, separado
por completo de Tkinter para poder probarlo sin hilos reales, sin GUI y
sin hardware.

Nace de un fallo real encontrado en la primera prueba en una PC limpia:
Windows emparejo la POS58 y creo DOS puertos Bluetooth SPP (COM3 y COM4,
"Serie estandar sobre el vinculo Bluetooth"), pero ninguno de los dos
podia abrirse (SerialException / OSError 22, timeout). La version
anterior de "CONFIGURAR IMPRESORA AUTOMATICAMENTE" dejaba la ventana en
"(No responde)" porque abrir un COM Bluetooth a medio crear puede
COLGARSE indefinidamente (no es un timeout de lectura: es la llamada de
apertura del sistema operativo la que no vuelve), y terminaba exponiendo
al usuario a elegir manualmente entre COM3/COM4.

Este modulo corrige eso con dos piezas:

1. `probar_apertura()`: ejecuta la apertura real en un hilo aparte con
   un limite de tiempo estricto. Si el hilo no vuelve a tiempo, se
   reporta como fallo por timeout y el llamador SIGUE (el hilo huerfano
   se abandona como daemon: Windows/pyserial no ofrecen una forma segura
   de cancelar una apertura de COM ya en curso).

2. `AsistenteDeteccion`: la maquina de estados de "probar candidatos uno
   por uno, sin bloquear, sin pedir seleccion manual, preguntando SI/NO
   solo cuando de verdad se envio una prueba de impresion". Recibe sus
   dependencias (como abrir un puerto, como preguntar SI/NO, donde
   avisar del progreso) por parametro, asi que la logica de decision se
   puede probar sin threading.Thread real y sin Tkinter.

Principio de UX (impuesto por la mision): el usuario ve estados humanos
genericos ("Comprobando conexion...", "Probando impresion..."), nunca
"COM3"/"SPP"/"OSError"/"SerialException"/"HWID" como mensaje principal.
Esos detalles quedan en `resultados` (para logs y "VER DETALLES
TECNICOS"), nunca en los textos que pasan por `en_progreso`.
"""

import threading
import time
from collections import namedtuple
from datetime import datetime
from pathlib import Path

import neko_config

# Estados finales de una sesion de deteccion/reparacion.
ESTADO_OK = "OK"
ESTADO_SIN_CANDIDATOS = "SIN_CANDIDATOS"
ESTADO_PAREADA_SIN_ENLACE = "PAIRED_BUT_NO_WORKING_SERIAL_LINK"

_TIMEOUT_APERTURA_SEG = 4.0


ResultadoPrueba = namedtuple("ResultadoPrueba", "puerto abrio error")


def probar_apertura(abridor, puerto, timeout=_TIMEOUT_APERTURA_SEG):
    """Ejecuta `abridor(puerto)` (una llamada que en el caso real abre el
    COM y manda una prueba de impresion, y que puede colgarse
    indefinidamente si el enlace Bluetooth quedo a medias) en un hilo
    aparte, con un limite de `timeout` segundos.

    Si `abridor` lanza una excepcion antes de agotar el timeout, se
    reporta como fallo con ese error. Si no vuelve a tiempo, se reporta
    como fallo por "timeout" y el hilo (daemon) se abandona: ni pyserial
    ni Windows ofrecen una forma segura de forzar el cierre de una
    apertura de COM en curso, pero al ser daemon nunca impide que el
    proceso principal (o los tests) terminen.

    Nunca lanza: siempre devuelve un ResultadoPrueba.
    """
    resultado = {}

    def _ejecutar():
        try:
            abridor(puerto)
            resultado["ok"] = True
        except Exception as e:
            resultado["ok"] = False
            resultado["error"] = str(e) or e.__class__.__name__

    hilo = threading.Thread(target=_ejecutar, daemon=True)
    hilo.start()
    hilo.join(timeout)

    if hilo.is_alive():
        return ResultadoPrueba(puerto=puerto, abrio=False, error="timeout")
    if resultado.get("ok"):
        return ResultadoPrueba(puerto=puerto, abrio=True, error=None)
    return ResultadoPrueba(puerto=puerto, abrio=False, error=resultado.get("error", "error desconocido"))


class AsistenteDeteccion:
    """Prueba `candidatos` (puertos ya ordenados por probabilidad, ver
    port_detection.ordenar_candidatos_por_probabilidad) uno por uno:

    - si un candidato NI SIQUIERA ABRE, se descarta en silencio y se
      sigue con el siguiente (nunca se le pregunta SI/NO al usuario algo
      que no llego a imprimir nada);
    - si abre, se pregunta SI/NO (via `preguntar_si_no`, sin argumentos:
      la pregunta en si misma no debe mencionar el puerto tecnico);
    - si el usuario confirma, termina con ESTADO_OK y ese puerto;
    - si el usuario dice que no, se sigue con el siguiente candidato;
    - si no queda ningun candidato, y al menos uno abrio pero ninguno
      fue confirmado, o ninguno abrio: ESTADO_PAREADA_SIN_ENLACE (salvo
      que no hubiera candidatos desde el principio: ESTADO_SIN_CANDIDATOS).

    `probador(puerto) -> ResultadoPrueba` es inyectable para poder
    probar la secuencia de decisiones sin threading.Thread real (los
    tests de threading/timeout viven aparte, contra `probar_apertura`).
    """

    def __init__(self, candidatos, probador, preguntar_si_no, en_progreso=None, log=None):
        self.candidatos = list(candidatos)
        self._probador = probador
        self._preguntar = preguntar_si_no
        self._progreso = en_progreso or (lambda texto: None)
        self._log = log
        self.resultados = []

    def _avisar(self, texto):
        self._progreso(texto)

    def ejecutar(self):
        total = len(self.candidatos)
        if total == 0:
            if self._log:
                self._log.info("Deteccion automatica: sin candidatos razonables")
            return ESTADO_SIN_CANDIDATOS, None, self.resultados

        for indice, puerto in enumerate(self.candidatos, start=1):
            self._avisar(f"Comprobando conexión ({indice}/{total})...")
            resultado = self._probador(puerto.device)
            self.resultados.append(resultado)
            if self._log:
                self._log.info(
                    "Candidato %s: abrio=%s error=%s", puerto.device, resultado.abrio, resultado.error
                )

            if not resultado.abrio:
                # No tiene sentido preguntar "¿salio la prueba?" de algo
                # que ni siquiera llego a abrirse: se sigue en silencio.
                continue

            self._avisar(f"Probando impresión ({indice}/{total})...")
            salio = self._preguntar()
            if self._log:
                self._log.info("Confirmacion candidato %s: %s", puerto.device, "SI" if salio else "NO")
            if salio:
                return ESTADO_OK, puerto, self.resultados

        return ESTADO_PAREADA_SIN_ENLACE, None, self.resultados


def esperar_puertos_nuevos(obtener_puertos, snapshot_antes, intentos=5, espera_seg=1.0, dormir=time.sleep):
    """Para el asistente de reparacion: reintenta listar puertos
    esperando a que aparezcan tarde (algunos enlaces Bluetooth tardan
    unos segundos en crear su COM tras un reemparejamiento). Compara
    contra `snapshot_antes` (lista de ListPortInfo/stub ya tomada antes
    de pedirle al usuario que reempareje) por `.device`.

    Devuelve (puertos_actuales, nuevos). `dormir`/`obtener_puertos` son
    inyectables para no depender de time.sleep real en los tests.
    """
    antes = {p.device for p in snapshot_antes}
    actuales = list(snapshot_antes)
    for _ in range(intentos):
        actuales = list(obtener_puertos())
        nuevos = [p for p in actuales if p.device not in antes]
        if nuevos:
            return actuales, nuevos
        dormir(espera_seg)
    return actuales, []


Diagnostico = namedtuple(
    "Diagnostico",
    "bluetooth pos58_pareada candidatos resultados estado puerto_confirmado marca_tiempo",
)


def construir_diagnostico(
    candidatos,
    resultados,
    estado,
    puerto_confirmado=None,
    bluetooth=None,
    pos58_pareada=None,
    marca_tiempo=None,
):
    return Diagnostico(
        bluetooth=bluetooth,
        pos58_pareada=pos58_pareada,
        candidatos=list(candidatos),
        resultados=list(resultados),
        estado=estado,
        puerto_confirmado=puerto_confirmado,
        marca_tiempo=marca_tiempo or datetime.now(),
    )


def _texto_estado_bool(valor, si, no, desconocido="Desconocido"):
    if valor is True:
        return si
    if valor is False:
        return no
    return desconocido


def resumen_humano(diagnostico):
    """Lineas (etiqueta, valor) en lenguaje humano para la vista
    "DIAGNÓSTICO DE IMPRESORA" (nunca nombres de COM ni excepciones)."""
    algun_candidato_abrio = any(r.abrio for r in diagnostico.resultados)

    if diagnostico.estado == ESTADO_OK:
        enlace, prueba = "OK", "OK"
    elif algun_candidato_abrio:
        enlace, prueba = "OK", "Pendiente"
    elif diagnostico.resultados:
        enlace, prueba = "Problema", "Pendiente"
    else:
        enlace, prueba = "Desconocido", "Pendiente"

    return [
        ("Bluetooth", _texto_estado_bool(diagnostico.bluetooth, "OK", "Problema")),
        ("POS58", _texto_estado_bool(diagnostico.pos58_pareada, "Emparejada", "No encontrada")),
        ("Enlace de impresión", enlace),
        ("Prueba", prueba),
    ]


def formatear_diagnostico_texto(diagnostico, version_texto, frozen, sistema=None):
    """Texto plano para "COPIAR DIAGNÓSTICO"/"GUARDAR DIAGNÓSTICO". No
    incluye credenciales, tokens, datos de clientes ni de ventas: este
    subsistema no maneja ninguno de esos datos, solo hardware/config
    local de impresora."""
    lineas = [
        "Neko Local - Diagnostico de impresora",
        f"Version: {version_texto}",
        f"Frozen: {frozen}",
        f"Sistema: {sistema or 'desconocido'}",
        f"Generado: {diagnostico.marca_tiempo.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Bluetooth disponible: {diagnostico.bluetooth}",
        f"POS58 emparejada (segun Windows): {diagnostico.pos58_pareada}",
        f"Estado final: {diagnostico.estado}",
        f"Puerto confirmado: {diagnostico.puerto_confirmado.device if diagnostico.puerto_confirmado else '-'}",
        "",
        "Candidatos detectados:",
    ]
    for candidato in diagnostico.candidatos:
        lineas.append(
            f"  - {candidato.device}: {getattr(candidato, 'description', '') or ''} "
            f"| hwid={getattr(candidato, 'hwid', None)}"
        )
    if not diagnostico.candidatos:
        lineas.append("  (ninguno)")

    lineas.append("")
    lineas.append("Resultados de prueba:")
    for resultado in diagnostico.resultados:
        estado_resultado = "abrio" if resultado.abrio else f"fallo ({resultado.error})"
        lineas.append(f"  - {resultado.puerto}: {estado_resultado}")
    if not diagnostico.resultados:
        lineas.append("  (ninguno probado)")

    return "\n".join(lineas)


def guardar_diagnostico(texto, ruta=None):
    """Guarda el texto de diagnostico en %LOCALAPPDATA%\\NekoWok\\logs\\
    (o en `ruta` si se indica, para tests). Devuelve la Path final."""
    if ruta is None:
        ruta = neko_config.logs_dir() / f"diagnostico_{datetime.now():%Y%m%d_%H%M%S}.txt"
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta
