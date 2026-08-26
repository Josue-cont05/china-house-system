from io import BytesIO
from urllib.parse import quote

import qrcode
import qrcode.image.svg


def qr_svg_data_uri(texto):
    svg = qr_svg(texto)
    return f"data:image/svg+xml;utf8,{quote(svg, safe='')}"


def qr_svg(texto):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(texto)
    qr.make(fit=True)
    imagen = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    salida = BytesIO()
    imagen.save(salida)
    return salida.getvalue().decode("utf-8")
