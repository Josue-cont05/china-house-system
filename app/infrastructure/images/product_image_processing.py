"""
product_image_processing.py (infraestructura / imagenes)

Valida y optimiza una imagen subida desde PC/tablet/telefono antes de
guardarla en la base de datos (app.infrastructure.database.product_images).

Seguridad:
- No se confia en la extension ni en el Content-Type del navegador: se
  mira la FIRMA real del archivo (JPEG / PNG / WebP) y ademas Pillow debe
  decodificarla con el mismo formato. SVG, HTML, GIF, PDF... se rechazan.
- Limite de tamano original (bytes) y de pixeles (bombas de descompresion).
- La imagen se RE-CODIFICA siempre: nunca se guardan los bytes subidos
  tal cual, y al re-codificar se descartan metadatos (EXIF con GPS, etc.).

Optimizacion:
- Respeta la orientacion EXIF de las fotos de telefono.
- Principal: lado mayor <= 1000 px. Miniatura: <= 400 px (tarjetas POS).
- WebP (calidad 80/75); si el Pillow del servidor no tiene WebP, JPEG.

Pillow se importa de forma diferida: si faltara en un despliegue, la app
arranca igual y solo la carga de imagenes responde con un error claro.
"""

from dataclasses import dataclass
from io import BytesIO

from app.domain.sales.product_images import ImagenProductoInvalida

TAMANO_MAXIMO_ORIGINAL = 8 * 1024 * 1024  # 8 MB, de sobra para una foto de telefono
PIXELES_MAXIMOS = 40_000_000  # ~ 8000x5000
LADO_MAXIMO = 1000
LADO_MINIATURA = 400
CALIDAD_PRINCIPAL = 80
CALIDAD_MINIATURA = 75
FORMATOS_PERMITIDOS = ("JPEG", "PNG", "WEBP")


@dataclass(frozen=True)
class ImagenProcesada:
    mime_type: str
    datos: bytes
    miniatura: bytes
    ancho: int
    alto: int
    tamano_original_bytes: int


def detectar_formato(datos):
    """Formato segun la firma binaria real, o None si no es JPEG/PNG/WebP."""
    if datos[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if len(datos) >= 12 and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "WEBP"
    return None


def _cargar_pillow():
    try:
        from PIL import Image, ImageOps, features
    except ImportError as exc:  # pragma: no cover - depende del despliegue
        raise ImagenProductoInvalida(
            "El servidor no tiene soporte de imagenes (falta Pillow)."
        ) from exc
    return Image, ImageOps, features


def _codificar(Image, imagen, lado, calidad, usar_webp):
    copia = imagen.copy()
    copia.thumbnail((lado, lado))
    salida = BytesIO()
    if usar_webp:
        copia.save(salida, format="WEBP", quality=calidad, method=4)
    else:
        if copia.mode != "RGB":
            fondo = copia.convert("RGBA")
            plano = Image.new("RGB", fondo.size, (28, 34, 48))
            plano.paste(fondo, mask=fondo.split()[-1])
            copia = plano
        copia.save(salida, format="JPEG", quality=calidad + 2, optimize=True, progressive=True)
    return salida.getvalue(), copia.size


def procesar_imagen_producto(datos):
    """bytes subidos -> ImagenProcesada. Levanta ImagenProductoInvalida."""
    if not datos:
        raise ImagenProductoInvalida("No se recibió ninguna imagen.")
    if len(datos) > TAMANO_MAXIMO_ORIGINAL:
        raise ImagenProductoInvalida(
            f"La imagen pesa demasiado (máximo {TAMANO_MAXIMO_ORIGINAL // (1024 * 1024)} MB)."
        )
    formato = detectar_formato(datos)
    if formato is None:
        raise ImagenProductoInvalida("Formato no permitido. Usa una imagen JPG, PNG o WebP.")

    Image, ImageOps, features = _cargar_pillow()
    try:
        with Image.open(BytesIO(datos)) as probe:
            if probe.format not in FORMATOS_PERMITIDOS or probe.format != formato:
                raise ImagenProductoInvalida("El contenido del archivo no coincide con una imagen válida.")
            ancho, alto = probe.size
            if ancho * alto > PIXELES_MAXIMOS:
                raise ImagenProductoInvalida("La imagen tiene demasiados píxeles.")
            probe.verify()
        imagen = Image.open(BytesIO(datos))
        imagen.seek(0)  # WebP/PNG animados: primer cuadro
        imagen.load()
        imagen = ImageOps.exif_transpose(imagen)
    except ImagenProductoInvalida:
        raise
    except Exception as exc:
        raise ImagenProductoInvalida("No se pudo leer la imagen; puede estar dañada.") from exc

    tiene_alfa = imagen.mode in ("RGBA", "LA") or (imagen.mode == "P" and "transparency" in imagen.info)
    imagen = imagen.convert("RGBA" if tiene_alfa else "RGB")

    usar_webp = bool(features.check("webp"))
    principal, (ancho_final, alto_final) = _codificar(Image, imagen, LADO_MAXIMO, CALIDAD_PRINCIPAL, usar_webp)
    miniatura, _ = _codificar(Image, imagen, LADO_MINIATURA, CALIDAD_MINIATURA, usar_webp)
    return ImagenProcesada(
        mime_type="image/webp" if usar_webp else "image/jpeg",
        datos=principal,
        miniatura=miniatura,
        ancho=ancho_final,
        alto=alto_final,
        tamano_original_bytes=len(datos),
    )
