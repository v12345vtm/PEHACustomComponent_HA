# Peha PHC-integratie, versie 1.1.0
"""Het PHC-protocol: CRC, commando's voor de STM (met C0/C1), frames van de bus en decodering.

Zuivere Python zonder Home Assistant. De bytes zijn gelijk aan de functies in de
Node-RED-flow (bouw AMD-frame, bouw JRM-frame, bouw IMD-frame).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .const import DEFAULT_PRIORITEIT, RELAIS_KANALEN, ROLLUIK_KANALEN

C0 = 0xC0   # begin van een frame naar de STM
C1 = 0xC1   # einde van een frame naar de STM
ESC = 0x7D  # escape: C0 wordt 7D E0, C1 wordt 7D E1, 7D wordt 7D 5D
STM_KOP = bytes([0xFE, 0x00, 0x06, 0x00])
STATUS_VERZOEK = bytes([0x01])

# Functiecodes van een relaismodule (uitgang), uit de flow
RELAIS_CODES: dict[str, int] = {
    "status": 0x01,
    "aan": 0x02,
    "uit": 0x03,
    "vergrendel_aan": 0x04,
    "vergrendel_uit": 0x05,
    "omschakelen": 0x06,
    "ontgrendel": 0x07,
    "aan_vertraagd": 0x08,
    "uit_vertraagd": 0x09,
    "aan_met_timer": 0x0A,
    "uit_met_timer": 0x0B,
    "omschakelen_vertraagd": 0x0C,
    "omschakelen_met_timer": 0x0D,
}
RELAIS_MET_TIJD = frozenset({
    "aan_vertraagd", "uit_vertraagd", "aan_met_timer",
    "uit_met_timer", "omschakelen_vertraagd", "omschakelen_met_timer",
})
RELAIS_NAMEN = {code: naam for naam, code in RELAIS_CODES.items()}

# Functiecodes van een rolluikmodule (JRM), uit de flow
ROLLUIK_CODES: dict[str, int] = {
    "status": 0x01,
    "stop": 0x02,
    "omhoog_stop": 0x03,
    "omlaag_stop": 0x04,
    "omhoog": 0x05,
    "omlaag": 0x06,
    "flip_omhoog": 0x07,
    "flip_omlaag": 0x08,
    "prio_lock": 0x09,
    "prio_unlock": 0x0A,
    "leren_aan": 0x0B,
    "leren_uit": 0x0C,
    "prio_setten": 0x0D,
    "prio_loschen": 0x0E,
    "sensor_heffen": 0x0F,
    "sensor_heffen_flip": 0x10,
    "sensor_senken": 0x11,
    "sensor_senken_flip": 0x12,
}
# Bewegingen die de integratie mag sturen. Leren en prioriteit blijven buiten de service.
ROLLUIK_BEWEGING = ("omhoog", "omlaag", "stop", "omhoog_stop", "omlaag_stop", "flip_omhoog", "flip_omlaag")
ROLLUIK_MET_TIJD = frozenset({"omhoog_stop", "omlaag_stop", "omhoog", "omlaag", "flip_omhoog", "flip_omlaag"})
ROLLUIK_MET_PRIO = frozenset({"prio_lock", "prio_unlock", "prio_setten", "prio_loschen"})
ROLLUIK_NAMEN = {code: naam for naam, code in ROLLUIK_CODES.items()}

# Terugkoppeling van een rolluikmodule, uit de commentaar in je flow.
# Let op: de handleiding (PDF) zat niet in de upload. Controleer dit tegen de handleiding.
ROLLUIK_GEBEURTENIS = {
    0x03: "start_omlaag",
    0x04: "klaar_omhoog",
    0x05: "klaar_omlaag",
    0x06: "timer_gestart",
    0x07: "timer_geannuleerd",
    0x08: "timer_afgelopen",
}
ROLLUIK_GEBEURTENIS_CODE = {naam: code for code, naam in ROLLUIK_GEBEURTENIS.items()}
ROLLUIK_TEKST = {
    "start_omlaag": "start met DALEN (omlaag)",
    "klaar_omhoog": "KLAAR met OMHOOG (gestopt)",
    "klaar_omlaag": "KLAAR met OMLAAG (gestopt)",
    "timer_gestart": "timer gestart",
    "timer_geannuleerd": "timer geannuleerd",
    "timer_afgelopen": "timer afgelopen (gestopt)",
}


# Tekst voor de statussensor van een rolluik: wat de JRM als laatste heeft teruggemeld.
ROLLUIK_STATUS_TEKST = {
    "start_omlaag": "omlaag gestart",
    "klaar_omhoog": "omhoog gegaan",
    "klaar_omlaag": "omlaag gegaan",
    "timer_gestart": "timer gestart",
    "timer_geannuleerd": "timer geannuleerd",
    "timer_afgelopen": "timer afgelopen (gestopt)",
}


def crc16(data: bytes) -> int:
    """PHC-CRC: startwaarde 0xFFFF, polynoom 0x8408 (gespiegeld), eindwaarde xor 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def _rond(getal: float) -> int:
    """Afronden zoals Math.round in de flow: 0,5 gaat omhoog."""
    return math.floor(getal + 0.5)


