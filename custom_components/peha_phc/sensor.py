"""Sensoren per module: de status (bits) en het laatst ontvangen busbericht."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PhcModuleEntity
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for module in hub.modules.values():
        entities.append(PhcStatusSensor(hub, module))
        entities.append(PhcLaatsteBericht(hub, module))
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
    """Het laatste bericht dat de parser voor deze module heeft gedecodeerd."""

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
