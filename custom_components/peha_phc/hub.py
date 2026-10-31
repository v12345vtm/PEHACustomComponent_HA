# hub.py - Peha PHC versie 0.1.5
# v0.1.5: ethernet-knop stuurt dezelfde aanvraag als curl; verbroken verbinding zonder antwoord telt als ACK
"""Verbindingen met de STM-stuureenheid (verzenden) en de RS485-busdongle (ontvangen)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit


from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from .const import (
    BUS_TYPES,
    CONF_ETHERNET,
    CONF_IP,
    CONF_STM,
    CONF_TYPE,
    DOMAIN,
    ETHERNET_TIMEOUT,
    MODULE_ETHERNET,
    MODULE_ETHERNET_KNOP,
    EVENT_INGANG,
    HOLD_TIMEOUT,
    LOG_LENGTE,
    MODULE_ROLLUIK,
    MODULE_VIRTUEEL,
    PRIORITEIT,
    SERIAL_OPTIONS,
    STATUS_NA_LOSLATEN,
    TIMER_MARGE,
)
from .models import PhcModule
from .protocol import (
    VIRTUAL_CODES,
    BusFrame,
    BusParser,
    command_frame,
    cover_frame,
    decode_frame,
    describe_sent,
    format_bus,
    ethernet_url,
    imd_event_tekst,
    relay_frame,
    status_frame,
    virtual_input_frame,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 10.0       # seconden wachten voor een nieuwe poging
INTERFRAME_DELAY = 0.05      # pauze tussen twee verzonden commando's
POLL_DELAY = 0.4             # pauze tussen statusopvragingen bij het opstarten
STATUS_REFRESH_DELAY = 0.5   # wachttijd voor een statusopvraag na een omschakelcommando
DUPLICATE_WINDOW = 0.25      # identieke frames binnen dit venster worden genegeerd
IGNORED_ADDRESSES = (0xFE, 0xE0)  # STM-header en broadcast
LINKS = ("stm", "bus")


# User-Agent zoals curl die stuurt, zodat de aanvraag gelijk is aan het werkende curl-commando.
ETHERNET_USER_AGENT = "curl/8.5.0"


class PhcHub:
    """Beheert de twee seriële verbindingen, de toestand van alle modules en de logs."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.stm_port = ""
        self.bus_port = ""
        self.modules: dict[int, PhcModule] = {}
        self.virtual_buttons: list[dict] = []
        self.ethernet_modules: list[dict] = []
        self.ethernet_knoppen: list[dict] = []
        self.enabled: dict[str, bool] = {"stm": True, "bus": True}
        self.stm_connected = False
        self.bus_connected = False
        self.log_verstuurd: deque[dict] = deque(maxlen=LOG_LENGTE)
        self.log_verwerkt: deque[dict] = deque(maxlen=LOG_LENGTE)
        self._stm_writer: Any = None
        self._send_lock = asyncio.Lock()
        self._parser = BusParser()
        self._recent: dict[bytes, float] = {}
        self._unknown_seen: set[int] = set()
        self._status_pending: dict[int, Callable[[], None]] = {}
        self._hold_timers: dict[tuple[int, int], Callable[[], None]] = {}
        self._cover_timers: dict[tuple[int, int], Callable[[], None]] = {}
        self._link_tasks: dict[str, asyncio.Task | None] = {"stm": None, "bus": None}
        self._link_locks: dict[str, asyncio.Lock] = {"stm": asyncio.Lock(), "bus": asyncio.Lock()}

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
        self.ethernet_modules = [i for i in items if i[CONF_TYPE] == MODULE_ETHERNET]
        self.ethernet_knoppen = [i for i in items if i[CONF_TYPE] == MODULE_ETHERNET_KNOP]
        for item in items:
            if item[CONF_TYPE] in BUS_TYPES:
                module = PhcModule.from_config(item)
                self.modules[module.address] = module

    def modules_of(self, kind: str) -> list[PhcModule]:
        return [m for m in self.modules.values() if m.kind == kind]

    # ----------------------------------------------------------- levenscyclus

    async def async_start(self) -> None:
        for which in LINKS:
            async with self._link_locks[which]:
                if self.enabled[which]:
                    self._start_link(which)

    async def async_stop(self) -> None:
        for which in LINKS:
            async with self._link_locks[which]:
                await self._stop_link(which)
        for cancel in self._cover_timers.values():
            cancel()
        self._cover_timers.clear()
        for cancel in self._status_pending.values():
            cancel()
        self._status_pending.clear()
        for cancel in self._hold_timers.values():
            cancel()
        self._hold_timers.clear()

    async def async_set_enabled(self, which: str, enabled: bool) -> None:
        """Opent of sluit een poort. Gesloten betekent dat de poort echt wordt losgelaten.

        Met een slot wordt elke schakeling afgemaakt voordat de volgende begint. Zo eindigt
        snel achter elkaar schakelen altijd in de stand van de laatste schakeling.
        """
        async with self._link_locks[which]:
            self.enabled[which] = enabled
            if enabled:
                self._start_link(which)
            else:
                await self._stop_link(which)
        self._dispatch()

    def _start_link(self, which: str) -> None:
        task = self._link_tasks[which]
        if task is None or task.done():
            self._link_tasks[which] = self.hass.async_create_background_task(
                self._run_link(which), f"peha_phc_{which}"
            )

    async def _stop_link(self, which: str) -> None:
        task = self._link_tasks[which]
        self._link_tasks[which] = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._set_link(which, False)

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
                                _LOGGER.exception("Bus-frame kon niet verwerkt worden: %s",
                                                  frame.raw.hex(" "))
                    else:
                        _LOGGER.debug("STM antwoord: %s", data.hex(" "))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Verbinding %s verbroken: %s", which, err)
            finally:
                if which == "stm" and self._stm_writer is writer:
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
            if not self.enabled["stm"]:
                raise HomeAssistantError("De Peha USB-kabel (STM) is uitgeschakeld in de integratie")
            raise HomeAssistantError("De Peha USB-kabel (STM) is niet verbonden")
        async with self._send_lock:
            _LOGGER.debug("STM << %s", frame.hex(" "))
            try:
                writer.write(frame)
                await writer.drain()
            except OSError as err:
                raise HomeAssistantError(f"Schrijven naar de STM mislukt: {err}") from err
            self._log(self.log_verstuurd, frame.hex(" ").upper(), describe_sent(frame, self._kind_of))
            self._dispatch()
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
        """Virtuele ingang: één commando, zoals de Node-RED IMD GENERATOR. Geen loslaatcommando."""
        code = VIRTUAL_CODES.get(functie)
        if code is None:
            raise HomeAssistantError(f"Onbekende virtuele functie: {functie}")
        await self._async_send(virtual_input_frame(address, (channel << 4) | code))

    async def async_ethernet_knop(self, ip: str, stm: int, mod: int, cha: int, functie: str) -> None:
        """Ethernet knop: één HTTP-opdracht naar de ethernetmodule, met precies dezelfde aanvraag als curl."""
        code = VIRTUAL_CODES.get(functie)
        if code is None:
            raise HomeAssistantError(f"Onbekende functie: {functie}")
        url = ethernet_url(ip, stm, mod, cha, code)
        doel = urlsplit(url)
        poort = doel.port or 80
        host = doel.hostname if poort == 80 else f"{doel.hostname}:{poort}"
        verzoek = (
            f"GET {doel.path}?{doel.query} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {ETHERNET_USER_AGENT}\r\n"
            "Accept: */*\r\n"
            "\r\n"
        ).encode("ascii")
        ack = f"ACK {stm}_{mod}_{cha}_EVT{code}"
        _LOGGER.debug("Ethernet verzoek naar %s: %r", url, verzoek)
        try:
            lezer, schrijver = await asyncio.wait_for(
                asyncio.open_connection(doel.hostname, poort), ETHERNET_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise HomeAssistantError(
                f"Ethernetmodule {ip} is niet bereikbaar: {str(err) or 'geen verbinding'}"
            ) from err
        try:
            schrijver.write(verzoek)
            await schrijver.drain()
        except OSError as err:
            schrijver.close()
            raise HomeAssistantError(f"Ethernetmodule {ip} is niet bereikbaar: {err}") from err
        try:
            antwoord = await asyncio.wait_for(lezer.read(4096), ETHERNET_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise HomeAssistantError(
                f"Ethernetmodule {ip} gaf geen antwoord binnen {ETHERNET_TIMEOUT} s"
            ) from err
        except ConnectionResetError:
            # De module reset de verbinding na het verzoek (Node-RED: "socket hang up"): dat is de bevestiging.
            antwoord = b""
        except OSError as err:
            raise HomeAssistantError(f"Ethernetmodule {ip} is niet bereikbaar: {err}") from err
        finally:
            schrijver.close()
        if antwoord:
            regel = antwoord.split(b"\r\n", 1)[0].decode("ascii", "replace")
            delen = regel.split(" ")
            if len(delen) >= 2 and delen[0].startswith("HTTP/") and delen[1].isdigit() and int(delen[1]) >= 300:
                raise HomeAssistantError(f"Ethernetmodule {ip} antwoordde met status {delen[1]}")
            ack = f"{ack} ({regel})"
        else:
            # Geen HTTP-antwoord: de module sloot de verbinding, de opdracht is dan uitgevoerd.
            ack = f"{ack} (geen HTTP-antwoord)"
        self._log(self.log_verstuurd, f"HTTP GET {ip}", ack)
        self._dispatch()

    async def _async_poll_all(self) -> None:
        for module in list(self.modules.values()):
            try:
                await self.async_request_status(module.address)
            except HomeAssistantError:
                return
            await asyncio.sleep(POLL_DELAY)

    def _kind_of(self, address: int) -> str | None:
        module = self.modules.get(address)
        return module.kind if module else None

    @staticmethod
    def _log(log: deque, hexstr: str, betekenis: str) -> None:
        log.append({"tijd": datetime.now().strftime("%H:%M:%S"), "hex": hexstr, "betekenis": betekenis})

    # --------------------------------------------------------------- ontvangen

    def _handle_frame(self, frame: BusFrame) -> None:
        if frame.address in IGNORED_ADDRESSES or self._is_duplicate(frame.raw):
            return
        msg = decode_frame(frame)
        module = self.modules.get(frame.address)
        regel = format_bus(frame, msg, module.kind if module else None)
        self._log(self.log_verwerkt, frame.raw.hex(" ").upper(), regel)
        if module is None:
            if frame.address not in self._unknown_seen:
                self._unknown_seen.add(frame.address)
                _LOGGER.info("Bus-adres 0x%02X is niet ingesteld in de integratie: %s",
                             frame.address, frame.raw.hex(" "))
            self._dispatch()
            return

        module.last_text = regel
        module.last_hex = frame.raw.hex(" ").upper()
        module.last_time = datetime.now().isoformat(timespec="seconds")
        _LOGGER.debug("Bus: %s", regel)

        before = [cover.generation for cover in module.covers]
        for effect in module.apply(msg):
            if effect[0] == "input":
                _, channel, action = effect
                module.laatste_event_tijd = module.last_time
                self.hass.bus.async_fire(
                    EVENT_INGANG,
                    {
                        "module": module.phc,
                        "adres": module.address,
                        "naam": module.name,
                        "kanaal": channel,
                        "event": imd_event_tekst(module.phc, channel, module.knop_code[channel]),
                        "actie": action,
                    },
                )
                self._input_feedback(module, channel)
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

    def _schedule_status(self, address: int, delay: float | None = None) -> None:
        """Vraagt de status van een module op na 'delay' seconden. Een eerdere, nog wachtende aanvraag vervalt."""
        wacht = STATUS_REFRESH_DELAY if delay is None else delay
        vorige = self._status_pending.pop(address, None)
        if vorige is not None:
            vorige()

        async def _refresh(_now: Any) -> None:
            self._status_pending.pop(address, None)
            try:
                await self.async_request_status(address)
            except HomeAssistantError:
                _LOGGER.debug("Statusopvraag mislukt voor adres 0x%02X", address)

        self._status_pending[address] = async_call_later(self.hass, wacht, _refresh)

    def _input_feedback(self, module: PhcModule, channel: int) -> None:
        """Statusopvraag na een ingangsactie, pas nadat de knop is losgelaten.

        Tijdens het indrukken vraagt de integratie niets: de module meldt dan nog 'hoog', en dat
        tussentijdse antwoord mag de stand niet meer bepalen.
        """
        key = (module.address, channel)
        if module.inputs[channel]:
            if key not in self._hold_timers:
                self._arm_hold_timer(module.address, key)
        else:
            self._cancel_hold_timer(key)
            self._schedule_status(module.address, STATUS_NA_LOSLATEN)

    def _arm_hold_timer(self, address: int, key: tuple[int, int]) -> None:
        """Vangnet: zonder loslaat-event vraagt de integratie na HOLD_TIMEOUT alsnog de status op."""

        async def _expired(_now: Any) -> None:
            self._hold_timers.pop(key, None)
            self._schedule_status(address)

        self._hold_timers[key] = async_call_later(self.hass, HOLD_TIMEOUT, _expired)

    def _cancel_hold_timer(self, key: tuple[int, int]) -> None:
        cancel = self._hold_timers.pop(key, None)
        if cancel is not None:
            cancel()

    # ------------------------------------------------------- rolluiktimers

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
