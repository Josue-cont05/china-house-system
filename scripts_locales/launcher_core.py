"""
launcher_core.py

Logica de orquestacion de Neko Local SIN interfaz grafica, para que se
pueda probar sin Tkinter, sin abrir puertos reales y sin hacer requests
reales. `neko_local.py` (la GUI) solo llama a estas funciones y pinta el
resultado.

Responsabilidades:
- decidir/actualizar que puerto usar (via port_detection.resolver_puerto);
- arrancar/detener el worker de cocina como proceso hijo, sin matar nada
  que este launcher no haya iniciado el mismo;
- comprobar, de forma ligera, si NekoPOS responde.
"""

import subprocess
import sys
from pathlib import Path

import requests

import neko_config
import port_detection

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent
WORKER_COCINA_PATH = SCRIPTS_LOCALES_DIR / "script_comanda_cocina.py"

# Endpoint liviano ya usado por script_factura.py para comprobar conexion;
# reutilizarlo evita inventar un segundo mecanismo de "ping" a NekoPOS.
_URL_VERIFICACION = f"{neko_config.NEKOPOS_BASE_URL}/api/tasa"


def resolver_y_persistir_puerto(config=None):
    """Resuelve el puerto a usar a partir de la config guardada. Si la
    huella encuentra un nuevo COM inequivoco, persiste la config
    actualizada (asi el usuario nunca tiene que enterarse del cambio de
    numero de puerto). Devuelve el `ResultadoResolucion` de port_detection.
    """
    config = neko_config.cargar_config() if config is None else config
    resultado = port_detection.resolver_puerto(config)
    if resultado.status == "rematched":
        neko_config.guardar_config(resultado.config)
    return resultado


def nekopos_accesible(timeout=3):
    try:
        respuesta = requests.get(_URL_VERIFICACION, timeout=timeout)
        return respuesta.status_code == 200
    except Exception:
        return False


def _python_actual():
    """Interprete a usar para lanzar el worker hijo: el mismo con el que
    corre este proceso (funciona igual en python.exe, pythonw.exe o un
    venv), para no reintroducir la busqueda de interprete que ya resuelve
    INICIAR_NEKO.bat al arrancar Neko Local."""
    return sys.executable


class GestorWorkerCocina:
    """Arranca/detiene el worker de cocina como proceso hijo y solo puede
    detener el que el mismo arranco (nunca mata procesos ajenos)."""

    def __init__(self, worker_path=WORKER_COCINA_PATH, python_exe=None):
        self.worker_path = Path(worker_path)
        self._python_exe = python_exe
        self._proceso = None

    @property
    def activo(self):
        return self._proceso is not None and self._proceso.poll() is None

    def iniciar(self, puerto):
        if self.activo:
            return self._proceso

        python_exe = self._python_exe or _python_actual()
        comando = [python_exe, str(self.worker_path)]
        if puerto:
            comando += ["--port", puerto]

        self._proceso = subprocess.Popen(
            comando,
            cwd=str(self.worker_path.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return self._proceso

    def detener(self, timeout=5):
        if not self.activo:
            self._proceso = None
            return True

        self._proceso.terminate()
        try:
            self._proceso.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proceso.kill()
            self._proceso.wait(timeout=timeout)
        finally:
            self._proceso = None
        return True
