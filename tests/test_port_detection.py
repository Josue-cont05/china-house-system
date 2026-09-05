"""Tests de port_detection.py (scripts_locales).

Nunca abre puertos reales: usa objetos stub con los mismos campos que
pyserial expone en ListPortInfo (device, description, hwid, manufacturer,
serial_number, product, vid, pid). `listar_puertos()` real (que llama a
pyserial) no se ejecuta en ningun test: siempre se pasa una lista de stubs
explicita a las funciones bajo prueba.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_LOCALES_DIR = Path(__file__).resolve().parent.parent / "scripts_locales"
if str(SCRIPTS_LOCALES_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LOCALES_DIR))

import port_detection  # noqa: E402


def _puerto(device, description="", manufacturer=None, hwid="", serial_number=None, product=None, vid=None, pid=None):
    return SimpleNamespace(
        device=device,
        description=description,
        manufacturer=manufacturer,
        hwid=hwid,
        serial_number=serial_number,
        product=product,
        vid=vid,
        pid=pid,
    )


POS58_BT = _puerto(
    "COM6",
    description="Standard Serial over Bluetooth link (COM6)",
    manufacturer="Microsoft",
    hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\7&1A2B3C4D&0&000000000000_00000001",
    serial_number="000000000000",
)
MOUSE_GENERICO = _puerto(
    "COM3", description="Puerto serie generico", manufacturer="ACME", hwid="USB\\VID_1234&PID_5678"
)
ARDUINO = _puerto(
    "COM5", description="USB-SERIAL CH340", manufacturer="wch.cn", hwid="USB\\VID_1A86&PID_7523"
)


class CandidatosPos58Test(unittest.TestCase):
    # 9. detectar candidatos POS58
    def test_pos58_bluetooth_es_candidato(self):
        self.assertTrue(port_detection.es_candidato_pos58(POS58_BT))

    # 10. Bluetooth generico
    def test_bluetooth_generico_por_descripcion_es_candidato(self):
        puerto = _puerto("COM8", description="Bluetooth-incoming-port")
        self.assertTrue(port_detection.es_candidato_pos58(puerto))

    def test_puerto_sin_relacion_no_es_candidato(self):
        self.assertFalse(port_detection.es_candidato_pos58(MOUSE_GENERICO))
        self.assertFalse(port_detection.es_candidato_pos58(ARDUINO))

    # 11. multiples COM
    def test_listar_candidatos_separa_candidatos_de_resto(self):
        candidatos, resto = port_detection.listar_candidatos([POS58_BT, MOUSE_GENERICO, ARDUINO])
        self.assertEqual(candidatos, [POS58_BT])
        self.assertEqual(resto, [MOUSE_GENERICO, ARDUINO])

    # 12. ningun COM
    def test_listar_candidatos_con_lista_vacia(self):
        candidatos, resto = port_detection.listar_candidatos([])
        self.assertEqual((candidatos, resto), ([], []))

    # 13. nunca abrir/probar puertos: estas funciones solo leen atributos,
    # nunca importan/usan bluetooth_printer ni serial.Serial.
    def test_modulo_no_importa_capa_de_hardware(self):
        import bluetooth_printer

        self.assertNotIn("BluetoothPrinter", vars(port_detection))
        self.assertFalse(hasattr(port_detection, "serial"))


class FingerprintTest(unittest.TestCase):
    def test_fingerprint_no_incluye_el_device(self):
        huella = port_detection.construir_fingerprint(POS58_BT)
        self.assertNotIn("device", huella)
        self.assertEqual(huella["hwid"], POS58_BT.hwid)

    def test_encontrar_por_fingerprint_usa_hwid(self):
        huella = port_detection.construir_fingerprint(POS58_BT)
        coincidencias = port_detection.encontrar_por_fingerprint(huella, [POS58_BT, MOUSE_GENERICO])
        self.assertEqual(coincidencias, [POS58_BT])

    def test_encontrar_por_fingerprint_sin_coincidencia(self):
        huella = port_detection.construir_fingerprint(POS58_BT)
        coincidencias = port_detection.encontrar_por_fingerprint(huella, [MOUSE_GENERICO, ARDUINO])
        self.assertEqual(coincidencias, [])


class ResolverPuertoTest(unittest.TestCase):
    def test_sin_config_previa(self):
        resultado = port_detection.resolver_puerto({"printer_port": None, "printer_fingerprint": None})
        self.assertEqual(resultado.status, "sin_configurar")

    def test_puerto_guardado_sigue_disponible(self):
        config = {
            "printer_port": "COM6",
            "printer_fingerprint": port_detection.construir_fingerprint(POS58_BT),
        }
        resultado = port_detection.resolver_puerto(config, puertos=[POS58_BT, MOUSE_GENERICO])
        self.assertEqual(resultado.status, "ok")
        self.assertEqual(resultado.port, "COM6")

    def test_puerto_guardado_desaparecio_pero_fingerprint_encuentra_uno(self):
        fingerprint = port_detection.construir_fingerprint(POS58_BT)
        config = {"printer_port": "COM6", "printer_fingerprint": fingerprint}

        pos58_en_nuevo_puerto = _puerto(
            "COM8",
            description=POS58_BT.description,
            manufacturer=POS58_BT.manufacturer,
            hwid=POS58_BT.hwid,
            serial_number=POS58_BT.serial_number,
        )

        resultado = port_detection.resolver_puerto(config, puertos=[pos58_en_nuevo_puerto, MOUSE_GENERICO])

        self.assertEqual(resultado.status, "rematched")
        self.assertEqual(resultado.port, "COM8")
        self.assertEqual(resultado.config["printer_port"], "COM8")

    def test_puerto_guardado_desaparecio_sin_ninguna_coincidencia(self):
        fingerprint = port_detection.construir_fingerprint(POS58_BT)
        config = {"printer_port": "COM6", "printer_fingerprint": fingerprint}

        resultado = port_detection.resolver_puerto(config, puertos=[MOUSE_GENERICO, ARDUINO])

        self.assertEqual(resultado.status, "not_found")
        self.assertIsNone(resultado.port)

    def test_fingerprint_ambiguo_no_selecciona_automaticamente(self):
        fingerprint = port_detection.construir_fingerprint(POS58_BT)
        config = {"printer_port": "COM6", "printer_fingerprint": fingerprint}

        # Dos puertos "iguales" a la huella (ej. dos adaptadores Bluetooth
        # genericos indistinguibles): NO se debe elegir ninguno solo.
        duplicado = _puerto(
            "COM9",
            description=POS58_BT.description,
            manufacturer=POS58_BT.manufacturer,
            hwid=POS58_BT.hwid,
            serial_number=POS58_BT.serial_number,
        )
        otro_igual = _puerto(
            "COM10",
            description=POS58_BT.description,
            manufacturer=POS58_BT.manufacturer,
            hwid=POS58_BT.hwid,
            serial_number=POS58_BT.serial_number,
        )

        resultado = port_detection.resolver_puerto(config, puertos=[duplicado, otro_igual])

        self.assertEqual(resultado.status, "ambiguous")
        self.assertIsNone(resultado.port)
        self.assertEqual(len(resultado.candidatos), 2)


YICHIP_EXPLICITO = _puerto(
    "COM7", description="YICHIP USB2.0-Serial", manufacturer="YICHIP", hwid="USB\\VID_1A86&PID_5523"
)
GENERICO_INCIERTO = _puerto("COM4", description="Puerto de comunicaciones", manufacturer=None, hwid="")


class PuntuarCandidatoTest(unittest.TestCase):
    """Puntuacion determinista usada SOLO por la deteccion automatica
    (CONFIGURAR IMPRESORA AUTOMATICAMENTE): decide orden de prueba y que
    puertos ni se prueban."""

    def test_pos58_bluetooth_puntua_positivo(self):
        self.assertGreater(port_detection.puntuar_candidato(POS58_BT), 0)

    def test_yichip_puntua_positivo(self):
        self.assertGreater(port_detection.puntuar_candidato(YICHIP_EXPLICITO), 0)

    def test_pos58_puntua_mas_que_bluetooth_generico(self):
        bluetooth_generico = _puerto("COM8", description="Bluetooth-incoming-port")
        self.assertGreater(
            port_detection.puntuar_candidato(POS58_BT),
            port_detection.puntuar_candidato(bluetooth_generico),
        )

    def test_arduino_puntua_cero_o_negativo(self):
        self.assertLessEqual(port_detection.puntuar_candidato(ARDUINO), 0)

    def test_generico_sin_indicadores_puntua_cero_o_negativo(self):
        self.assertLessEqual(port_detection.puntuar_candidato(GENERICO_INCIERTO), 0)

    def test_dispositivo_ajeno_con_palabra_positiva_incidental_queda_excluido(self):
        # "Bluetooth" aparece, pero tambien "Arduino": debe primar la
        # exclusion, nunca probarse automaticamente.
        mixto = _puerto("COM11", description="Arduino Bluetooth Shield", manufacturer="wch.cn")
        self.assertLessEqual(port_detection.puntuar_candidato(mixto), 0)

    def test_fingerprint_conocido_puntua_por_encima_de_cualquier_otro(self):
        huella = port_detection.construir_fingerprint(POS58_BT)
        # El mismo puerto, ahora en un COM distinto (simula cambio de COM),
        # sigue puntuando maximo porque la huella coincide.
        mismo_dispositivo_otro_com = _puerto(
            "COM9",
            description=POS58_BT.description,
            manufacturer=POS58_BT.manufacturer,
            hwid=POS58_BT.hwid,
            serial_number=POS58_BT.serial_number,
        )
        puntaje_con_huella = port_detection.puntuar_candidato(mismo_dispositivo_otro_com, huella)
        puntaje_sin_huella = port_detection.puntuar_candidato(YICHIP_EXPLICITO)
        self.assertGreater(puntaje_con_huella, puntaje_sin_huella)


class OrdenarCandidatosTest(unittest.TestCase):
    def test_ordena_de_mayor_a_menor_probabilidad(self):
        # YICHIP identifica el chip real de los clones POS58 (mas
        # especifico que un generico "Standard Serial over Bluetooth
        # link", que podria ser cualquier dispositivo SPP) - debe quedar
        # primero; el generico incierto sin ninguna palabra clave, fuera.
        orden = port_detection.ordenar_candidatos_por_probabilidad(
            [YICHIP_EXPLICITO, POS58_BT, GENERICO_INCIERTO]
        )
        self.assertEqual(orden[0], YICHIP_EXPLICITO)
        self.assertIn(POS58_BT, orden)
        self.assertNotIn(GENERICO_INCIERTO, orden)

    def test_excluye_candidatos_con_puntaje_no_positivo(self):
        orden = port_detection.ordenar_candidatos_por_probabilidad([POS58_BT, ARDUINO, GENERICO_INCIERTO])
        self.assertNotIn(ARDUINO, orden)
        self.assertNotIn(GENERICO_INCIERTO, orden)

    def test_ningun_candidato_razonable_da_lista_vacia(self):
        self.assertEqual(
            port_detection.ordenar_candidatos_por_probabilidad([ARDUINO, GENERICO_INCIERTO]), []
        )

    def test_fingerprint_conocido_queda_primero(self):
        huella = port_detection.construir_fingerprint(POS58_BT)
        mismo_dispositivo_otro_com = _puerto(
            "COM9",
            description=POS58_BT.description,
            manufacturer=POS58_BT.manufacturer,
            hwid=POS58_BT.hwid,
            serial_number=POS58_BT.serial_number,
        )
        orden = port_detection.ordenar_candidatos_por_probabilidad(
            [YICHIP_EXPLICITO, mismo_dispositivo_otro_com], fingerprint_conocido=huella
        )
        self.assertEqual(orden[0], mismo_dispositivo_otro_com)

    def test_nunca_abre_hardware_al_puntuar_u_ordenar(self):
        # Mismo principio que test_modulo_no_importa_capa_de_hardware: la
        # deteccion (incluida la puntuacion) es pura lectura de metadatos.
        self.assertFalse(hasattr(port_detection, "serial"))


if __name__ == "__main__":
    unittest.main()
