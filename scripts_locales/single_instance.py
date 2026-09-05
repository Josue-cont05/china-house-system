"""
single_instance.py

Proteccion de instancia unica para el worker de cocina (y, en el futuro,
el de facturas), usando un mutex con nombre de Windows via ctypes.

Por que un named mutex y no un archivo de bloqueo (lock file): un mutex de
Windows lo libera el sistema operativo automaticamente si el proceso muere
(crash, kill, corte de luz) - no deja un lock "stale" que obligue a borrar
un archivo a mano para poder volver a arrancar. Un lock file requeriria
logica adicional (verificar PID vivo, manejar el archivo huerfano) para
lograr la misma garantia.

En Windows, dos objetos `SingleInstanceLock` con el MISMO `name` -- vengan
del mismo proceso o de dos procesos distintos -- solo permiten que UNO
adquiera el mutex; el segundo `acquire()` devuelve False. Eso es lo que
usan los tests (dos locks en el mismo proceso de prueba), sin necesitar
lanzar un segundo proceso real.

Fuera de Windows (dev en otro SO) no hay garantia real entre procesos:
`acquire()` siempre devuelve True. Documentado explicitamente, no se
pretende resolver aqui multiplataforma real.
"""

import sys

_ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    def __init__(self, name):
        self.name = name
        self._handle = None
        self._acquired = False

    @property
    def acquired(self):
        return self._acquired

    def acquire(self):
        if sys.platform != "win32":
            # Ver docstring del modulo: sin garantia real fuera de Windows.
            self._acquired = True
            return True

        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        error = kernel32.GetLastError()

        if not handle:
            raise OSError(f"No se pudo crear el mutex '{self.name}' (error {error})")

        if error == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            self._handle = None
            self._acquired = False
            return False

        self._handle = handle
        self._acquired = True
        return True

    def release(self):
        if self._handle is not None:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
