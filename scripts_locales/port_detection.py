"""
port_detection.py

Deteccion y "huella" (fingerprint) de puertos serie para localizar la POS58
sin depender de que el numero de puerto (COM6, COM8, ...) sea siempre el
mismo entre computadoras o entre reconexiones Bluetooth.

Reglas duras de este modulo (no romperlas en cambios futuros):
- NUNCA abre un puerto ni envia bytes. Solo lee metadatos que Windows/pyserial
  ya exponen (`serial.tools.list_ports.comports()`).
- NUNCA elige un puerto al azar cuando hay ambiguedad: si mas de un puerto
  coincide igual de bien, se reporta como ambiguo y el llamador debe pedir
  al usuario que elija.
"""

from collections import namedtuple

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - pyserial siempre deberia estar instalado
    list_ports = None

# Palabras clave que suelen aparecer en descripcion/manufacturer/hwid de una
# POS58 conectada por Bluetooth SPP (clones YICHIP incluidos). Todo en
# minusculas: la comparacion siempre pasa el texto por .lower() primero.
_PALABRAS_CLAVE_CANDIDATO = (
    "pos58",
    "yichip",
    "bluetooth",
    "standard serial over bluetooth link",
    "spp",
    "rn42",
    "hc-05",
    "hc-06",
)

# Campos de un ListPortInfo (o de un stub equivalente en tests) usados tanto
# para detectar candidatos como para construir la huella.
_CAMPOS_FINGERPRINT = (
    "hwid",
    "serial_number",
    "description",
    "manufacturer",
    "product",
    "vid",
    "pid",
)

ResultadoResolucion = namedtuple(
    "ResultadoResolucion", "status port config candidatos"
)


def listar_puertos():
    """Lista los puertos serie visibles ahora mismo. Nunca los abre."""
    if list_ports is None:
        return []
    return list(list_ports.comports())


def _texto_puerto(port_info):
    partes = [
        getattr(port_info, "description", None),
        getattr(port_info, "manufacturer", None),
        getattr(port_info, "hwid", None),
        getattr(port_info, "product", None),
    ]
    return " ".join(str(p) for p in partes if p).lower()


def es_candidato_pos58(port_info):
    """True si la descripcion/fabricante/hwid del puerto sugiere una POS58
    o un adaptador Bluetooth SPP generico (los clones no siempre se llaman
    "POS58" literalmente)."""
    texto = _texto_puerto(port_info)
    return any(palabra in texto for palabra in _PALABRAS_CLAVE_CANDIDATO)


def listar_candidatos(puertos=None):
    """Devuelve (candidatos, resto): candidatos = puertos que parecen POS58/
    Bluetooth SPP; resto = los demas puertos serie detectados (se muestran
    igual en el asistente, pero sin resaltar)."""
    puertos = listar_puertos() if puertos is None else list(puertos)
    candidatos = [p for p in puertos if es_candidato_pos58(p)]
    resto = [p for p in puertos if p not in candidatos]
    return candidatos, resto


def construir_fingerprint(port_info):
    """Huella de un puerto para volver a encontrarlo aunque cambie de
    numero de COM. No incluye `device` (el propio COM), justamente porque
    eso es lo que puede cambiar."""
    return {campo: getattr(port_info, campo, None) for campo in _CAMPOS_FINGERPRINT}


def _huella_coincide(port_info, fingerprint):
    if not fingerprint:
        return False
    actual = construir_fingerprint(port_info)
    # hwid y serial_number son los identificadores mas fuertes: si alguno
    # de los dos coincide y no es un valor vacio/generico, es suficiente.
    for campo in ("hwid", "serial_number"):
        esperado = fingerprint.get(campo)
        if esperado and actual.get(campo) == esperado:
            return True
    # Si no hay hwid/serial_number utilizables, exige description +
    # manufacturer iguales (mas debil, pero mejor que nada).
    if fingerprint.get("description") and fingerprint.get("manufacturer"):
        return (
            actual.get("description") == fingerprint.get("description")
            and actual.get("manufacturer") == fingerprint.get("manufacturer")
        )
    return False


def encontrar_por_fingerprint(fingerprint, puertos=None):
    """Busca puertos actuales cuya huella coincida con `fingerprint`.
    Devuelve la lista de coincidencias (puede tener 0, 1 o mas de 1)."""
    puertos = listar_puertos() if puertos is None else list(puertos)
    return [p for p in puertos if _huella_coincide(p, fingerprint)]


def resolver_puerto(config, puertos=None):
    """Decide que puerto usar a partir de la configuracion guardada.

    No abre ningun puerto: solo compara metadatos.

    status posibles:
    - "sin_configurar": no hay impresora guardada todavia.
    - "ok": el puerto guardado (`config['printer_port']`) sigue existiendo
      tal cual -> se usa sin tocar la config.
    - "rematched": el puerto guardado ya no existe, pero la huella
      encontro EXACTAMENTE un puerto nuevo -> se devuelve la config
      actualizada con el nuevo puerto (el llamador decide si persistirla).
    - "ambiguous": la huella coincide con mas de un puerto -> NO se elige
      ninguno, el llamador debe pedir seleccion manual.
    - "not_found": el puerto guardado desaparecio y la huella no encontro
      ningun candidato -> hace falta reconfigurar.
    """
    if not config.get("printer_port") and not config.get("printer_fingerprint"):
        return ResultadoResolucion("sin_configurar", None, None, [])

    puertos = listar_puertos() if puertos is None else list(puertos)

    puerto_guardado = config.get("printer_port")
    if puerto_guardado and any(p.device == puerto_guardado for p in puertos):
        return ResultadoResolucion("ok", puerto_guardado, config, [])

    fingerprint = config.get("printer_fingerprint")
    coincidencias = encontrar_por_fingerprint(fingerprint, puertos) if fingerprint else []

    if len(coincidencias) == 1:
        nuevo_puerto = coincidencias[0].device
        nueva_config = dict(config)
        nueva_config["printer_port"] = nuevo_puerto
        nueva_config["printer_fingerprint"] = construir_fingerprint(coincidencias[0])
        return ResultadoResolucion("rematched", nuevo_puerto, nueva_config, coincidencias)

    if len(coincidencias) > 1:
        return ResultadoResolucion("ambiguous", None, None, coincidencias)

    return ResultadoResolucion("not_found", None, None, [])
