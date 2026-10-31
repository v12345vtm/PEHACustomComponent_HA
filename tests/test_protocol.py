# test_protocol.py - Peha PHC versie 0.1.5
"""Controles voor protocol, modulelogica en logregels (zonder Home Assistant).

Uitvoeren vanuit de map peha_phc:
    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "peha_phc"

# Laad het pakket zonder __init__.py uit te voeren (die importeert Home Assistant).
_pkg = types.ModuleType("peha_phc")
_pkg.__path__ = [str(COMPONENT)]
sys.modules["peha_phc"] = _pkg

from peha_phc import protocol as p  # noqa: E402
from peha_phc.const import MODULE_INGANG, MODULE_RELAIS, MODULE_ROLLUIK  # noqa: E402
from peha_phc.models import CoverState, PhcModule  # noqa: E402


def _bus(address: int, payload: list[int]) -> bytes:
    """Bouwt een busframe zoals een module het verstuurt (zonder toggle-bit)."""
    body = bytes([address, len(payload)]) + bytes(payload)
    crc = p.phc_crc(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def _msg(address: int, payload: list[int]) -> p.Decoded:
    (frame,) = p.BusParser().feed(_bus(address, payload))
    return p.decode_frame(frame)


def _frame(hexstr: str) -> p.BusFrame:
    (frame,) = p.BusParser().feed(bytes.fromhex(hexstr))
    return frame


class CrcTests(unittest.TestCase):
    def test_voorbeelden_uit_flow_en_notities(self):
        self.assertEqual(p.phc_crc([0xFE, 0x00, 0x06, 0x00, 0x00, 0x01, 0x01]), 0xAEC9)
        self.assertEqual(p.phc_crc([0x43, 0x82, 0x05, 0x00]), 0x0848)
        self.assertEqual(p.phc_crc([0x43, 0x81, 0x02]), 0x99D8)
        self.assertEqual(p.phc_crc([0x01, 0x01, 0xF2]), 0x5155)

    def test_voorbeelden_uit_het_bericht_zijn_geldig(self):
        for hexstr in ("42 81 26 22 A4", "42 82 00 44 6B 6E", "01 01 F2 55 51", "43 82 05 00 48 08"):
            self.assertEqual(len(p.BusParser().feed(bytes.fromhex(hexstr))), 1, hexstr)


class FrameTests(unittest.TestCase):
    def test_statusopvraag_imd0_exact(self):
        expected = bytes.fromhex("C0 FE 00 06 00 00 01 01 C9 AE C1")
        self.assertEqual(p.status_frame(0x00), expected)

    def test_escaping_van_c0_in_payload(self):
        frame = p.command_frame(0x40, bytes([0xC0]))
        self.assertNotIn(0xC0, frame[1:-1])
        self.assertEqual(p.unwrap_stm(frame)[:7], bytes([0xFE, 0x00, 0x06, 0x00, 0x40, 0x01, 0xC0]))

    def test_rolluik_omlaag_30_seconden(self):
        body = p.unwrap_stm(p.cover_frame(0x42, 0, "omlaag", 300))
        self.assertEqual(body[4:10], bytes([0x42, 0x04, 0x06, 0x07, 0x2C, 0x01]))
        self.assertEqual(p.phc_crc(body[:-2]), body[-2] | (body[-1] << 8))

    def test_virtuele_ingang_header(self):
        body = p.unwrap_stm(p.virtual_input_frame(0x01, (15 << 4) | 2))
        self.assertEqual(body[:6], bytes([0xFE, 0x00, 0x21, 0x00, 0x01, 0xF2]))
        self.assertEqual(len(body), 8)  # header, adres, payload, CRC: geen lengte-byte


class ParserTests(unittest.TestCase):
    def test_jrm_klaar_omlaag(self):
        msg = p.decode_frame(_frame("43 82 05 00 48 08"))
        self.assertEqual((msg.kind, msg.channel, msg.code), ("jrm_event", 0, 5))

    def test_jrm_stop_echo(self):
        msg = p.decode_frame(_frame("43 81 02 D8 99"))
        self.assertEqual((msg.kind, msg.channel, msg.code), ("output_cmd", 0, 2))

    def test_imd_event_knop_15_kort(self):
        msg = p.decode_frame(_frame("01 01 F2 55 51"))
        self.assertEqual((msg.kind, msg.channel, msg.action, msg.pressed),
                         ("input_event", 15, "kort_ingedrukt", True))

    def test_ruis_en_gesplitste_bytes(self):
        parser = p.BusParser()
        frames = parser.feed(bytes.fromhex("00 00 43 82"))
        frames += parser.feed(bytes.fromhex("05 00 48 08 01 01 F2"))
        frames += parser.feed(bytes.fromhex("55 51"))
        self.assertEqual([f.address for f in frames], [0x43, 0x01])

    def test_ruis_blijft_begrensd_en_geldig_frame_wordt_nog_gevonden(self):
        parser = p.BusParser()
        parser.feed(bytes([0x55]) * 300)
        self.assertLessEqual(len(parser._buf), 131)
        frames = parser.feed(bytes.fromhex("43 82 05 00 48 08"))
        self.assertEqual([f.address for f in frames], [0x43])


class ModelTests(unittest.TestCase):
    def test_relais_status_bit6_is_index6(self):
        module = PhcModule(kind=MODULE_RELAIS, phc=0, name="relais", address=0x40)
        module.apply(_msg(0x40, [0x01, 0x40]))
        self.assertEqual(module.status_text(), "00000010")

    def test_rolluik_omlaag_en_klaar(self):
        module = PhcModule(kind=MODULE_ROLLUIK, phc=2, name="rolluik", address=0x42)
        module.apply(_msg(0x42, [0x06, 0x07, 0x2C, 0x01]))
        self.assertEqual(module.covers[0].status, "closing")
        self.assertEqual(module.covers[0].duration, 30.0)
        module.apply(_msg(0x42, [0x05, 0x00]))
        self.assertEqual(module.covers[0].status, "closed")

    def test_rolluik_stop_geeft_halted(self):
        module = PhcModule(kind=MODULE_ROLLUIK, phc=2, name="rolluik", address=0x42)
        module.apply(_msg(0x42, [0x05, 0x07, 0x2C, 0x01]))
        self.assertEqual(module.covers[0].status, "opening")
        module.apply(_msg(0x42, [0x02]))
        self.assertEqual(module.covers[0].status, "halted")
        self.assertIs(module.covers[0].closed, False)

    def test_ingang_status_en_event(self):
        module = PhcModule(kind=MODULE_INGANG, phc=1, name="ingang", address=0x01)
        module.apply(_msg(0x01, [0x01, 0x00, 0x05, 0x00]))
        self.assertEqual((module.inputs[0], module.inputs[1], module.inputs[2]), (True, False, True))
        effects = module.apply(_msg(0x01, [0xF2]))
        self.assertEqual(module.inputs[15], True)
        self.assertEqual(effects, [("input", 15, "kort_ingedrukt")])


class RegressionTests(unittest.TestCase):
    def test_ingang_status_zonder_leds_toont_vraagtekens(self):
        module = PhcModule(kind=MODULE_INGANG, phc=1, name="ingang", address=0x01)
        module.apply(_msg(0x01, [0xF2]))
        self.assertEqual(module.status_text(), "?" * 15 + "1," + "?" * 16)

    def test_standaard_looptijden_per_kanaal(self):
        module = PhcModule(kind=MODULE_ROLLUIK, phc=2, name="rolluik", address=0x42)
        self.assertEqual(module.runtimes, [20.0, 25.0, 30.0, 16.0])

    def test_nieuwe_beweging_verhoogt_generatie(self):
        cover = CoverState()
        cover.start("omlaag", 20.0)
        eerste = cover.generation
        cover.start("omhoog")
        self.assertGreater(cover.generation, eerste)
        self.assertEqual(cover.duration, 0.0)


class FormatTests(unittest.TestCase):
    """De logregels moeten exact overeenkomen met de voorbeelden uit het bericht."""

    def test_imd_event(self):
        frame = _frame("01 01 F2 55 51")
        self.assertEqual(p.format_bus(frame, p.decode_frame(frame), MODULE_INGANG),
                         "imd 01 : event: 01 01 F2 55 51 -> knop 15 : (Aan > 0 seconden)")

    def test_jrm_klaar_omlaag(self):
        frame = _frame("43 82 05 00 48 08")
        self.assertEqual(p.format_bus(frame, p.decode_frame(frame), MODULE_ROLLUIK),
                         "jrm 43 : event: 43 82 05 00 48 08 -> kanaal 0 -> KLAAR met OMLAAG (gestopt)")

    def test_relais_omschakelen_cmd(self):
        frame = _frame("42 81 26 22 A4")
        self.assertEqual(p.format_bus(frame, p.decode_frame(frame), MODULE_RELAIS),
                         "amd 42 : cmd  : 42 81 26 22 A4 -> 26 *Omschakelen (kanaal 1)*")

    def test_relais_ack_met_kanalen(self):
        frame = _frame("42 82 00 44 6B 6E")
        self.assertEqual(p.format_bus(frame, p.decode_frame(frame), MODULE_RELAIS),
                         "amd 42 : ack  : 42 82 00 44 6B 6E -> 00100010 (aan: 2,6)")

    def test_rolluik_stop_echo(self):
        frame = _frame("43 81 02 D8 99")
        self.assertEqual(p.format_bus(frame, p.decode_frame(frame), MODULE_ROLLUIK),
                         "jrm 43 : cmd  : 43 81 02 D8 99 -> 02 *Stop (kanaal 0)*")

    def test_verstuurd_virtuele_ingang_is_een_enkel_commando(self):
        expected = "imd 01 : virtueel: 01 01 F2 55 51 -> knop 15 : (Aan > 0 seconden)"
        self.assertEqual(p.describe_sent(p.virtual_input_frame(0x01, (15 << 4) | 2),
                                         lambda adres: MODULE_INGANG), expected)

    def test_verstuurd_relais_aan(self):
        raw = _bus(0x40, [0x02])
        expected = f"amd 40 : cmd  : {raw.hex(' ').upper()} -> 02 *Aan (kanaal 0)*"
        self.assertEqual(p.describe_sent(p.relay_frame(0x40, 0, "aan"),
                                         lambda adres: MODULE_RELAIS), expected)


class VirtueleFunctieTests(unittest.TestCase):
    def test_functies_komen_overeen_met_const(self):
        from peha_phc.const import VIRTUAL_FUNCTIES
        self.assertEqual(set(VIRTUAL_FUNCTIES), set(p.VIRTUAL_CODES))

    def test_codes_van_de_vijf_functies(self):
        self.assertEqual(
            {k: p.VIRTUAL_CODES[k] for k in ("kort", "uit_lt_1", "lang", "uit_gt_1", "extra_lang")},
            {"kort": 0x02, "uit_lt_1": 0x03, "lang": 0x04, "uit_gt_1": 0x05, "extra_lang": 0x06},
        )

    def test_uit_lt_1_frame_heeft_payload_f3(self):
        body = p.unwrap_stm(p.virtual_input_frame(0x01, (15 << 4) | p.VIRTUAL_CODES["uit_lt_1"]))
        self.assertEqual(body[4:6], bytes([0x01, 0xF3]))

    def test_verstuurde_regel_uit_lt_1(self):
        crc = p.phc_crc([0x01, 0x01, 0xF3])
        expected = f"imd 01 : virtueel: 01 01 F3 {crc & 0xFF:02X} {crc >> 8:02X} -> knop 15 : (Uit < 1 seconden)"
        self.assertEqual(p.describe_sent(p.virtual_input_frame(0x01, (15 << 4) | 3), lambda adres: None), expected)

    def test_ingang_status_logregel(self):
        raw = _bus(0x01, [0x01, 0x00, 0x05, 0x00])
        frame = p.BusParser().feed(raw)[0]
        regel = p.format_bus(frame, p.decode_frame(frame), MODULE_INGANG)
        self.assertEqual(
            regel,
            f"imd 01 : status: {raw.hex(' ').upper()} -> ingangen 1010000000000000 | LEDs 0000000000000000",
        )


class IngangEventTests(unittest.TestCase):
    def test_eventvolgorde_van_een_knop(self):
        volgorde = [
            (0xF2, True, "kort_ingedrukt"),
            (0xF3, False, "kort_losgelaten"),
            (0xF4, True, "lang_ingedrukt"),
            (0xF6, True, "extra_lang_ingedrukt"),
            (0xF5, False, "lang_losgelaten"),
        ]
        for byte, ingedrukt, actie in volgorde:
            msg = _msg(0x01, [byte])
            self.assertEqual((msg.kind, msg.channel, msg.pressed, msg.action),
                             ("input_event", 15, ingedrukt, actie))


class VirtueleNaamTests(unittest.TestCase):
    def test_sleutel_naam_en_nummer_geven_dezelfde_functie(self):
        self.assertEqual(p.virtual_functie("aan > 0 seconden"), "kort")
        self.assertEqual(p.virtual_functie("Uit < 1 seconden"), "uit_lt_1")
        self.assertEqual(p.virtual_functie("3"), "uit_lt_1")
        self.assertEqual(p.virtual_functie(2), "kort")
        self.assertEqual(p.virtual_functie("lang"), "lang")
        self.assertIsNone(p.virtual_functie("onbekend"))

    def test_namen_komen_overeen_met_de_keuzelijst(self):
        from peha_phc.const import VIRTUAL_FUNCTIES
        for sleutel, tekst in VIRTUAL_FUNCTIES.items():
            self.assertEqual(tekst.lower(), p.VIRTUAL_NAMEN[sleutel])


class StatusTimingTests(unittest.TestCase):
    def test_statusopvraag_pas_na_het_loslaten(self):
        from peha_phc.const import HOLD_TIMEOUT, STATUS_NA_LOSLATEN
        self.assertLess(0, STATUS_NA_LOSLATEN)
        self.assertLess(STATUS_NA_LOSLATEN, HOLD_TIMEOUT)


class IngangsEventVoorbeeldTests(unittest.TestCase):
    """De voorbeelden uit het bericht moeten exact zo gelezen en benoemd worden."""

    VOORBEELDEN = [
        ("01 01 C2 D6 60", "imd 01 : event: 01 01 C2 D6 60 -> knop 12 : (Aan > 0 seconden)", "01.12.2"),
        ("01 81 C3 93 FD", "imd 01 : event: 01 81 C3 93 FD -> knop 12 : (Uit < 1 seconden)", "01.12.3"),
        ("01 81 C4 2C 89", "imd 01 : event: 01 81 C4 2C 89 -> knop 12 : (Aan > 1 seconden)", "01.12.4"),
        ("01 01 C6 F2 26", "imd 01 : event: 01 01 C6 F2 26 -> knop 12 : (Aan > 2 seconden)", "01.12.6"),
        ("01 81 C5 A5 98", "imd 01 : event: 01 81 C5 A5 98 -> knop 12 : (Uit > 1 seconden)", "01.12.5"),
    ]

    def test_logregels_zijn_exact(self):
        for hexstr, regel, _ in self.VOORBEELDEN:
            frame = _frame(hexstr)
            self.assertEqual(p.format_bus(frame, p.decode_frame(frame), MODULE_INGANG), regel)

    def test_vereenvoudigd_event(self):
        for hexstr, _, tekst in self.VOORBEELDEN:
            frame = _frame(hexstr)
            msg = p.decode_frame(frame)
            self.assertEqual(p.imd_event_tekst(frame.address, msg.channel, msg.code), tekst)
        self.assertEqual(p.imd_event_tekst(0, 3, 5), "00.03.5")

    def test_namen(self):
        self.assertEqual(p.IMD_SIMPLE_NAMEN, {2: "inflank", 3: "kort_uitflank", 4: "lang",
                                             5: "lang_uitflank", 6: "lang_zeerlang", 7: "losgelaten"})

    def test_laatste_event_van_een_module(self):
        module = PhcModule(kind=MODULE_INGANG, phc=1, name="ingang", address=0x01)
        self.assertIsNone(module.laatste_tekst())
        module.apply(_msg(0x01, [0xC2]))
        module.apply(_msg(0x01, [0xC5]))
        self.assertEqual(module.laatste_tekst(), "01.12.5")
        self.assertEqual(module.knop_code[12], 5)


class EthernetTests(unittest.TestCase):
    def test_url_is_exact_als_het_voorbeeld(self):
        self.assertEqual(p.ethernet_url("192.168.1.2", 0, 3, 0, 2),
                         "http://192.168.1.2:80/postEvent.html?action=input&STM=0&MOD=3&CHA=0&EVT=2")

    def test_ipv4_controle(self):
        self.assertTrue(p.geldig_ipv4("192.168.1.2"))
        self.assertTrue(p.geldig_ipv4(" 10.0.0.1 "))
        self.assertFalse(p.geldig_ipv4("256.1.1.1"))
        self.assertFalse(p.geldig_ipv4("abc"))
        self.assertFalse(p.geldig_ipv4(""))

    def test_sleutels_en_apparaat(self):
        from peha_phc.const import BUS_TYPES, MODULE_ETHERNET, MODULE_LABELS, ethernet_device_id, module_key
        self.assertEqual(ethernet_device_id("192.168.1.2"), "ETH_192_168_1_2")
        self.assertEqual(module_key({"type": "ethernet", "ip": "192.168.1.2", "stm": 0, "naam": "E"}),
                         "ethernet_192.168.1.2")
        self.assertEqual(module_key({"type": "ethernetknop", "ethernet": "192.168.1.2", "phc": 3,
                                     "kanaal": 0, "functie": "kort", "naam": "K"}),
                         "ethernetknop_192.168.1.2_3_0_kort")
        self.assertEqual(module_key({"type": "relais", "phc": 0, "naam": "R"}), "relais_0")
        self.assertNotIn(MODULE_ETHERNET, BUS_TYPES)
        self.assertIn(MODULE_ETHERNET, MODULE_LABELS)


if __name__ == "__main__":
    unittest.main()
