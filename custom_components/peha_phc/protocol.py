# protocol.py - Peha PHC versie 0.1.2
"""PHC-protocol: CRC, STM-framing, busparser, decoders en logregels.

Puur Python zonder Home Assistant, zodat het los te testen is.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# --- STM-stuureenheid (USB-kabel): frames met C0 ... C1 en escaping ---------
FRAME_START = 0xC0
FRAME_END = 0xC1
FRAME_ESC = 0x7D

HEADER_CMD = bytes((0xFE, 0x00, 0x06, 0x00))      # commando met lengte-byte
HEADER_VIRTUAL = bytes((0xFE, 0x00, 0x21, 0x00))  # virtuele ingang (geen lengte-byte)

# --- Functiecodes van de output-modules (AMD = relais, JRM = rolluik) --------
OUT_STATUS = 0x01
OUT_AAN = 0x02          # relais aan (1 byte) / JRM stop (1 byte)
OUT_UIT = 0x03          # relais uit
OUT_OMSCHAKELEN = 0x06  # relais omschakelen
JRM_STOP = 0x02
JRM_OMHOOG_STOP = 0x03
JRM_OMLAAG_STOP = 0x04
JRM_OMHOOG = 0x05
JRM_OMLAAG = 0x06

JRM_EVENTEN = {
    3: "start met DALEN (omlaag)",
    4: "KLAAR met OMHOOG (gestopt)",
    5: "KLAAR met OMLAAG (gestopt)",
    6: "timer gestart",
    7: "timer geannuleerd",
    8: "timer afgelopen (gestopt)",
}

# Namen van multi-byte commando's, voor de logregels
JRM_NAMEN = {
    0x03: "Omschakelen heffen stop",
    0x04: "Omschakelen dalen stop",
    0x05: "Omhoog (heffen)",
    0x06: "Omlaag (dalen)",
    0x07: "Flip omhoog",
    0x08: "Flip omlaag",
}
AMD_TIJD_NAMEN = {
    0x08: "Aan vertraagd",
    0x09: "Uit vertraagd",
    0x0A: "Aan met timer",
    0x0B: "Uit met timer",
    0x0C: "Omschakelen vertraagd",
    0x0D: "Omschakelen met timer",
}
PRIO_NAMEN = {0x09: "Prio lock", 0x0A: "Prio unlock", 0x0D: "Prio setten", 0x0E: "Prio loschen"}

# IMD-ingangsevents: code -> (actie, ingedrukt?, naam zoals in de logregel)
IMD_EVENTEN = {
    2: ("kort_ingedrukt", True, "Aan > 0 seconden"),
    3: ("kort_losgelaten", False, "Uit < 1 seconden"),
    4: ("lang_ingedrukt", True, "Aan > 1 seconden"),
    5: ("lang_losgelaten", False, "Uit > 1 seconden"),
    6: ("extra_lang_ingedrukt", True, "Aan > 2 seconden"),
    7: ("losgelaten", False, "Uit (losgelaten)"),
}

# Functiecode per virtuele functie, zoals de Node-RED IMD GENERATOR. Geen loslaatcommando.
VIRTUAL_CODES = {
    "kort": 0x02,        # aan > 0 seconden
    "uit_lt_1": 0x03,    # uit < 1 seconden
    "lang": 0x04,        # aan > 1 seconden
    "uit_gt_1": 0x05,    # uit > 1 seconden
    "extra_lang": 0x06,  # aan > 2 seconden
}

# Namen van de virtuele functies, zoals de Node-RED IMD GENERATOR ze kent (kleine letters)
VIRTUAL_NAMEN = {
    "kort": "aan > 0 seconden",
    "uit_lt_1": "uit < 1 seconden",
    "lang": "aan > 1 seconden",
    "uit_gt_1": "uit > 1 seconden",
    "extra_lang": "aan > 2 seconden",
}


def virtual_functie(waarde) -> str | None:
    """Zet een functie om naar de sleutel. Accepteert de sleutel, de naam of het nummer."""
    tekst = str(waarde).strip().lower()
    for sleutel, code in VIRTUAL_CODES.items():
        if tekst in (sleutel, VIRTUAL_NAMEN[sleutel], str(code)):
            return sleutel
    return None

MAX_FRAME = 132  # 1 adres + 1 lengte + max. 127 payload + 2 CRC + marge


def _crc_step(crc: int, byte: int) -> int:
    crc ^= byte
    for _ in range(8):
        crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def phc_crc(data) -> int:
    """PHC-CRC-16: init 0xFFFF, gereflecteerd polynoom 0x8408, eindxor 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc = _crc_step(crc, byte)
    return crc ^ 0xFFFF


