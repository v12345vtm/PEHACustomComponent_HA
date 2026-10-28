# sensor.py - Peha PHC versie 0.1.1
"""Sensoren: module-status, laatste bus-data, rolluikstatus per kanaal en de twee logsensoren."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import AANTAL_ROLLUIKEN, DOMAIN, MODULE_ROLLUIK
from .entity import PhcHubAltijdBeschikbaar, PhcModuleEntity, hub_device_info
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [PhcLogSensor(hub, "verstuurd"), PhcLogSensor(hub, "verwerkt")]
    for module in hub.modules.values():
        entities.append(PhcStatusSensor(hub, module))
        entities.append(PhcLaatsteBericht(hub, module))
        if module.kind == MODULE_ROLLUIK:
            for channel in range(AANTAL_ROLLUIKEN):
                entities.append(PhcRolluikStatus(hub, module, channel))
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
