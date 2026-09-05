"""Genera neko_local.ico (icono Windows multi-resolucion) a partir de un
PNG fuente (el arte de "NekoWok Printer": impresora termica + comanda).

No deforma la imagen: si el PNG no es cuadrado, se centra sobre un
lienzo cuadrado transparente (padding proporcional) antes de generar
las variantes de tamano, para que ningun tamano estire el dibujo.

Se ejecuta UNA sola vez durante el desarrollo (o cuando cambie el arte
fuente): el resultado (neko_local.ico) se versiona en
scripts_locales/, y la instalacion final NO depende del PNG original.
"""

import sys
from pathlib import Path

from PIL import Image

TAMANOS = (16, 24, 32, 48, 64, 128, 256)

# El arte fuente ("NekoWok Printer") es una insignia completa: gato,
# palmeras, atardecer, cinta con texto "NEKO WOK / IMPRIMIR COMANDAS",
# y la impresora+comanda en el centro. Reducir la insignia COMPLETA a
# 16-32px la vuelve un borron irreconocible (probado visualmente: a
# 16px no se distingue nada; a 32px la impresora apenas se intuye).
# Este recorte aisla la impresora+comanda (el elemento de mayor
# contraste de toda la insignia: cuerpo oscuro + papel blanco), que es
# el requisito explicito de la mision ("el objetivo principal a
# tamanos pequenos debe seguir siendo reconocible: IMPRESORA+COMANDA").
# Coordenadas ajustadas a mano sobre el PNG fuente de 1222x1287px.
RECORTE_FOCO = (300, 200, 980, 850)


def _lienzo_cuadrado(imagen):
    """Centra `imagen` (con su alpha intacto) sobre un lienzo cuadrado
    transparente del lado mayor de sus dos dimensiones. Si ya es
    cuadrada, la devuelve tal cual (sin copia innecesaria)."""
    ancho, alto = imagen.size
    lado = max(ancho, alto)
    if ancho == alto:
        return imagen

    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    offset = ((lado - ancho) // 2, (lado - alto) // 2)
    lienzo.paste(imagen, offset, imagen if imagen.mode == "RGBA" else None)
    return lienzo


def generar_ico(png_origen, ico_destino, recorte=RECORTE_FOCO, tamanos=TAMANOS):
    """Genera `ico_destino` a partir de `png_origen`, con las variantes
    de tamano en `tamanos`. Si `recorte` no es None, recorta primero a
    esa caja (left, top, right, bottom) -- ver RECORTE_FOCO. Preserva
    transparencia y proporciones (nunca deforma: el padding para
    cuadrar el lienzo, si hace falta, es transparente)."""
    origen = Image.open(png_origen)
    if origen.mode != "RGBA":
        origen = origen.convert("RGBA")

    if recorte is not None:
        origen = origen.crop(recorte)

    cuadrada = _lienzo_cuadrado(origen)

    ico_destino = Path(ico_destino)
    ico_destino.parent.mkdir(parents=True, exist_ok=True)
    cuadrada.save(ico_destino, format="ICO", sizes=[(t, t) for t in tamanos])
    return ico_destino


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: build_icon.py <png_origen> <ico_destino>")
        sys.exit(2)
    ruta = generar_ico(sys.argv[1], sys.argv[2])
    print(f"Icono generado: {ruta}")
