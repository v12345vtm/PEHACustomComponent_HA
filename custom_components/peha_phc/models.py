# models.py - Peha PHC versie 0.1.5
"""Toestand per module. Puur Python, zodat de logica los testbaar is."""
from __future__ import annotations

from dataclasses import dataclass, field

from .const import (
    AANTAL_INGANGEN,
    AANTAL_RELAIS,
    AANTAL_ROLLUIKEN,
    CONF_NAAM,
    CONF_PHC,
    CONF_TYPE,
    MODULE_CODES,
    MODULE_INGANG,
    MODULE_LABELS,
    MODULE_RELAIS,
    MODULE_ROLLUIK,
    DEFAULT_LOOPTIJDEN,
    module_address,
)
from .protocol import (
    JRM_OMHOOG,
    JRM_OMHOOG_STOP,
    JRM_OMLAAG,
    JRM_OMLAAG_STOP,
    JRM_STOP,
    OUT_AAN,
    OUT_OMSCHAKELEN,
    OUT_UIT,
    Decoded,
    imd_event_tekst,
)


def _bits(values: list) -> str | None:
    """Toon bits als tekst. Onbekende waarden zijn '?'. Alles onbekend geeft None."""
    if all(v is None for v in values):
        return None
    return "".join("?" if v is None else ("1" if v else "0") for v in values)


@dataclass
class CoverState:
    """Toestand van één rolluikkanaal. Alleen gebaseerd op feedback van de module."""

    moving: str | None = None   # "omhoog", "omlaag" of None
    closed: bool | None = None  # True = dicht, False = niet dicht, None = onbekend
    halted: bool = False        # gestopt tijdens een beweging
    duration: float = 0.0       # looptijd van de lopende beweging, 0 = looptijd uit de instelling gebruiken
    generation: int = 0         # verhoogt bij elke nieuwe beweging, zodat de hub de timer opnieuw start

    def start(self, direction: str, duration: float | None = None) -> None:
        self.moving = direction
        self.halted = False
        self.generation += 1
        self.duration = duration or 0.0

    def stop(self) -> None:
        if self.moving is not None:
            self.moving = None
            self.halted = True
            self.closed = False

    def done(self, closed: bool) -> None:
        self.moving = None
        self.halted = False
        self.closed = closed

    def finish_timer(self) -> None:
        """Looptijd voorbij zonder bericht: einde volgt uit de richting."""
        if self.moving == "omlaag":
            self.done(True)
        elif self.moving == "omhoog":
            self.done(False)

    @property
    def status(self) -> str:
        if self.moving == "omhoog":
            return "opening"
        if self.moving == "omlaag":
            return "closing"
        if self.halted:
            return "halted"
        if self.closed is None:
            return "unknown"
        return "closed" if self.closed else "open"