def _escape(data: bytes) -> bytes:
    uit = bytearray()
    for byte in data:
        if byte == C0:
            uit += bytes([ESC, 0xE0])
        elif byte == C1:
            uit += bytes([ESC, 0xE1])
        elif byte == ESC:
            uit += bytes([ESC, 0x5D])
        else:
            uit.append(byte)
    return bytes(uit)


def ontescape(frame: bytes) -> bytes:
    """Haalt de C0/C1-randen weg en maakt de escapes ongedaan. Het omgekeerde van stm_frame."""
    if frame[:1] == bytes([C0]) and frame[-1:] == bytes([C1]):
        frame = frame[1:-1]
    uit = bytearray()
    i = 0
    while i < len(frame):
        byte = frame[i]
        if byte == ESC and i + 1 < len(frame):
            uit.append(frame[i + 1] ^ 0x20)
            i += 2
        else:
            uit.append(byte)
            i += 1
    return bytes(uit)


def stm_frame(adres: int, payload: bytes) -> bytes:
    """Commando voor de STM: C0, ge-escapete tekst FE 00 06 00 adres lengte payload crc, C1.

    De CRC rekent mee over de STM-kop, net als in de flow. Dat is niet dezelfde CRC als op de bus.
    """
    if not 0 <= adres <= 0xFF:
        raise ValueError(f"adres {adres} past niet in één byte")
    if not 1 <= len(payload) <= 0x7F:
        raise ValueError("payload moet 1 t/m 127 bytes zijn")
    body = STM_KOP + bytes([adres, len(payload)]) + payload
    crc = crc16(body)
    return bytes([C0]) + _escape(body + bytes([crc & 0xFF, crc >> 8])) + bytes([C1])


