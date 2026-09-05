"""Genera un QR estatico (PNG, negro sobre blanco) para el footer
"PIDE DE NUEVO" del recibo de Mesa/Pick Up.

Se ejecuta UNA sola vez durante el desarrollo (o cuando cambie el
numero de WhatsApp): el PNG resultante se versiona en scripts_locales/,
y la impresion final NO depende de internet ni de la libreria qrcode
en tiempo de ejecucion (factura_presentacion.py solo llama a
BluetoothPrinter.print_image() sobre el PNG ya generado).

qrcode es una dependencia de build (ya la usa el backend para el QR de
self-ordering, ver app/shared/qr/svg.py), NO una dependencia de Neko
Local: no hace falta agregarla a scripts_locales/requirements.txt.
"""

import sys
from pathlib import Path

import qrcode

# Mismo nivel de correccion de errores que el QR de self-ordering del
# backend (app/shared/qr/svg.py): M (~15% de recuperacion), buen
# equilibrio entre densidad y resistencia a suciedad/dobleces del papel
# termico.
ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_M
BOX_SIZE = 10
BORDER = 4


def generar_qr(texto, destino, box_size=BOX_SIZE, border=BORDER):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECTION,
        box_size=box_size,
        border=border,
    )
    qr.add_data(texto)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(destino)
    return destino


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: build_qr.py <texto> <destino.png>")
        sys.exit(2)
    ruta = generar_qr(sys.argv[1], sys.argv[2])
    print(f"QR generado: {ruta}")
