"""Verbindingen met de STM-stuureenheid (verzenden) en de RS485-busdongle (ontvangen)."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_TYPE,
    DOMAIN,
    EVENT_INGANG,
    MODULE_ROLLUIK,
    MODULE_VIRTUEEL,
    PRIORITEIT,
    SERIAL_OPTIONS,
    TIMER_MARGE,
    VIRTUAL_FUNCTIES,
)
from .models import PhcModule
from .protocol import (
    BusFrame,
    BusParser,
    command_frame,
    cover_frame,
    decode_frame,
    relay_frame,
    status_frame,
    virtual_input_frame,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 10.0       # seconden wachten voor een nieuwe poging
INTERFRAME_DELAY = 0.05      # pauze tussen twee verzonden commando's
POLL_DELAY = 0.4             # pauze tussen statusopvragingen bij het opstarten
STATUS_REFRESH_DELAY = 0.5   # wachttijd voor een statusverversing na een bus-omschakelcommando
DUPLICATE_WINDOW = 0.25      # identieke frames binnen dit venster worden genegeerd
IGNORED_ADDRESSES = (0xFE, 0xE0)  # STM-header en broadcast


class PhcHub:
    """Beheert de twee seriële verbindingen en de toestand van alle modules."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.stm_port = ""
        self.bus_port = ""
        self.modules: dict[int, PhcModule] = {}
        self.virtual_buttons: list[dict] = []
        self.stm_connected = False
        self.bus_connected = False
        self._stm_writer: Any = None
        self._send_lock = asyncio.Lock()
        self._parser = BusParser()
        self._recent: dict[bytes, float] = {}
        self._unknown_seen: set[int] = set()
        self._status_pending: set[int] = set()
        self._cover_timers: dict[tuple[int, int], Callable[[], None]] = {}
        self._tasks: list[asyncio.Task] = []

    @property
    def signal(self) -> str:
        return f"{DOMAIN}_{self.entry_id}_update"

    @property
    def available(self) -> bool:
        return self.stm_connected and self.bus_connected

    def configure(self, items: list[dict], stm_port: str, bus_port: str) -> None:
        self.stm_port = stm_port
        self.bus_port = bus_port
        self.modules = {}
        self.virtual_buttons = [i for i in items if i[CONF_TYPE] == MODULE_VIRTUEEL]
        for item in items:
            if item[CONF_TYPE] != MODULE_VIRTUEEL:
                module = PhcModule.from_config(item)
                self.modules[module.address] = module

    def modules_of(self, kind: str) -> list[PhcModule]:
        return [m for m in self.modules.values() if m.kind == kind]

    # ----------------------------------------------------------------- levenscyclus

    async def async_start(self) -> None:
        self._tasks = [
            self.hass.async_create_background_task(self._run_link("stm"), "peha_phc_stm"),
            self.hass.async_create_background_task(self._run_link("bus"), "peha_phc_bus"),
        ]

    async def async_stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        for cancel in self._cover_timers.values():
            cancel()
        self._cover_timers.clear()

    async def _run_link(self, which: str) -> None:
        # Hier geïmporteerd, zodat de losse tests zonder pyserial kunnen draaien.
        from serial_asyncio import open_serial_connection  # pylint: disable=import-outside-toplevel

        port = self.stm_port if which == "stm" else self.bus_port
        while True:
            try:
                reader, writer = await open_serial_connection(url=port, **SERIAL_OPTIONS)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Poort %s (%s) niet beschikbaar: %s", port, which, err)
                await asyncio.sleep(RECONNECT_DELAY)
                continue

            _LOGGER.info("Poort %s (%s) verbonden", port, which)
            if which == "stm":
                self._stm_writer = writer
            else:
                self._parser.reset()
            self._set_link(which, True)
            try:
                while data := await reader.read(256):
                    if which == "bus":
                        for frame in self._parser.feed(data):
                            try:
                                self._handle_frame(frame)
                            except Exception:  # noqa: BLE001
                                _LOGGER.exception("Bus-frame kon niet verwerkt worden: %s", frame.raw.hex(" "))
                    else:
                        _LOGGER.debug("STM antwoord: %s", data.hex(" "))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Verbinding %s verbroken: %s", which, err)
            finally:
                if which == "stm":
                    self._stm_writer = None
                writer.close()
                self._set_link(which, False)
            await asyncio.sleep(RECONNECT_DELAY)

    def _set_link(self, which: str, up: bool) -> None:
        if which == "stm":
            self.stm_connected = up
        else:
            self.bus_connected = up
        if up and self.stm_connected and self.bus_connected:
            # Vraag bij elke (her)verbinding de status op, vooral voor de ingangen.
            self.hass.async_create_background_task(self._async_poll_all(), "peha_phc_poll")
        self._dispatch()

    # --------------------------------------------------------------- verzenden

    async def _async_send(self, frame: bytes) -> None:
        writer = self._stm_writer
        if writer is None or not self.stm_connected:
            raise HomeAssistantError("De Peha USB-kabel (STM) is niet verbonden")
        async with self._send_lock:
            _LOGGER.debug("STM << %s", frame.hex(" "))
            try:
                writer.write(frame)
                await writer.drain()
            except OSError as err:
                raise HomeAssistantError(f"Schrijven naar de STM mislukt: {err}") from err
            await asyncio.sleep(INTERFRAME_DELAY)

    async def async_request_status(self, address: int) -> None:
        await self._async_send(status_frame(address))

    async def async_raw(self, address: int, data: bytes) -> None:
        await self._async_send(command_frame(address, data))

    async def async_relay(self, module: PhcModule, channel: int, action: str) -> None:
        await self._async_send(relay_frame(module.address, channel, action))
        module.optimistic_relay(channel, action)
        self._dispatch()

    async def async_cover(self, module: PhcModule, channel: int, action: str) -> None:
        duur = module.runtimes[channel]
        await self._async_send(cover_frame(module.address, channel, action, round(duur * 10), PRIORITEIT))
        before = [cover.generation for cover in module.covers]
        module.optimistic_cover(channel, action, duur)
        self._refresh_cover_timers(module, before)
        self._dispatch()

    async def async_virtual_click(self, address: int, channel: int, functie: str) -> None:
        press, release, hold = VIRTUAL_FUNCTIES[functie]
        await self._async_send(virtual_input_frame(address, (channel << 4) | press))
        await asyncio.sleep(hold)
        await self._async_send(virtual_input_frame(address, (channel << 4) | release))

    async def _async_poll_all(self) -> None:
        for module in list(self.modules.values()):
            try:
                await self.async_request_status(module.address)
            except HomeAssistantError:
                return
            await asyncio.sleep(POLL_DELAY)

    # --------------------------------------------------------------- ontvangen

    def _handle_frame(self, frame: BusFrame) -> None:
        if frame.address in IGNORED_ADDRESSES or self._is_duplicate(frame.raw):
            return
        msg = decode_frame(frame)
        module = self.modules.get(frame.address)
        if module is None:
            if frame.address not in self._unknown_seen:
                self._unknown_seen.add(frame.address)
                _LOGGER.info(
                    "Bus-adres 0x%02X is niet ingesteld in de integratie: %s",
                    frame.address, frame.raw.hex(" "),
                )
            return

        module.last_text = msg.text
        module.last_hex = frame.raw.hex(" ").upper()
        module.last_time = datetime.now().isoformat(timespec="seconds")
        _LOGGER.debug("Bus: %s", msg.text)

        before = [cover.generation for cover in module.covers]
        for effect in module.apply(msg):
            if effect[0] == "input":
                _, channel, action = effect
                self.hass.bus.async_fire(
                    EVENT_INGANG,
                    {
                        "module": module.phc,
                        "adres": module.address,
                        "naam": module.name,
                        "kanaal": channel,
                        "actie": action,
                    },
                )
            elif effect[0] == "refresh":
                self._schedule_status(module.address)

        if module.kind == MODULE_ROLLUIK:
            self._refresh_cover_timers(module, before)
        self._dispatch()

    def _is_duplicate(self, raw: bytes) -> bool:
        now = time.monotonic()
        last = self._recent.get(raw)
        self._recent[raw] = now
        if len(self._recent) > 200:
            self._recent = {k: t for k, t in self._recent.items() if now - t < DUPLICATE_WINDOW}
        return last is not None and now - last < DUPLICATE_WINDOW

    def _schedule_status(self, address: int) -> None:
        if address in self._status_pending:
            return
        self._status_pending.add(address)

        async def _refresh(_now: Any) -> None:
            self._status_pending.discard(address)
            try:
                await self.async_request_status(address)
            except HomeAssistantError:
                _LOGGER.debug("Statusverversing mislukt voor adres 0x%02X", address)

        async_call_later(self.hass, STATUS_REFRESH_DELAY, _refresh)

    def _refresh_cover_timers(self, module: PhcModule, before: list[int]) -> None:
        """Start de looptijd-timer opnieuw bij elke nieuwe beweging en ruimt hem op als de beweging voorbij is."""
        for channel, cover in enumerate(module.covers):
            key = (module.address, channel)
            if cover.moving is None:
                self._cancel_cover_timer(key)
            elif cover.generation != before[channel] or key not in self._cover_timers:
                self._cancel_cover_timer(key)
                self._arm_cover_timer(module, channel)

    def _cancel_cover_timer(self, key: tuple[int, int]) -> None:
        cancel = self._cover_timers.pop(key, None)
        if cancel is not None:
            cancel()

    def _arm_cover_timer(self, module: PhcModule, channel: int) -> None:
        """Vangnet: als de module geen eindmelding stuurt, eindigt de beweging na de looptijd plus een marge."""
        key = (module.address, channel)
        cover = module.covers[channel]
        delay = (cover.duration or module.runtimes[channel]) + TIMER_MARGE

        async def _timeout(_now: Any) -> None:
            self._cover_timers.pop(key, None)
            cover.finish_timer()
            self._dispatch()

        self._cover_timers[key] = async_call_later(self.hass, delay, _timeout)

    def _dispatch(self) -> None:
        async_dispatcher_send(self.hass, self.signal)