@dataclass
class PhcModule:
    kind: str
    phc: int
    name: str
    address: int
    relays: list = field(default_factory=lambda: [None] * AANTAL_RELAIS)
    inputs: list = field(default_factory=lambda: [None] * AANTAL_INGANGEN)
    leds: list = field(default_factory=lambda: [None] * AANTAL_INGANGEN)
    covers: list = field(default_factory=lambda: [CoverState() for _ in range(AANTAL_ROLLUIKEN)])
    runtimes: list = field(default_factory=lambda: list(DEFAULT_LOOPTIJDEN))
    knop_code: list = field(default_factory=lambda: [None] * AANTAL_INGANGEN)
    laatste_event: tuple | None = None
    laatste_event_tijd: str = ""
    raw_status: int | None = None
    last_text: str = "nog geen bericht ontvangen"
    last_hex: str = ""
    last_time: str = ""

    @classmethod
    def from_config(cls, item: dict) -> PhcModule:
        kind, phc = item[CONF_TYPE], int(item[CONF_PHC])
        return cls(kind=kind, phc=phc, name=item[CONF_NAAM], address=module_address(kind, phc))

    @property
    def code(self) -> str:
        return MODULE_CODES[self.kind]

    @property
    def device_id(self) -> str:
        return f"{self.code}_{self.phc:02d}"

    @property
    def model(self) -> str:
        return f"{MODULE_LABELS[self.kind]} (adres 0x{self.address:02X})"

    def status_text(self) -> str | None:
        if self.kind == MODULE_RELAIS:
            return _bits(self.relays)
        if self.kind == MODULE_INGANG:
            ingangen, leds = _bits(self.inputs), _bits(self.leds)
            if ingangen is None and leds is None:
                return None
            return f"{ingangen or '?' * AANTAL_INGANGEN},{leds or '?' * AANTAL_INGANGEN}"
        if self.kind == MODULE_ROLLUIK:
            return " ".join(f"{i}:{cover.status}" for i, cover in enumerate(self.covers))
        return None

    def laatste_tekst(self) -> str | None:
        """Vereenvoudigd event van de laatste knopactie, bijvoorbeeld 01.12.2."""
        if self.laatste_event is None:
            return None
        knop, code, _actie = self.laatste_event
        return imd_event_tekst(self.phc, knop, code)

    def optimistic_relay(self, channel: int, action: str) -> None:
        if action == "aan":
            self.relays[channel] = True
        elif action == "uit":
            self.relays[channel] = False
        else:
            self.relays[channel] = not bool(self.relays[channel])

    def optimistic_cover(self, channel: int, action: str, duration: float) -> None:
        cover = self.covers[channel]
        if action == "stop":
            cover.stop()
        else:
            cover.start("omhoog" if action == "omhoog" else "omlaag", duration)

    def apply(self, msg: Decoded) -> list[tuple]:
        """Verwerkt een busbericht en geeft neveneffecten terug voor de hub."""
        effects: list[tuple] = []

        if self.kind == MODULE_INGANG:
            if msg.kind == "input_event" and msg.channel is not None:
                self.inputs[msg.channel] = msg.pressed
                self.knop_code[msg.channel] = msg.code
                self.laatste_event = (msg.channel, msg.code, msg.action)
                effects.append(("input", msg.channel, msg.action))
            elif msg.kind == "input_status" and msg.value is not None:
                self.inputs = [bool((msg.value >> i) & 1) for i in range(AANTAL_INGANGEN)]
                self.leds = [bool((msg.leds >> i) & 1) for i in range(AANTAL_INGANGEN)]

        elif self.kind == MODULE_RELAIS:
            if msg.kind == "output_status" and msg.value is not None:
                self.raw_status = msg.value
                self.relays = [bool((msg.value >> i) & 1) for i in range(AANTAL_RELAIS)]
            elif msg.kind == "output_cmd" and msg.channel is not None:
                if msg.code == OUT_AAN:
                    self.relays[msg.channel] = True
                elif msg.code == OUT_UIT:
                    self.relays[msg.channel] = False
                elif msg.code == OUT_OMSCHAKELEN:
                    effects.append(("refresh",))

        elif self.kind == MODULE_ROLLUIK:
            if msg.kind == "output_status" and msg.value is not None:
                self.raw_status = msg.value
            elif msg.channel is not None and msg.channel < AANTAL_ROLLUIKEN:
                if msg.kind == "jrm_event":
                    self._apply_jrm_event(msg.channel, msg.code)
                elif msg.kind == "output_cmd":
                    self._apply_jrm_command(msg)

        return effects

    def _apply_jrm_event(self, channel: int, code: int | None) -> None:
        cover = self.covers[channel]
        if code == 3:
            cover.start("omlaag")
        elif code == 4:
            cover.done(False)
        elif code == 5:
            cover.done(True)
        elif code == 7:
            cover.stop()
        elif code == 8:
            cover.finish_timer()
        # code 6 (timer gestart) verandert de toestand niet

    def _apply_jrm_command(self, msg: Decoded) -> None:
        cover = self.covers[msg.channel]
        if msg.tenths is None:
            # 1-byte commando: alleen stop is relevant voor een rolluik
            if msg.code == JRM_STOP:
                cover.stop()
            return
        duur = msg.tenths / 10
        if msg.code == JRM_OMHOOG:
            cover.start("omhoog", duur)
        elif msg.code == JRM_OMLAAG:
            cover.start("omlaag", duur)
        elif msg.code == JRM_OMHOOG_STOP:
            if cover.moving == "omhoog":
                cover.stop()
            else:
                cover.start("omhoog", duur)
        elif msg.code == JRM_OMLAAG_STOP:
            if cover.moving == "omlaag":
                cover.stop()
            else:
                cover.start("omlaag", duur)
