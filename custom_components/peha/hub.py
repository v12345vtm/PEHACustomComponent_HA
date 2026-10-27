# Peha PHC-integratie, versie 1.1.0
"""De hub: bewaart de stand van alle modules, stuurt commando's en verwerkt de busframes.

Deze laag kent geen Home Assistant. De integratie geeft een notify-functie mee die de hub
aanroept bij elke wijziging. Soorten: 'module' (data = adres), 'hub', 'conn' en 'event'.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from .const import (
    DEFAULT_PRIORITEIT,
    HERVERBIND_NA,
    IDLE_RESET,
    INGANG_MAX,
    LEDS_STANDAARD,
    NOODSTOP_MARGE,
    RELAIS_KANALEN,
    ROLLUIK_KANALEN,
    STM_PAUZE,
    TYPE_NAMEN,
    TYPE_RELAIS,
    TYPE_ROLLUIK,
)
from .model import Module
from .protocol import (
    ROLLUIK_STATUS_TEKST,
    ROLLUIK_TEKST,
    STATUS_VERZOEK,
    BusFrame,
    BusParser,
    ingang_status,
    relais_payload,
    relais_status,
    rolluik_gebeurtenis,
    rolluik_payload,
    stm_frame,
)

_LOGGER = logging.getLogger(__name__)
NotifyFn = Callable[[str, Any], None]

# Na deze acties weten we de stand al, dus zetten we die direct (optimistisch).
_OPTIMISTISCH = {"aan": True, "vergrendel_aan": True, "uit": False, "vergrendel_uit": False}
_OMHOOG = ("omhoog", "omhoog_stop")
_OMLAAG = ("omlaag", "omlaag_stop")


class PehaError(Exception):
    """Een commando kon niet worden verstuurd, of past niet bij de module."""


def _lege_stand(module: Module) -> dict[str, Any]:
    if module.type == TYPE_RELAIS:
        return {"kanalen": [None] * RELAIS_KANALEN}
    if module.type == TYPE_ROLLUIK:
        return {
            "kanalen": [{"beweging": None, "timer": False, "laatste": None} for _ in range(ROLLUIK_KANALEN)],
            "laatste": None,  # de laatste terugmelding van de module, voor de statussensor
        }
    return {"ingangen": [None] * INGANG_MAX, "leds": [None] * LEDS_STANDAARD}


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


class PehaHub:
    """Eén PHC-installatie: twee poorten, de modules en hun stand."""

    def __init__(
        self,
        naam: str,
        modules: list[Module],
        stm: Any,
        bus: Any,
        notify: NotifyFn,
        *,
        stm_pauze: float = STM_PAUZE,
        noodstop_marge: float = NOODSTOP_MARGE,
    ) -> None:
        self.naam = naam
        self.modules: dict[int, Module] = {m.adres: m for m in modules}
        self.state: dict[int, dict[str, Any]] = {m.adres: _lege_stand(m) for m in modules}
        self.stm_ok = False
        self.bus_ok = False
        self.laatste_busregel = ""
        self.laatste_commando = ""
        self.laatste_stm_antwoord = ""
        self._stm = stm
        self._bus = bus
        self._notify = notify
        self._stm_pauze = stm_pauze
        self._noodstop_marge = noodstop_marge
        self._parser = BusParser()
        self._lock = asyncio.Lock()
        self._laatst_verstuurd = 0.0
        self._taken: set[asyncio.Task] = set()
        self._noodstoppen: dict[tuple[int, int], asyncio.TimerHandle] = {}

    # ----- levenscyclus -------------------------------------------------------

    async def start(self) -> None:
        if self._stm is self._bus:  # testmodus: één nep-verbinding, dus altijd verbonden
            self._zet_stm(True)
            self._zet_bus(True)
        else:
            self._start_taak(self._lees_stm())
        self._start_taak(self._lees_bus())

    async def stop(self) -> None:
        taken = list(self._taken)
        for taak in taken:
            taak.cancel()
        await asyncio.gather(*taken, return_exceptions=True)
        for timer in self._noodstoppen.values():
            timer.cancel()
        self._noodstoppen.clear()
        await self._stm.close()
        if self._bus is not self._stm:
            await self._bus.close()

    def _start_taak(self, coro: Any) -> None:
        taak = asyncio.create_task(coro)
        self._taken.add(taak)
        taak.add_done_callback(self._taken.discard)

    async def _lees_bus(self) -> None:
        while True:
            try:
                if not self._bus.is_open:
                    await self._bus.open()
                self._zet_bus(True)
                data = await asyncio.wait_for(self._bus.read(), timeout=IDLE_RESET)
            except TimeoutError:
                self._parser.reset()  # stilte: een halfgelezen frame is niet meer te redden
                continue
            except OSError as err:
                _LOGGER.warning("Bus-poort: %s. Nieuwe poging over %s s", err, HERVERBIND_NA)
                self._zet_bus(False)
                await self._bus.close()
                await asyncio.sleep(HERVERBIND_NA)
                continue
            self.verwerk_busbytes(data)

    async def _lees_stm(self) -> None:
        """De STM stuurt soms zelf iets terug. Dat lezen we uit, zodat de buffer niet vol loopt."""
        while True:
            try:
                if not self._stm.is_open:
                    await self._stm.open()
                self._zet_stm(True)
                data = await self._stm.read()
            except OSError as err:
                _LOGGER.warning("STM-poort: %s. Nieuwe poging over %s s", err, HERVERBIND_NA)
                self._zet_stm(False)
                await self._stm.close()
                await asyncio.sleep(HERVERBIND_NA)
                continue
            self.laatste_stm_antwoord = _hex(data)[:255]
            self._notify("hub", None)

    def _zet_bus(self, waarde: bool) -> None:
        if self.bus_ok != waarde:
            self.bus_ok = waarde
            self._notify("conn", None)

    def _zet_stm(self, waarde: bool) -> None:
        if self.stm_ok != waarde:
            self.stm_ok = waarde
            self._notify("conn", None)

    def _zet_busregel(self, tekst: str) -> None:
        self.laatste_busregel = tekst
        self._notify("hub", None)

    # ----- busberichten ontvangen ---------------------------------------------

    def verwerk_busbytes(self, data: bytes) -> None:
        for frame in self._parser.feed(data):
            self.verwerk_frame(frame)

    def verwerk_frame(self, frame: BusFrame) -> None:
        module = self.modules.get(frame.adres)
        if module is None:
            beschrijving = (
                f"onbekend adres {frame.adres:02X} (mod {frame.adres & 0x1F:02d}): "
                f"payload {_hex(frame.payload)}"
            )
        else:
            beschrijving = self._verwerk_module(module, frame)
        self._zet_busregel(f"{beschrijving}  -> {_hex(frame.raw)}")

    def _verwerk_module(self, module: Module, frame: BusFrame) -> str:
        naam = module.weergavenaam
        if module.type == TYPE_RELAIS:
            byte = relais_status(frame.payload)
            if byte is None:
                return f"{naam}: onbekend bericht {_hex(frame.payload)}"
            stand = [bool(byte >> k & 1) for k in range(RELAIS_KANALEN)]
            self.state[module.adres]["kanalen"] = stand
            self._notify("module", module.adres)
            aan = [str(k) for k, s in enumerate(stand) if s]
            return f"{naam}: kanalen aan [{', '.join(aan) or 'geen'}]"

        if module.type == TYPE_ROLLUIK:
            gebeurtenis = rolluik_gebeurtenis(frame.payload)
            if gebeurtenis is None:
                return f"{naam}: onbekend bericht {_hex(frame.payload)}"
            kanaal, soort = gebeurtenis
            self._verwerk_rolluik(module.adres, kanaal, soort)
            self._notify("module", module.adres)
            return f"{naam} kanaal {kanaal}: {ROLLUIK_TEKST[soort]}"

        ingang = ingang_status(frame.payload)
        if ingang is None:
            return f"{naam}: onbekend bericht {_hex(frame.payload)}"
        ingangen, leds, _aantal_leds = ingang
        self._verwerk_ingang(module, ingangen, leds)
        self._notify("module", module.adres)
        actief = [str(k) for k, s in enumerate(self.state[module.adres]["ingangen"]) if s]
        return f"{naam}: ingangen aan [{', '.join(actief) or 'geen'}]"

    def _verwerk_rolluik(self, adres: int, kanaal: int, soort: str) -> None:
        """Een terugmelding van de JRM. Die zet alleen de beweging, nooit een eindstand.

        We weten niet waar het rolluik precies staat, dus 'klaar omlaag' betekent alleen 'gestopt'.
        Zo blijven de knoppen in Home Assistant altijd bruikbaar.
        """
        stand = self.state[adres]
        kan = stand["kanalen"][kanaal]
        tekst = ROLLUIK_STATUS_TEKST[soort]
        kan["laatste"] = tekst
        stand["laatste"] = f"kanaal {kanaal}: {tekst}"
        if soort == "start_omlaag":
            kan["beweging"] = "omlaag"
        elif soort in ("klaar_omhoog", "klaar_omlaag", "timer_afgelopen"):
            kan["beweging"] = None
            if soort == "timer_afgelopen":
                kan["timer"] = False
            self._annuleer_noodstop(adres, kanaal)
        elif soort == "timer_gestart":
            kan["timer"] = True
        elif soort == "timer_geannuleerd":
            kan["timer"] = False

    def _verwerk_ingang(self, module: Module, ingangen: int, leds: int) -> None:
        stand = self.state[module.adres]
        oud = stand["ingangen"]
        nieuw = [bool(ingangen >> k & 1) for k in range(INGANG_MAX)]
        for k in range(INGANG_MAX):
            if oud[k] is not None and oud[k] != nieuw[k]:
                self._notify("event", {
                    "peha": self.naam,
                    "module": module.nummer,
                    "adres": module.adres,
                    "ingang": k,
                    "actief": nieuw[k],
                })
        stand["ingangen"] = nieuw
        stand["leds"] = [bool(leds >> k & 1) for k in range(LEDS_STANDAARD)]

    # ----- commando's versturen -----------------------------------------------

    async def relais_commando(self, adres: int, kanaal: int, actie: str, tijd: float | None = None) -> None:
        module = self._module(adres, TYPE_RELAIS)
        try:
            payload = relais_payload(kanaal, actie, tijd)
        except ValueError as err:
            raise PehaError(str(err)) from err
        await self._stuur(adres, payload, f"{module.weergavenaam} kanaal {kanaal}: {actie}")
        stand = self.state[adres]["kanalen"]
        if actie == "omschakelen":
            stand[kanaal] = None if stand[kanaal] is None else not stand[kanaal]
        elif actie in _OPTIMISTISCH:
            stand[kanaal] = _OPTIMISTISCH[actie]
        self._notify("module", adres)

    async def rolluik_commando(
        self,
        adres: int,
        kanaal: int,
        actie: str,
        tijd: float = 0.0,
        prioriteit: int = DEFAULT_PRIORITEIT,
    ) -> None:
        module = self._module(adres, TYPE_ROLLUIK)
        try:
            payload = rolluik_payload(kanaal, actie, tijd, prioriteit)
        except ValueError as err:
            raise PehaError(str(err)) from err
        # Bewust geen controle op de huidige stand. Een tweede druk op omlaag stuurt altijd het
        # commando, ook als de integratie denkt dat het rolluik al beweegt of al dicht is.
        await self._stuur(adres, payload, f"{module.weergavenaam} kanaal {kanaal}: {actie}")
        kan = self.state[adres]["kanalen"][kanaal]
        if actie in _OMHOOG or actie in _OMLAAG:
            kan["beweging"] = "omhoog" if actie in _OMHOOG else "omlaag"
            self._plan_noodstop(adres, kanaal, tijd)
        elif actie == "stop":
            kan["beweging"] = None
            self._annuleer_noodstop(adres, kanaal)
        self._notify("module", adres)

    async def vraag_status(self, adres: int) -> None:
        module = self.modules.get(adres)
        if module is None:
            raise PehaError(f"geen module geconfigureerd op adres {adres:02X}")
        await self._stuur(adres, STATUS_VERZOEK, f"status {module.weergavenaam}")

    async def vraag_status_alles(self) -> None:
        for adres in list(self.modules):
            try:
                await self.vraag_status(adres)
            except PehaError as err:
                _LOGGER.warning("Statusopvraag mislukt: %s", err)

    async def stuur_ruw(self, adres: int, payload: bytes) -> None:
        await self._stuur(adres, payload, f"ruw commando naar {adres:02X}")

    async def _stuur(self, adres: int, payload: bytes, omschrijving: str) -> None:
        try:
            frame = stm_frame(adres, payload)
        except ValueError as err:
            raise PehaError(str(err)) from err
        async with self._lock:  # één commando tegelijk, met een pauze ertussen
            wacht = self._laatst_verstuurd + self._stm_pauze - time.monotonic()
            if wacht > 0:
                await asyncio.sleep(wacht)
            try:
                if not self._stm.is_open:
                    await self._stm.open()
                await self._stm.write(frame)
            except OSError as err:
                self._zet_stm(False)
                raise PehaError(f"usbkabel (STM) niet bereikbaar: {err}") from err
            self._laatst_verstuurd = time.monotonic()
        self._zet_stm(True)
        self.laatste_commando = f"{omschrijving} -> {_hex(frame)}"
        self._notify("hub", None)

    # ----- hulpfuncties -------------------------------------------------------

    def _module(self, adres: int, soort: str) -> Module:
        module = self.modules.get(adres)
        if module is None:
            raise PehaError(f"geen module geconfigureerd op adres {adres:02X}")
        if module.type != soort:
            raise PehaError(f"adres {adres:02X} is geen {TYPE_NAMEN[soort].lower()}")
        return module

    def _plan_noodstop(self, adres: int, kanaal: int, tijd: float) -> None:
        """Na looptijd + marge zetten we alleen de weergave op stil, als er geen terugmelding kwam.

        Het commando zelf wordt er niet door geblokkeerd.
        """
        self._annuleer_noodstop(adres, kanaal)
        if tijd and tijd > 0:
            loop = asyncio.get_running_loop()
            self._noodstoppen[(adres, kanaal)] = loop.call_later(
                tijd + self._noodstop_marge, self._noodstop, adres, kanaal
            )

    def _annuleer_noodstop(self, adres: int, kanaal: int) -> None:
        timer = self._noodstoppen.pop((adres, kanaal), None)
        if timer is not None:
            timer.cancel()

    def _noodstop(self, adres: int, kanaal: int) -> None:
        self._noodstoppen.pop((adres, kanaal), None)
        kan = self.state[adres]["kanalen"][kanaal]
        if kan["beweging"] is not None:
            kan["beweging"] = None
            self._notify("module", adres)
