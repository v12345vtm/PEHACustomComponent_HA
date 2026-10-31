# sensor.py - Peha PHC versie 0.1.5
"""Sensoren: module-status, laatste bus-data, rolluikstatus per kanaal en de twee logsensoren."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import AANTAL_INGANGEN, AANTAL_ROLLUIKEN, DOMAIN, MODULE_INGANG, MODULE_ROLLUIK
from .entity import PhcHubAltijdBeschikbaar, PhcModuleEntity, hub_device_info
from .hub import PhcHub
from .protocol import IMD_SIMPLE_NAMEN


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [PhcLogSensor(hub, "verstuurd"), PhcLogSensor(hub, "verwerkt")]
    for module in hub.modules.values():
        entities.append(PhcStatusSensor(hub, module))
        entities.append(PhcLaatsteBericht(hub, module))
        if module.kind == MODULE_ROLLUIK:
            for channel in range(AANTAL_ROLLUIKEN):
                entities.append(PhcRolluikStatus(hub, module, channel))
        if module.kind == MODULE_INGANG:
            entities.append(PhcLaatsteEvent(hub, module))
            for knop in range(AANTAL_INGANGEN):
                entities.append(PhcKnopEvent(hub, module, knop))
    async_add_entities(entities)


class PhcStatusSensor(PhcModuleEntity, SensorEntity):
    """Relais: 00000000 (positie = kanaal). Ingang: ingangen,LEDs. Rolluik: status per kanaal."""

    _attr_icon = "mdi:format-list-bulleted-square"

    def __init__(self, hub: PhcHub, module) -> None:
        super().__init__(hub, module, "status", "Status")

    @property
    def native_value(self) -> str | None:
        return self._module.status_text()


class PhcLaatsteBericht(PhcModuleEntity, SensorEntity):
    """Het laatste bericht dat de parser voor deze module heeft verwerkt."""

    _attr_icon = "mdi:console-line"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: PhcHub, module) -> None:
        super().__init__(hub, module, "laatste_bericht", "Laatste bus-data")

    @property
    def native_value(self) -> str:
        return self._module.last_text[:255]

    @property
    def extra_state_attributes(self) -> dict:
        return {"hex": self._module.last_hex, "tijd": self._module.last_time}


class PhcRolluikStatus(PhcModuleEntity, SensorEntity, RestoreEntity):
    """Echte status van een rolluikkanaal: open, closed, halted, opening, closing of unknown.

    Na een herstart van Home Assistant wordt de laatst bekende status hersteld.
    """

    _attr_icon = "mdi:window-shutter"

    def __init__(self, hub: PhcHub, module, channel: int) -> None:
        super().__init__(hub, module, f"kanaal{channel}_status", f"Kanaal {channel} status")
        self._channel = channel

    @property
    def _cover(self):
        return self._module.covers[self._channel]

    @property
    def native_value(self) -> str:
        return self._cover.status

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        cover = self._cover
        if last is None or cover.moving or cover.closed is not None or cover.halted:
            return  # er is al een live status binnengekomen
        if last.state == "closed":
            cover.closed = True
        elif last.state == "open":
            cover.closed = False
        elif last.state == "halted":
            cover.closed = False
            cover.halted = True


class PhcLogSensor(PhcHubAltijdBeschikbaar, SensorEntity):
    """Logsensor. De state is het laatste pakket; de volledige lijst staat in het attribuut 'pakketten'."""

    _attr_icon = "mdi:console-line"
    _unrecorded_attributes = frozenset({"pakketten", "tekst"})

    def __init__(self, hub: PhcHub, which: str) -> None:
        if which == "verstuurd":
            super().__init__(hub, "peha_log_verstuurd", "Verstuurde pakketten (USB-kabel)")
            self._log = hub.log_verstuurd
        else:
            super().__init__(hub, "peha_log_verwerkt", "Verwerkte bus-pakketten")
            self._log = hub.log_verwerkt
        self._which = which
        self._attr_device_info = hub_device_info(hub.entry_id)

    @property
    def native_value(self) -> str:
        if not self._log:
            return "nog geen pakketten"
        laatste = self._log[-1]
        tekst = laatste["hex"] if self._which == "verstuurd" else laatste["betekenis"]
        return tekst[:255]

    @property
    def extra_state_attributes(self) -> dict:
        pakketten = [dict(regel) for regel in self._log]
        if self._which == "verstuurd":
            regels = [f"{r['tijd']}  {r['hex']}  ({r['betekenis']})" for r in self._log]
        else:
            regels = [f"{r['tijd']}  {r['betekenis']}" for r in self._log]
        return {"pakketten": pakketten, "tekst": "\n".join(regels)}


class PhcLaatsteEvent(PhcModuleEntity, SensorEntity):
    """Vereenvoudigd event van de laatste knopactie, zoals 01.12.2 (module 01, knop 12, event 2).

    Met één waarde kies je in een automatisering de juiste knop en het juiste event.
    """

    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, hub: PhcHub, module) -> None:
        super().__init__(hub, module, "laatste_event", "Laatste knop-event")

    @property
    def native_value(self) -> str | None:
        return self._module.laatste_tekst()

    @property
    def extra_state_attributes(self) -> dict:
        if self._module.laatste_event is None:
            return {}
        knop, code, actie = self._module.laatste_event
        return {
            "knop": knop,
            "code": code,
            "naam": IMD_SIMPLE_NAMEN.get(code),
            "actie": actie,
            "tijd": self._module.laatste_event_tijd,
        }


class PhcKnopEvent(PhcModuleEntity, SensorEntity):
    """Numerieke status van het laatste event van één knop (Event 00 t/m Event 15).

    Diagnose: standaard uitgeschakeld. Zet hem aan via de entiteitsinstellingen.
    """

    _attr_icon = "mdi:numeric"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, hub: PhcHub, module, knop: int) -> None:
        super().__init__(hub, module, f"event{knop:02d}", f"Event {knop:02d}")
        self._knop = knop

    @property
    def native_value(self) -> int | None:
        return self._module.knop_code[self._knop]
