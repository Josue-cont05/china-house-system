"""
product_images.py (dominio)

Imagen OPCIONAL por producto (`productos.imagen_url`), usada por las
tarjetas del catalogo de /orden/<id>. Un producto sin imagen sigue
funcionando igual: la vista muestra un placeholder con el icono de su
categoria.

Por ahora la imagen es una referencia (no hay upload): una URL
http(s) o una ruta absoluta del propio servidor (p. ej.
`/static/productos/combo1.jpg`). Se valida aqui para que nunca llegue
al atributo `src` un esquema peligroso (`javascript:`, `data:`) ni una
URL relativa a protocolo (`//host`), que el navegador trataria como
externa sin que el admin lo note. Modulo puro: no toca BD ni Flask.
"""

IMAGEN_URL_MAX_LARGO = 500


class ImagenProductoInvalida(ValueError):
    pass


def normalizar_imagen_url(valor):
    """Devuelve la URL limpia, o None si viene vacia (= quitar imagen).
    Levanta ImagenProductoInvalida si el valor no es una referencia
    segura de imagen."""
    texto = (valor or "").strip()
    if not texto:
        return None
    if len(texto) > IMAGEN_URL_MAX_LARGO:
        raise ImagenProductoInvalida(
            f"La URL de imagen no puede superar {IMAGEN_URL_MAX_LARGO} caracteres."
        )
    if any(c.isspace() for c in texto) or any(c in texto for c in "\"'<>\\"):
        raise ImagenProductoInvalida("La URL de imagen contiene caracteres no permitidos.")

    minuscula = texto.lower()
    if minuscula.startswith("https://") or minuscula.startswith("http://"):
        return texto
    if texto.startswith("/") and not texto.startswith("//"):
        return texto
    raise ImagenProductoInvalida(
        "La imagen debe ser una URL http(s) o una ruta del servidor que empiece por '/'."
    )
