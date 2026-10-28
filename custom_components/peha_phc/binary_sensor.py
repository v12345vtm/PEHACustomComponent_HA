# binary_sensor.py - Peha PHC versie 0.1.1
"""Ingangen (IMD): 16 binaire sensoren per ingangsmodule."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AANTAL_INGANGEN, DOMAIN, MODULE_INGANG
from .entity import PhcModuleEntity
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PhcIngang(hub, module, channel)
        for module in hub.modules_of(MODULE_INGANG)
        for channel in range(AANTAL_INGANGEN)
    )


class PhcIngang(PhcModuleEntity, BinarySensorEntity):
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, hub: PhcHub, module, channel: int) -> None:
        super().__init__(hub, module, f"ingang{channel}", f"Ingang {channel}")
        self._channel = channel

    @property
    def is_on(self) -> bool | None:
        return self._module.inputs[self._channel]
