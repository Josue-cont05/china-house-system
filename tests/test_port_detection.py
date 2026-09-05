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


if __name__ == "__main__":
    unittest.main()
