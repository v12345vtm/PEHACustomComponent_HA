# Peha PHC-integratie, versie 1.1.0
"""De twee USB-poorten, en de testmodus zonder hardware.

Usbkabel (STM): alleen schrijven, de commando's gaan in C0/C1-frames.
Bus-dongle (RS485): alleen lezen, ruwe PHC-frames die de parser in de hub verwerkt.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress

from .const import BAUDRATE, TYPE_RELAIS, TYPE_ROLLUIK
from .model import Module
from .protocol import (
    RELAIS_NAMEN,
    ROLLUIK_GEBEURTENIS_CODE,
    ROLLUIK_NAMEN,
    STATUS_VERZOEK,
    STM_KOP,
    bus_frame,
    ontescape,
)


class SerialTransport:
    """Eén seriële poort op 19200 baud, 8 databits, geen pariteit, 2 stopbits."""

    def __init__(self, poort: str) -> None:
        self.poort = poort
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def open(self) -> None:
        async with self._lock:
            if self.is_open:
                return
            import serial  # geïnstalleerd via de manifest (pyserial-asyncio)
            import serial_asyncio

            try:
                self._reader, self._writer = await serial_asyncio.open_serial_connection(
                    url=self.poort,
                    baudrate=BAUDRATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_TWO,
                )
            except OSError as err:
                raise ConnectionError(f"poort {self.poort} is niet te openen: {err}") from err

    async def read(self) -> bytes:
        if self._reader is None or not self.is_open:
            raise ConnectionError(f"poort {self.poort} is niet open")
        data = await self._reader.read(256)
        if not data:
            raise ConnectionError(f"poort {self.poort} is gesloten")
        return data

    async def write(self, data: bytes) -> None:
        if self._writer is None or not self.is_open:
            raise ConnectionError(f"poort {self.poort} is niet open")
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


class DemoTransport:
    """Testmodus: geen hardware. Commando's naar de STM krijgen een nagebootst busantwoord.

    Eén object vervangt beide poorten. Het is versimpeld: timers worden direct toegepast,
    en ingangen houden hun stand alleen vast via de busberichten die je zelf simuleert.
    """

    is_open = True

    def __init__(self, modules: list[Module]) -> None:
        self._modules = {m.adres: m for m in modules}
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._mask: dict[int, int] = {}
        self._ingangen: dict[int, int] = {}
        self._richting: dict[tuple[int, int], str] = {}
        self._timers: dict[tuple[int, int], asyncio.TimerHandle] = {}

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()

    async def read(self) -> bytes:
        return await self._queue.get()

    async def write(self, data: bytes) -> None:
        for antwoord in self._verwerk(data):
            self._queue.put_nowait(antwoord)

    def _verwerk(self, data: bytes) -> list[bytes]:
        raw = ontescape(data)
        if raw[:4] != STM_KOP or len(raw) < 8:
            return []
        adres = raw[4]
        payload = raw[6:6 + (raw[5] & 0x7F)]
        module = self._modules.get(adres)
        if module is None or not payload:
            return []
        if module.type == TYPE_RELAIS:
            return self._relais(adres, payload)
        if module.type == TYPE_ROLLUIK:
            return self._rolluik(adres, payload)
        return self._ingang(adres, payload)

    def _relais(self, adres: int, payload: bytes) -> list[bytes]:
        mask = self._mask.get(adres, 0)
        if payload == STATUS_VERZOEK:
            return [bus_frame(adres, bytes([0x01, mask]))]
        actie = RELAIS_NAMEN.get(payload[0] & 0x1F, "")
        bit = 1 << (payload[0] >> 5)
        if actie.startswith("aan") or actie == "vergrendel_aan":
            mask |= bit
        elif actie.startswith("uit") or actie == "vergrendel_uit":
            mask &= ~bit
        elif actie.startswith("omschakelen"):
            mask ^= bit
        self._mask[adres] = mask & 0xFF
        return [bus_frame(adres, bytes([0x00, self._mask[adres]]))]

    def _rolluik(self, adres: int, payload: bytes) -> list[bytes]:
        kanaal = (payload[0] >> 5) & 0x03
        actie = ROLLUIK_NAMEN.get(payload[0] & 0x1F, "")
        sleutel = (adres, kanaal)
        if actie in ("omhoog", "omhoog_stop", "omlaag", "omlaag_stop"):
            richting = "omhoog" if actie.startswith("omhoog") else "omlaag"
            self._richting[sleutel] = richting
            tijd = (payload[2] | (payload[3] << 8)) / 10 if len(payload) >= 4 else 0.0
            self._plan(sleutel, tijd, richting)
            if richting == "omlaag":
                return [self._gebeurtenis(adres, kanaal, "start_omlaag")]
            return []
        if actie == "stop":
            self._annuleer(sleutel)
            richting = self._richting.get(sleutel)
            if richting:
                return [self._gebeurtenis(adres, kanaal, f"klaar_{richting}")]
        return []

    def _gebeurtenis(self, adres: int, kanaal: int, naam: str) -> bytes:
        return bus_frame(adres, bytes([(kanaal << 5) | ROLLUIK_GEBEURTENIS_CODE[naam], 0x00]))

    def _plan(self, sleutel: tuple[int, int], tijd: float, richting: str) -> None:
        self._annuleer(sleutel)
        if tijd > 0:
            loop = asyncio.get_running_loop()
            self._timers[sleutel] = loop.call_later(tijd, self._klaar, sleutel, richting)

    def _annuleer(self, sleutel: tuple[int, int]) -> None:
        timer = self._timers.pop(sleutel, None)
        if timer is not None:
            timer.cancel()

    def _klaar(self, sleutel: tuple[int, int], richting: str) -> None:
        self._timers.pop(sleutel, None)
        adres, kanaal = sleutel
        self._queue.put_nowait(self._gebeurtenis(adres, kanaal, f"klaar_{richting}"))

    def _ingang(self, adres: int, payload: bytes) -> list[bytes]:
        if payload == STATUS_VERZOEK:
            mask = self._ingangen.get(adres, 0)
            return [bus_frame(adres, bytes([0x01, 0x00, mask & 0xFF, mask >> 8, 0x00]))]
        return []
