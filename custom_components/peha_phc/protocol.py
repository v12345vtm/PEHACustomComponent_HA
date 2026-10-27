"""PHC-protocol: CRC, STM-framing, busparser en decoders.

Puur Python zonder Home Assistant, zodat het los te testen is.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- STM-stuureenheid (USB-kabel): frames met C0 ... C1 en escaping ---------
FRAME_START = 0xC0
FRAME_END = 0xC1
FRAME_ESC = 0x7D

HEADER_CMD = bytes((0xFE, 0x00, 0x06, 0x00))      # commando met lengte-byte
HEADER_VIRTUAL = bytes((0xFE, 0x00, 0x21, 0x00))  # virtuele ingang (geen lengte-byte)

# --- Functiecodes van de output-modules (AMD = relais, JRM = rolluik) --------
OUT_STATUS = 0x01
OUT_AAN = 0x02          # relais aan (1 byte) / JRM stop
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

# IMD-ingangsevents: code -> (actie, ingedrukt?, omschrijving)
IMD_EVENTEN = {
    2: ("kort_ingedrukt", True, "Ein>0 kort ingedrukt"),
    3: ("kort_losgelaten", False, "Aus<0 losgelaten (<1 s)"),
    4: ("lang_ingedrukt", True, "Ein>1 lang ingedrukt"),
    5: ("lang_losgelaten", False, "Aus>1 losgelaten"),
    6: ("extra_lang_ingedrukt", True, "Ein>2 extra lang ingedrukt"),
    7: ("losgelaten", False, "Aus losgelaten"),
}

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
    text: str
    channel: int | None = None
    code: int | None = None
    value: int | None = None   # statusbyte (output) of ingangen-bitmask (input)
    leds: int | None = None    # LED-bitmask (input)
    pressed: bool | None = None
    action: str | None = None
    tenths: int | None = None  # tijd in 1/10 s
    prio: int | None = None


def decode_frame(frame: BusFrame) -> Decoded:
    address, payload = frame.address, frame.payload
    if address <= 0x1F:
        return _decode_input(address, payload)
    if 0x40 <= address <= 0x5F:
        return _decode_output(address, payload)
    return Decoded("unknown", address, f"onbekend adres 0x{address:02X}: {payload.hex(' ').upper()}")


def _decode_input(address: int, payload: bytes) -> Decoded:
    if len(payload) == 1:
        byte = payload[0]
        if byte == 0x00:
            return Decoded("ack", address, "ack ingangsmodule")
        if byte == 0x01:
            return Decoded("status_request", address, "statusopvraag (echo)")
        channel, code = byte >> 4, byte & 0x0F
        if code in IMD_EVENTEN:
            action, pressed, omschrijving = IMD_EVENTEN[code]
            return Decoded(
                "input_event", address, f"knop {channel}: {omschrijving}",
                channel=channel, code=code, action=action, pressed=pressed,
            )
    elif len(payload) in (4, 5) and payload[0] == 0x01:
        inputs = payload[2] | (payload[3] << 8)
        leds = payload[1] | ((payload[4] if len(payload) == 5 else 0) << 8)
        return Decoded(
            "input_status", address,
            f"ingangen {bitstr(inputs, 16)} LEDs {bitstr(leds, 16)}",
            value=inputs, leds=leds,
        )
    return Decoded("unknown", address, f"onbekend ingangsbericht {payload.hex(' ').upper()}")


def _decode_output(address: int, payload: bytes) -> Decoded:
    if not payload:
        return Decoded("unknown", address, "leeg bericht")
    first = payload[0]
    code = first & 0x1F
    channel = (first >> 5) & 0x07
    length = len(payload)

    if length == 1:
        if first == 0x00:
            return Decoded("ack", address, "ack outputmodule")
        if code == OUT_STATUS:
            return Decoded("status_request", address, "statusopvraag (echo)", channel=channel)
        return Decoded(
            "output_cmd", address, f"commando 0x{code:02X} kanaal {channel}",
            channel=channel, code=code,
        )

    if length == 2:
        if 3 <= code <= 8:
            jrm_kanaal = (first >> 5) & 0x03
            return Decoded(
                "jrm_event", address, f"kanaal {jrm_kanaal}: {JRM_EVENTEN[code]}",
                channel=jrm_kanaal, code=code,
            )
        if first in (0x00, 0x01):
            soort = "ack" if first == 0x00 else "status"
            return Decoded(
                "output_status", address, f"{soort} {bitstr(payload[1], 8)}",
                value=payload[1],
            )
        return Decoded(
            "output_cmd", address, f"commando 0x{code:02X} kanaal {channel} prio {payload[1]}",
            channel=channel, code=code, prio=payload[1],
        )

    if length == 3:
        tenths = payload[1] | (payload[2] << 8)
        return Decoded(
            "output_cmd", address, f"commando 0x{code:02X} kanaal {channel} tijd {tenths / 10:.1f} s",
            channel=channel, code=code, tenths=tenths,
        )

    if length == 4:
        tenths = payload[2] | (payload[3] << 8)
        return Decoded(
            "output_cmd", address,
            f"commando 0x{code:02X} kanaal {channel} prio {payload[1]} tijd {tenths / 10:.1f} s",
            channel=channel, code=code, prio=payload[1], tenths=tenths,
        )

    return Decoded("unknown", address, f"onbekend bericht {payload.hex(' ').upper()}")