def bus_frame(adres: int, payload: bytes) -> bytes:
    """Frame zoals het op de bus staat: adres, lengte, payload, crc (laag, hoog). Geen C0/C1."""
    body = bytes([adres & 0xFF, len(payload) & 0x7F]) + payload
    crc = crc16(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def relais_payload(kanaal: int, actie: str, tijd: float | None = None) -> bytes:
    """Payload voor een relaismodule. Het kanaal zit in de bovenste drie bits."""
    if actie == "status":
        return STATUS_VERZOEK
    if actie not in RELAIS_CODES:
        raise ValueError(f"onbekende actie voor een relais: {actie}")
    if not 0 <= kanaal < RELAIS_KANALEN:
        raise ValueError(f"kanaal {kanaal} valt buiten 0 t/m {RELAIS_KANALEN - 1}")
    payload = bytes([(kanaal << 5) | RELAIS_CODES[actie]])
    if actie in RELAIS_MET_TIJD:
        if tijd is None:
            raise ValueError(f"actie {actie} heeft een tijd in seconden nodig")
        seconden = _rond(tijd)
        if not 0 <= seconden <= 0xFFFF:
            raise ValueError("tijd valt buiten het bereik")
        payload += bytes([seconden & 0xFF, seconden >> 8])
    return payload


def rolluik_payload(
    kanaal: int,
    actie: str,
    tijd: float = 0.0,
    prioriteit: int = DEFAULT_PRIORITEIT,
) -> bytes:
    """Payload voor een rolluikmodule. Tijd gaat in tienden van seconden, zoals in de flow.

    Let op: de status-opvraag stuurt altijd alleen 01, zonder kanaalbits (voor kanaal 0 is dat gelijk aan de flow).
    """
    if actie == "status":
        return STATUS_VERZOEK
    if actie not in ROLLUIK_CODES:
        raise ValueError(f"onbekende actie voor een rolluik: {actie}")
    if not 0 <= kanaal < ROLLUIK_KANALEN:
        raise ValueError(f"kanaal {kanaal} valt buiten 0 t/m {ROLLUIK_KANALEN - 1}")
    if not 0 <= prioriteit <= 0xFF:
        raise ValueError("prioriteit valt buiten 0 t/m 255")
    payload = bytes([(kanaal << 5) | ROLLUIK_CODES[actie]])
    if actie in ROLLUIK_MET_TIJD:
        tienden = _rond(tijd * 10)
        if not 0 <= tienden <= 0xFFFF:
            raise ValueError("tijd valt buiten het bereik")
        payload += bytes([prioriteit, tienden & 0xFF, tienden >> 8])
    elif actie in ROLLUIK_MET_PRIO:
        payload += bytes([prioriteit])
    return payload


@dataclass(frozen=True)
class BusFrame:
    adres: int
    payload: bytes
    raw: bytes


class BusParser:
    """Zoekt frames in een stroom ruwe bytes.

    Een frame is: adres, lengte (bit 7 is de toggle, daarom & 0x7F), payload, crc laag, crc hoog.
    Past de CRC niet, dan schuift de parser één byte op. Zo herstelt hij zich na ruis.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def reset(self) -> None:
        self._buf.clear()

    def feed(self, data: bytes) -> list[BusFrame]:
        self._buf.extend(data)
        buf = self._buf
        frames: list[BusFrame] = []
        while len(buf) >= 4:
            totaal = (buf[1] & 0x7F) + 4
            if len(buf) >= totaal:
                if _geldig(buf, 0, totaal):
                    frames.append(BusFrame(buf[0], bytes(buf[2:totaal - 2]), bytes(buf[:totaal])))
                    del buf[:totaal]
                else:
                    del buf[0]
                continue
            # Het kandidaat-frame is nog niet compleet. Staat er verderop al een geldig frame?
            # Dan is het begin ruis, en die gooien we weg.
            k = _zoek_geldig_frame(buf)
            if k is None:
                break  # wacht op meer bytes; een frame is hooguit 131 bytes lang
            del buf[:k]
        return frames


def _geldig(buf, start: int, totaal: int) -> bool:
    """Klopt de CRC van het frame dat op start begint en totaal bytes lang is?"""
    eind = start + totaal
    crc_rx = buf[eind - 2] | (buf[eind - 1] << 8)
    return crc16(bytes(buf[start:eind - 2])) == crc_rx


def _zoek_geldig_frame(buf) -> int | None:
    """Geeft de eerste positie (vanaf 1) waar een compleet, geldig frame begint, of None."""
    for k in range(1, len(buf) - 3):
        totaal = (buf[k + 1] & 0x7F) + 4
        if k + totaal <= len(buf) and _geldig(buf, k, totaal):
            return k
    return None


def relais_status(payload: bytes) -> int | None:
    """Antwoord van een relais: 00 xx (ack) of 01 xx (status). xx heeft een bit per kanaal, bit 0 is kanaal 0."""
    if len(payload) == 2 and payload[0] in (0x00, 0x01):
        return payload[1]
    return None


def ingang_status(payload: bytes) -> tuple[int, int, int] | None:
    """Antwoord van een ingangsmodule: 01 leds0-7 ingang0-7 ingang8-15 [leds8-15].

    Geeft (ingangen, leds, aantal_leds). Bit 0 is ingang of LED 0. Een bericht van 4 bytes komt van
    een module met 8 LED's, een bericht van 5 bytes van een module met 16 LED's (zie je flow).
    """
    if len(payload) in (4, 5) and payload[0] == 0x01:
        ingangen = payload[2] | (payload[3] << 8)
        leds = payload[1] | ((payload[4] << 8) if len(payload) == 5 else 0)
        return ingangen, leds, 16 if len(payload) == 5 else 8
    return None


def rolluik_gebeurtenis(payload: bytes) -> tuple[int, str] | None:
    """Terugkoppeling van een rolluik: (kanaal, gebeurtenis). Alleen frames van 2 bytes met code 3 t/m 8."""
    if len(payload) == 2:
        code = payload[0] & 0x1F
        if code in ROLLUIK_GEBEURTENIS:
            return (payload[0] >> 5) & 0x03, ROLLUIK_GEBEURTENIS[code]
    return None