def bitstr(value: int, count: int) -> str:
    """Bits als tekst. Positie i staat voor bit i, dus kanaal i staat op positie i."""
    return "".join("1" if (value >> i) & 1 else "0" for i in range(count))


# --- Zenden naar de STM ----------------------------------------------------------

def _escape(data: bytes) -> bytes:
    out = bytearray()
    for byte in data:
        if byte == FRAME_START:
            out += bytes((FRAME_ESC, 0xE0))
        elif byte == FRAME_END:
            out += bytes((FRAME_ESC, 0xE1))
        elif byte == FRAME_ESC:
            out += bytes((FRAME_ESC, 0x5D))
        else:
            out.append(byte)
    return bytes(out)


def _stm_wrap(body: bytes) -> bytes:
    crc = phc_crc(body)
    return bytes((FRAME_START,)) + _escape(body + bytes((crc & 0xFF, crc >> 8))) + bytes((FRAME_END,))


def unwrap_stm(frame: bytes) -> bytes:
    """Haalt C0/C1 en de escaping weg, zodat de inhoud van een STM-frame zichtbaar is."""
    out = bytearray()
    escaped = False
    for byte in frame[1:-1]:
        if escaped:
            out.append({0xE0: FRAME_START, 0xE1: FRAME_END, 0x5D: FRAME_ESC}[byte])
            escaped = False
        elif byte == FRAME_ESC:
            escaped = True
        else:
            out.append(byte)
    return bytes(out)


def command_frame(address: int, payload: bytes) -> bytes:
    """Commando via de STM: header FE 00 06 00, adres, lengte, payload, CRC."""
    return _stm_wrap(HEADER_CMD + bytes((address & 0xFF, len(payload) & 0x7F)) + payload)


def virtual_input_frame(address: int, payload_byte: int) -> bytes:
    """Virtuele ingang: header FE 00 21 00, adres, (kanaal << 4) | functie."""
    return _stm_wrap(HEADER_VIRTUAL + bytes((address & 0xFF, payload_byte & 0xFF)))


def status_frame(address: int) -> bytes:
    """Statusopvraag, werkt voor alle modules."""
    return command_frame(address, bytes((OUT_STATUS,)))


def relay_frame(address: int, channel: int, action: str) -> bytes:
    """Relais: 'aan', 'uit' of 'omschakelen'."""
    code = {"aan": OUT_AAN, "uit": OUT_UIT, "omschakelen": OUT_OMSCHAKELEN}[action]
    return command_frame(address, bytes(((channel << 5) | code,)))


def cover_frame(address: int, channel: int, action: str, tenths: int = 0, prio: int = 7) -> bytes:
    """Rolluik: 'omhoog' of 'omlaag' (looptijd in 1/10 s) of 'stop'."""
    if action == "stop":
        return command_frame(address, bytes(((channel << 5) | JRM_STOP,)))
    code = JRM_OMHOOG if action == "omhoog" else JRM_OMLAAG
    tijd = max(0, min(0xFFFF, int(tenths)))
    return command_frame(address, bytes(((channel << 5) | code, prio, tijd & 0xFF, tijd >> 8)))


# --- Ontvangen van de bus (ruwe bytes, geen framing) ------------------------------

@dataclass(frozen=True)
class BusFrame:
    address: int
    payload: bytes
    raw: bytes


def _u16(buf, index: int) -> int:
    return buf[index] | (buf[index + 1] << 8)


def _frame_len_at(buf: bytearray, start: int) -> int | None:
    """Lengte van een geldig frame dat op 'start' begint, anders None."""
    if len(buf) - start < 5:
        return None
    total = (buf[start + 1] & 0x7F) + 4  # adres + lengte + payload + CRC
    if len(buf) - start < total:
        return None
    if phc_crc(buf[start:start + total - 2]) == _u16(buf, start + total - 2):
        return total
    return None


