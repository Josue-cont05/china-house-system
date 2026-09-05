"""
bluetooth_printer.py

Modulo independiente para imprimir comandas en una impresora termica POS58
(controlador YICHIP) conectada por Bluetooth SPP como puerto serie virtual
(Windows la expone como puerto COM, en este entorno COM6 a 9600 baudios).

Uso basico:

    from bluetooth_printer import BluetoothPrinter

    with BluetoothPrinter(port="COM6") as printer:
        printer.align("center")
        printer.set_bold(True)
        printer.print_line("NEKO WOK")
        printer.set_bold(False)
        printer.feed(3)
"""

from __future__ import annotations

import os
import textwrap

import serial
from serial import SerialException


class PrinterError(Exception):
    """Error generico al operar la impresora."""


class PrinterConnectionError(PrinterError):
    """Error al conectar o desconectar del puerto serie."""


class PrinterImageError(PrinterError):
    """Error al preparar o imprimir una imagen (logo)."""


class BluetoothPrinter:
    """Encapsula el envio de comandos ESC/POS a una impresora POS58 por Bluetooth SPP."""

    # Comandos ESC/POS
    _ESC = b"\x1b"
    _GS = b"\x1d"

    _CMD_INIT = _ESC + b"@"
    _CMD_ALIGN = _ESC + b"a"          # + n (0 izquierda, 1 centro, 2 derecha)
    _CMD_BOLD = _ESC + b"E"           # + 0/1
    _CMD_SIZE = _GS + b"!"            # + n (0x00 normal, 0x11 doble ancho/alto)
    _CMD_CODEPAGE = _ESC + b"t"       # + n (tabla de caracteres)
    _CMD_RASTER = _GS + b"v" + b"\x30"  # + m xL xH yL yH + datos (bit image)

    _ALIGN_MAP = {"left": 0, "center": 1, "right": 2}

    # Ancho maximo de impresion en POS58 (58 mm) en pixeles, multiplo de 8.
    MAX_LOGO_WIDTH_PX = 340

    # Valor de gris (0-255) a partir del cual un pixel se considera fondo
    # (blanco) al recortar los margenes externos de un logo.
    _LOGO_MARGEN_UMBRAL = 245

    # Valor de gris (0-255): por debajo se convierte a negro puro, desde ahi
    # a blanco puro. Reemplaza el dithering (que ensuciaba el resultado a
    # tamanos pequenos) por un blanco/negro limpio.
    _LOGO_BN_UMBRAL = 160

    def __init__(
        self,
        port: str = "COM6",
        baudrate: int = 9600,
        timeout: float = 2.0,
        codepage: int = 16,
        encoding: str = "cp1252",
        chars_per_line: int = 32,
    ) -> None:
        """
        port: puerto COM asignado al Bluetooth SPP (verificado: COM6).
        baudrate: velocidad de conexion (verificado: 9600).
        codepage: tabla de caracteres ESC/POS a activar en la impresora.
            2 = CP850 (Latin-1 / Europa Occidental), incluye á é í ó ú ñ Ñ ¿ ¡.
            Si los acentos no salen correctos en tu impresora, prueba otros
            valores comunes en clones POS58: 0 (CP437), 16 (WPC1252), 19, 3.
        encoding: codificacion Python usada para convertir el texto a bytes,
            debe corresponder con el codepage seleccionado (cp850 por defecto).
        chars_per_line: ancho util de la impresora en caracteres, usado por
            print_wrapped() para ajustar texto largo. 32 es el valor tipico
            para impresoras de 58 mm con la fuente normal (Font A).
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.codepage = codepage
        self.encoding = encoding
        self.chars_per_line = chars_per_line
        self._serial: serial.Serial | None = None

    # ------------------------------------------------------------------
    # Conexion
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Abre el puerto serie e inicializa la impresora."""
        if self._serial is not None and self._serial.is_open:
            return
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
        except SerialException as exc:
            self._serial = None
            raise PrinterConnectionError(
                f"No se pudo abrir el puerto {self.port}: {exc}"
            ) from exc

        self._write(self._CMD_INIT)
        self._write(self._CMD_CODEPAGE + bytes([self.codepage]))

    def disconnect(self) -> None:
        """Cierra el puerto serie si esta abierto."""
        if self._serial is not None:
            try:
                self._serial.close()
            except SerialException as exc:
                raise PrinterConnectionError(
                    f"Error al cerrar el puerto {self.port}: {exc}"
                ) from exc
            finally:
                self._serial = None

    def __enter__(self) -> "BluetoothPrinter":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    # Envio de datos
    # ------------------------------------------------------------------
    def _write(self, data: bytes) -> None:
        if self._serial is None or not self._serial.is_open:
            raise PrinterConnectionError(
                "La impresora no esta conectada. Llama a connect() primero."
            )
        try:
            self._serial.write(data)
            self._serial.flush()
        except SerialException as exc:
            raise PrinterError(f"Error al enviar datos a la impresora: {exc}") from exc

    def send_bytes(self, data: bytes) -> None:
        """Envia bytes crudos (ESC/POS u otros) a la impresora."""
        self._write(data)

    def _encode(self, text: str) -> bytes:
        return text.encode(self.encoding, errors="replace")

    # ------------------------------------------------------------------
    # Texto
    # ------------------------------------------------------------------
    def print_text(self, text: str) -> None:
        """Imprime texto sin salto de linea final."""
        self._write(self._encode(text))

    def print_line(self, text: str = "") -> None:
        """Imprime una linea de texto seguida de un salto de linea."""
        self._write(self._encode(text) + b"\n")

    def print_image(
        self,
        path: str,
        max_width: int = MAX_LOGO_WIDTH_PX,
        offset_x: int = 0,
        canvas_width: int | None = None,
    ) -> None:
        """Imprime un logo centrado en formato ESC/POS raster (GS v 0).

        - Recorta los margenes blancos/transparentes externos, usando solo
          el contenido real de la imagen.
        - La ajusta proporcionalmente a un maximo de `max_width` px de ancho
          (por defecto 340 px, dentro del ancho util tipico de una POS58 de 58 mm).
        - Mejora nitidez/contraste y convierte a blanco/negro por umbral fijo
          (sin dithering, que ensucia el resultado a tamanos pequenos).
        - Deja 1 linea de separacion despues de imprimirla.

        Centrado:
        - Si `canvas_width` es None (por defecto, compatible con llamadas
          existentes): se centra sobre un ancho de `max_width` px, y ese
          bloque se desplaza `offset_x` px hacia la derecha (0 = sin
          desplazamiento). Con logos mas angostos que el ancho fisico de la
          POS58 (~384 px), esto imprime pegado al margen izquierdo real del
          papel, no centrado en la hoja.
        - Si se indica `canvas_width` (p. ej. 384, el ancho imprimible real
          de una POS58 de 58 mm): el raster final mide exactamente
          `canvas_width` px y el logo (ya redimensionado a `max_width`) se
          centra matematicamente dentro de ese ancho fisico -- este es el
          centrado real recomendado, no depende de "espacios" de texto.
          `offset_x` se sigue sumando encima como ajuste manual opcional
          (0 por defecto).

        Lanza PrinterImageError si el archivo no existe, si Pillow no esta
        instalado, o si la imagen no se puede procesar.
        """
        if not os.path.isfile(path):
            raise PrinterImageError(f"No se encontro el archivo de imagen: {path}")

        try:
            from PIL import Image, ImageFilter, ImageOps
        except ImportError as exc:
            raise PrinterImageError(
                "Pillow no esta instalado. Instala la dependencia con: "
                "pip install -r requirements.txt"
            ) from exc

        try:
            opened = Image.open(path)
            has_alpha = opened.mode in ("RGBA", "LA") or (
                opened.mode == "P" and "transparency" in opened.info
            )
            if has_alpha:
                opened = opened.convert("RGBA")
                background = Image.new("RGBA", opened.size, (255, 255, 255, 255))
                opened = Image.alpha_composite(background, opened)
            source = opened.convert("L")
        except Exception as exc:
            raise PrinterImageError(
                f"No se pudo abrir o procesar la imagen '{path}': {exc}"
            ) from exc

        # Recortar margenes externos blancos/transparentes: usar solo el
        # contenido real (evita que un margen asimetrico descentre el logo).
        mascara_contenido = source.point(
            lambda p: 255 if p < self._LOGO_MARGEN_UMBRAL else 0
        )
        bbox = mascara_contenido.getbbox()
        if bbox:
            source = source.crop(bbox)

        paper_width = max_width - (max_width % 8)  # multiplo de 8 requerido

        if source.width > paper_width:
            scale = paper_width / source.width
            new_size = (paper_width, max(1, round(source.height * scale)))
            source = source.resize(new_size, Image.LANCZOS)

        # Recuperar nitidez perdida en el resize y normalizar contraste antes
        # de binarizar, para que el gato/wok/texto se mantengan legibles.
        source = ImageOps.autocontrast(source, cutoff=1)
        source = source.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=2))

        # Blanco/negro limpio por umbral fijo (ya sin dithering: los valores
        # quedan puros 0/255 antes de la conversion final a modo "1").
        source = source.point(lambda p: 255 if p >= self._LOGO_BN_UMBRAL else 0)

        # Ancho final del raster y posicion horizontal del logo dentro de el.
        offset_x = max(offset_x, 0)
        if canvas_width is not None:
            # Centrado real: el lienzo es el ancho fisico indicado, y el
            # logo se centra matematicamente dentro de ese ancho.
            raster_width = canvas_width - (canvas_width % 8)
            x_offset = offset_x + (raster_width - source.width) // 2
        else:
            # Comportamiento previo (compatible): el lienzo es max_width (+
            # offset_x si se pide desplazarlo), no el ancho fisico del papel.
            raster_width = paper_width + offset_x
            raster_width -= raster_width % 8
            x_offset = offset_x + (paper_width - source.width) // 2

        canvas = Image.new("L", (raster_width, source.height), color=255)
        canvas.paste(source, (x_offset, 0))

        bw = canvas.convert("1", dither=Image.Dither.NONE)
        bytes_per_row = raster_width // 8
        pixels = bw.load()

        data = bytearray()
        for y in range(bw.height):
            for byte_index in range(bytes_per_row):
                byte = 0
                base_x = byte_index * 8
                for bit in range(8):
                    if pixels[base_x + bit, y] == 0:  # 0 = negro
                        byte |= 0x80 >> bit
                data.append(byte)

        height = bw.height
        header = self._CMD_RASTER + bytes(
            [
                0x00,  # m: modo normal
                bytes_per_row & 0xFF,
                (bytes_per_row >> 8) & 0xFF,
                height & 0xFF,
                (height >> 8) & 0xFF,
            ]
        )
        self._write(header + bytes(data))
        self._write(b"\n")

    def wrap_text(self, text: str, width: int | None = None) -> list[str]:
        """Divide un texto en lineas que respetan el ancho util de la
        impresora (58 mm), cortando unicamente por espacios entre palabras.
        Nunca parte una palabra entre dos lineas.
        """
        w = width or self.chars_per_line
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            wrapped = textwrap.wrap(
                paragraph,
                width=w,
                break_long_words=False,
                break_on_hyphens=False,
            )
            lines.extend(wrapped or [""])
        return lines

    def print_wrapped(self, text: str, width: int | None = None) -> None:
        """Imprime texto largo (p. ej. observaciones) ajustado al ancho de
        papel de 58 mm, con salto de linea por palabras, sin partir palabras.
        """
        for line in self.wrap_text(text, width):
            self.print_line(line)

    def feed(self, lines: int = 1) -> None:
        """Avanza el papel n lineas en blanco."""
        for _ in range(max(lines, 0)):
            self._write(b"\n")

    # ------------------------------------------------------------------
    # Formato
    # ------------------------------------------------------------------
    def align(self, mode: str) -> None:
        """Alineacion del texto: 'left', 'center' o 'right'."""
        if mode not in self._ALIGN_MAP:
            raise ValueError("mode debe ser 'left', 'center' o 'right'")
        self._write(self._CMD_ALIGN + bytes([self._ALIGN_MAP[mode]]))

    def set_bold(self, enabled: bool) -> None:
        """Activa o desactiva la negrita."""
        self._write(self._CMD_BOLD + (b"\x01" if enabled else b"\x00"))

    def set_size(self, size: str = "normal") -> None:
        """Tamano de fuente: 'normal' o 'double' (doble ancho y alto)."""
        if size == "normal":
            self._write(self._CMD_SIZE + b"\x00")
        elif size == "double":
            self._write(self._CMD_SIZE + b"\x11")
        else:
            raise ValueError("size debe ser 'normal' o 'double'")

    def reset_format(self) -> None:
        """Restablece alineacion, negrita y tamano a los valores por defecto."""
        self.align("left")
        self.set_bold(False)
        self.set_size("normal")
