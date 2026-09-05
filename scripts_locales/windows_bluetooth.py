"""
windows_bluetooth.py

Consulta de SOLO LECTURA al inventario de dispositivos Bluetooth que
Windows ya conoce (Get-PnpDevice -Class Bluetooth), para poder distinguir
"la POS58 esta emparejada pero el enlace de impresion quedo incompleto"
de "no encontramos la POS58 en absoluto" -- sin que el usuario tenga que
abrir el Administrador de dispositivos ni una terminal.

Reglas duras de este modulo (no romperlas en cambios futuros):
- SOLO LECTURA: nunca cambia nada de la configuracion de Windows (no
  empareja, no desempareja, no instala nada).
- Se ejecuta oculto (sin ventana) y con timeout corto: NUNCA puede
  colgar la GUI, sin importar que PowerShell tarde, falle o no exista.
- Si algo sale mal (PowerShell ausente, timeout, execution policy,
  salida inesperada) se devuelve "desconocido" (None). Nunca se inventa
  un True/False sin evidencia real de Windows.
"""

import json
import subprocess

import port_detection

_TIMEOUT_SEG = 5

_COMANDO_LISTAR = (
    "Get-PnpDevice -Class Bluetooth -PresentOnly | "
    "Select-Object FriendlyName, Status, InstanceId | ConvertTo-Json -Compress"
)


def _ejecutar_powershell(comando=_COMANDO_LISTAR, timeout=_TIMEOUT_SEG, ejecutor=None):
    """Corre `comando` con powershell.exe oculto, con timeout. Nunca
    lanza una excepcion hacia el llamador: cualquier fallo se traduce en
    None. `ejecutor` es inyectable para tests (por defecto subprocess.run,
    nunca se ejecuta un proceso real durante los tests)."""
    ejecutor = ejecutor or subprocess.run
    try:
        proceso = ejecutor(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-Command",
                comando,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None

    if proceso.returncode != 0:
        return None

    salida = (proceso.stdout or "").strip()
    if not salida:
        return []  # comando OK, sin dispositivos Bluetooth presentes ahora

    try:
        datos = json.loads(salida)
    except ValueError:
        return None

    if isinstance(datos, dict):
        datos = [datos]
    if not isinstance(datos, list):
        return None
    return datos


def listar_dispositivos_bluetooth(ejecutor=None):
    """Lista de dicts {FriendlyName, Status, InstanceId} de dispositivos
    Bluetooth que Windows ya conoce (tipicamente: emparejados alguna
    vez). None si no se pudo determinar (nunca [] por error: [] significa
    "se pregunto y Windows no reporto ninguno")."""
    return _ejecutar_powershell(ejecutor=ejecutor)


def bluetooth_disponible(dispositivos=None, ejecutor=None):
    """True/False/None: hay al menos un adaptador/dispositivo Bluetooth
    presente segun Windows. None = no se pudo determinar."""
    if dispositivos is None:
        dispositivos = listar_dispositivos_bluetooth(ejecutor=ejecutor)
    if dispositivos is None:
        return None
    return len(dispositivos) > 0


def buscar_dispositivo_pos58(dispositivos=None, ejecutor=None):
    """Primer dispositivo Bluetooth cuyo nombre sugiere una POS58 (mismas
    palabras clave que port_detection usa para los puertos serie), o
    None si no hay ninguno o no se pudo determinar."""
    if dispositivos is None:
        dispositivos = listar_dispositivos_bluetooth(ejecutor=ejecutor)
    if not dispositivos:
        return None
    for dispositivo in dispositivos:
        if port_detection.es_nombre_candidato(dispositivo.get("FriendlyName")):
            return dispositivo
    return None


def evaluar_bluetooth(ejecutor=None):
    """Una sola consulta a Windows, dos respuestas: (bluetooth_ok,
    pos58_pareada), cada una True/False/None. Si bluetooth_ok es None
    (no se pudo preguntar), pos58_pareada tambien es None: no tiene
    sentido afirmar "no esta emparejada" si ni siquiera se pudo
    preguntar."""
    dispositivos = listar_dispositivos_bluetooth(ejecutor=ejecutor)
    if dispositivos is None:
        return None, None
    bluetooth_ok = len(dispositivos) > 0
    pos58_pareada = buscar_dispositivo_pos58(dispositivos) is not None
    return bluetooth_ok, pos58_pareada