class BusParser:
    """Zet de ruwe bytes van de busdongle om in frames. Ruis wordt overgeslagen."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def reset(self) -> None:
        self._buf.clear()

    def feed(self, data: bytes) -> list[BusFrame]:
        buf = self._buf
        buf.extend(data)
        frames: list[BusFrame] = []
        while True:
            found = None
            for start in range(max(0, len(buf) - 4)):
                total = _frame_len_at(buf, start)
                if total is not None:
                    found = (start, total)
                    break
            if found is None:
                if len(buf) < MAX_FRAME:
                    break  # wacht op meer data
                # Geen geldig frame: alles behalve de laatste bytes kan nooit meer een frame worden.
                del buf[: len(buf) - MAX_FRAME + 1]
                break
            start, total = found
            raw = bytes(buf[start:start + total])
            del buf[:start + total]
            frames.append(BusFrame(raw[0], raw[2:-2], raw))
        return frames


# --- Decoders ----------------------------------------------------------------------

@dataclass(frozen=True)
class Decoded:
    kind: str
    address: int
    text: str = ""
    channel: int | None = None
    code: int | None = None
    value: int | None = None   # statusbyte (output) of ingangen-bitmask (input)
    leds: int | None = None    # LED-bitmask (input)
    pressed: bool | None = None
    action: str | None = None
    tenths: int | None = None  # tijd in 1/10 s
    prio: int | None = None
    soort: str | None = None   # "ack" of "status" bij uitgangsmodules


def decode_frame(frame: BusFrame) -> Decoded:
    address, payload = frame.address, frame.payload
    if address <= 0x1F:
        return _decode_input(address, payload)
    if 0x40 <= address <= 0x5F:
        return _decode_output(address, payload)
    return Decoded("unknown", address, payload.hex(" ").upper())


def _decode_input(address: int, payload: bytes) -> Decoded:
    if len(payload) == 1:
        byte = payload[0]
        if byte == 0x00:
            return Decoded("ack", address, "bevestiging")
        if byte == 0x01:
            return Decoded("status_request", address, "Status opvragen", code=OUT_STATUS)
        channel, code = byte >> 4, byte & 0x0F
        if code in IMD_EVENTEN:
            action, pressed, naam = IMD_EVENTEN[code]
            return Decoded("input_event", address, naam, channel=channel, code=code,
                           action=action, pressed=pressed)
    elif len(payload) in (4, 5) and payload[0] == 0x01:
        inputs = payload[2] | (payload[3] << 8)
        leds = payload[1] | ((payload[4] if len(payload) == 5 else 0) << 8)
        tekst = f"ingangen {bitstr(inputs, 16)} | LEDs {bitstr(leds, 16)}"
        return Decoded("input_status", address, tekst, value=inputs, leds=leds)
    return Decoded("unknown", address, payload.hex(" ").upper())


def _decode_output(address: int, payload: bytes) -> Decoded:
    if not payload:
        return Decoded("unknown", address, "leeg bericht")
    first = payload[0]
    code = first & 0x1F
    channel = (first >> 5) & 0x07
    lengte = len(payload)

    if lengte == 1:
        if first == 0x00:
            return Decoded("ack", address, "bevestiging")
        if code == OUT_STATUS:
            return Decoded("status_request", address, "Status opvragen", channel=channel, code=code)
        return Decoded("output_cmd", address, "", channel=channel, code=code)

    if lengte == 2:
        if 3 <= code <= 8:
            jrm_kanaal = (first >> 5) & 0x03
            return Decoded("jrm_event", address, JRM_EVENTEN[code], channel=jrm_kanaal, code=code)
        if first in (0x00, 0x01):
            soort = "ack" if first == 0x00 else "status"
            return Decoded("output_status", address, soort, value=payload[1], soort=soort)
        return Decoded("output_cmd", address, "", channel=channel, code=code, prio=payload[1])

    if lengte == 3:
        tenths = payload[1] | (payload[2] << 8)
        return Decoded("output_cmd", address, "", channel=channel, code=code, tenths=tenths)

    if lengte == 4:
        tenths = payload[2] | (payload[3] << 8)
        return Decoded("output_cmd", address, "", channel=channel, code=code,
                       prio=payload[1], tenths=tenths)

    return Decoded("unknown", address, payload.hex(" ").upper())


# --- Logregels (zelfde stijl als de Node-RED-parser) -------------------------------

def _kanalen(value: int) -> str:
    kanalen = [str(kanaal) for kanaal in range(8) if value & (1 << kanaal)]
    return ",".join(kanalen) if kanalen else "-"


def _uitgang_prefix(modkind: str | None, payload: bytes) -> str:
    if modkind == "rolluik":
        return "jrm"
    if modkind == "relais":
        return "amd"
    return "jrm" if len(payload) >= 4 else "amd"


def _uitgang_naam(code: int, kanaal: int | None, modkind: str | None) -> str:
    """Naam van een commando van 1 byte voor een uitgangsmodule."""
    if code == OUT_STATUS:
        return "Status opvragen"
    if code == OUT_AAN:
        if modkind == "rolluik":
            return f"Stop (kanaal {kanaal})"
        if modkind == "relais":
            return f"Aan (kanaal {kanaal})"
        return f"Aan / stop (kanaal {kanaal})"
    if code == OUT_UIT:
        return f"Uit (kanaal {kanaal})"
    if code == OUT_OMSCHAKELEN:
        return f"Omschakelen (kanaal {kanaal})"
    return f"commando 0x{code:02X} (kanaal {kanaal})"


def _commando_tekst(payload: bytes, msg: Decoded, modkind: str | None) -> str:
    code, kanaal = msg.code or 0, msg.channel
    if len(payload) == 1:
        return _uitgang_naam(code, kanaal, modkind)
    if len(payload) == 2:
        naam = PRIO_NAMEN.get(code, f"commando 0x{code:02X}")
        return f"{naam} (kanaal {kanaal}), prio {msg.prio}"
    if len(payload) == 3:
        naam = AMD_TIJD_NAMEN.get(code, f"commando 0x{code:02X}")
        return f"{naam} (kanaal {kanaal}), tijd {msg.tenths / 10:.1f} s"
    naam = JRM_NAMEN.get(code, f"commando 0x{code:02X}")
    return f"{naam} (kanaal {kanaal}), prio {msg.prio}, tijd {msg.tenths / 10:.1f} s"


def format_bus(frame: BusFrame, msg: Decoded, modkind: str | None = None) -> str:
    """Logregel van een ontvangen frame, bijvoorbeeld 'imd 01 : event: 01 01 F2 55 51 -> knop 15 : (...)'."""
    hexstr = frame.raw.hex(" ").upper()
    addr = f"{frame.address:02X}"
    if frame.address <= 0x1F:
        if msg.kind == "input_event":
            return f"imd {addr} : event: {hexstr} -> knop {msg.channel} : ({msg.text})"
        if msg.kind == "input_status":
            return f"imd {addr} : status: {hexstr} -> {msg.text}"
        if msg.kind == "ack":
            return f"imd {addr} : ack  : {hexstr} -> 00 *bevestiging*"
        if msg.kind == "status_request":
            return f"imd {addr} : cmd  : {hexstr} -> 01 *Status opvragen*"
        return f"onbekend {addr} : {hexstr}"
    if msg.kind == "jrm_event":
        return f"jrm {addr} : event: {hexstr} -> kanaal {msg.channel} -> {msg.text}"
    prefix = _uitgang_prefix(modkind, frame.payload)
    if msg.kind == "output_status":
        return (f"{prefix} {addr} : {msg.soort:<5}: {hexstr} -> "
                f"{bitstr(msg.value, 8)} (aan: {_kanalen(msg.value)})")
    if msg.kind in ("output_cmd", "status_request"):
        tekst = _commando_tekst(frame.payload, msg, modkind)
        return f"{prefix} {addr} : cmd  : {hexstr} -> {frame.payload[0]:02X} *{tekst}*"
    if msg.kind == "ack":
        return f"{prefix} {addr} : ack  : {hexstr} -> 00 *bevestiging*"
    return f"onbekend {addr} : {hexstr}"


def _crc_bytes(data: bytes) -> tuple[int, int]:
    crc = phc_crc(data)
    return crc & 0xFF, crc >> 8


def describe_sent(stm_frame: bytes, modkind_of: Callable[[int], str | None]) -> str:
    """Logregel van een verstuurd commando, met de bytes zoals die op de bus verschijnen.

    De CRC van een STM-frame dekt de STM-header mee; op de bus geldt alleen adres, lengte
    en payload. Daarom wordt de regel opnieuw opgebouwd met de bus-CRC.
    """
    body = unwrap_stm(stm_frame)
    if len(body) < 7:
        return "ongeldig frame"
    if body[:4] == HEADER_VIRTUAL:
        address, byte = body[4], body[5]
        channel, code = byte >> 4, byte & 0x0F
        bus = bytes([address, 0x01, byte])
        raw = bus + bytes(_crc_bytes(bus))
        naam = IMD_EVENTEN[code][2] if code in IMD_EVENTEN else f"functie {code}"
        return f"imd {address:02X} : virtueel: {raw.hex(' ').upper()} -> knop {channel} : ({naam})"
    address = body[4]
    lengte = body[5] & 0x7F
    payload = body[6:6 + lengte]
    bus = bytes([address, lengte]) + payload
    raw = bus + bytes(_crc_bytes(bus))
    frame = BusFrame(address, payload, raw)
    return format_bus(frame, decode_frame(frame), modkind_of(address))
