# -*- mode: python ; coding: utf-8 -*-
"""
NekoLocal.spec

PyInstaller spec de Neko Local: UN solo ejecutable (NekoLocal.exe) que
sirve de GUI y, relanzandose a si mismo con --kitchen-worker/
--receipt-worker, tambien de worker de cocina y de recibos (ver
scripts_locales/neko_local.py::main y
scripts_locales/launcher_core.py::GestorWorkerProceso).

ONEDIR (no ONEFILE): mas estable para Tkinter + Pillow + pyserial +
subprocess que relanza el mismo .exe - onefile descomprime a una carpeta
temporal en cada arranque, lo que complicaria justamente que
`sys.executable` siga siendo un .exe estable y que los assets vivan
"junto al .exe" (ver scripts_locales/resource_paths.py).

Solo se empaqueta lo que Neko Local necesita: GUI, workers, driver
Bluetooth/ESC-POS, presentacion, deteccion/configuracion, instancia
unica y los dos logos termicos. NO se empaqueta el backend NekoPOS
(Flask/Postgres/SQLite/app/ ni tests/): ese sigue viviendo unicamente en
Render.

Build: BUILD_NEKO_LOCAL.bat (o manualmente `pyinstaller NekoLocal.spec`).
"""

import sys
from pathlib import Path

block_cipher = None

REPO_ROOT = Path(SPECPATH)
SCRIPTS_LOCALES = REPO_ROOT / "scripts_locales"

# Los logos ESC/POS y el QR de WhatsApp (ver
# scripts_locales/resource_paths.py): se colocan en la RAIZ del onedir,
# junto al .exe, no en una subcarpeta - es justo donde
# resource_paths.recurso() los busca cuando esta frozen.
datas = [
    (str(SCRIPTS_LOCALES / "mini_logo_neko_thermal_01.png"), "."),
    (str(SCRIPTS_LOCALES / "logo_neko_thermal.png"), "."),
    (str(SCRIPTS_LOCALES / "qr_whatsapp_pedidos.png"), "."),
]

# print_dispatcher/script_comanda_cocina/script_factura se importan de
# forma DINAMICA (dentro de neko_local.main(), solo cuando
# --print-dispatcher/--kitchen-worker/--receipt-worker) - el analisis
# estatico de PyInstaller no los detecta solo; se declaran aqui
# explicitamente para que queden incluidos.
hiddenimports = [
    "print_dispatcher",
    "script_comanda_cocina",
    "script_factura",
    "comanda_presentacion",
    "factura_presentacion",
    "bluetooth_printer",
    "neko_config",
    "neko_log",
    "neko_version",
    "port_detection",
    "print_queue_client",
    "station_roles",
    "printer_diagnostics",
    "windows_bluetooth",
    "kitchen_ticket_times",
    "pytz",
    "resource_paths",
    "single_instance",
    "launcher_core",
    "serial",
    "serial.tools.list_ports",
    "PIL._tkinter_finder",
]

a = Analysis(
    [str(SCRIPTS_LOCALES / "neko_local.py")],
    pathex=[str(SCRIPTS_LOCALES)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # El backend NekoPOS (Flask/app/web_app.py) vive SOLO en Render: se
    # excluye explicitamente para que un import accidental nunca infle
    # el paquete ni arrastre dependencias de servidor a la PC del socio.
    excludes=["flask", "psycopg2", "web_app", "app"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NekoLocal",
    icon=str(SCRIPTS_LOCALES / "neko_local.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=True a proposito (no "--windowed"): con la consola oculta,
    # Windows deja sys.stdout/stderr en None y --version/--diagnostics
    # (pensados para diagnostico/soporte) quedarian mudos incluso con el
    # shim de neko_local.py. Los workers (--kitchen-worker/
    # --receipt-worker) igual arrancan SIN ventana de consola porque
    # launcher_core.GestorWorkerProceso los lanza con
    # creationflags=CREATE_NO_WINDOW; el unico efecto visible de
    # console=True es que, al abrir la GUI con doble clic, aparece
    # tambien una ventana de consola detras - tradeoff deliberado
    # (confiabilidad del diagnostico > estetica).
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NekoLocal",
)
