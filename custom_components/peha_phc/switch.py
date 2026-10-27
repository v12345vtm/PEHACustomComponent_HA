"""Relais (AMD): 8 schakelaars per module."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AANTAL_RELAIS, DOMAIN, MODULE_RELAIS
from .entity import PhcModuleEntity
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PhcRelaisSchakelaar(hub, module, channel)
        for module in hub.modules_of(MODULE_RELAIS)
        for channel in range(AANTAL_RELAIS)
    )


class PhcRelaisSchakelaar(PhcModuleEntity, SwitchEntity):
    def __init__(self, hub: PhcHub, module, channel: int) -> None:
        super().__init__(hub, module, f"kanaal{channel}", f"Kanaal {channel}")
        self._channel = channel

    @property
    def is_on(self) -> bool | None:
        return self._module.relays[self._channel]

    async def async_turn_on(self, **kwargs) -> None:
        await self._hub.async_relay(self._module, self._channel, "aan")

    async def async_turn_off(self, **kwargs) -> None:
        await self._hub.async_relay(self._module, self._channel, "uit")
