# switch.py - Peha PHC versie 0.1.1
"""Schakelaars: de twee poorten (standaard aan) en de relais (8 kanalen per module)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import AANTAL_RELAIS, DOMAIN, MODULE_RELAIS
from .entity import PhcHubAltijdBeschikbaar, PhcModuleEntity, hub_device_info
from .hub import PhcHub

POORTEN = {"stm": "USB-kabel (STM)", "bus": "busdongle (RS485)"}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [PhcPoortSchakelaar(hub, which) for which in POORTEN]
    for module in hub.modules_of(MODULE_RELAIS):
        for channel in range(AANTAL_RELAIS):
            entities.append(PhcRelaisSchakelaar(hub, module, channel))
    async_add_entities(entities)


class PhcPoortSchakelaar(PhcHubAltijdBeschikbaar, SwitchEntity, RestoreEntity):
    """Aan: de poort is open. Uit: de poort wordt echt gesloten, zodat een ander programma hem kan gebruiken.

    Standaard aan. De stand blijft bewaard na een herstart.
    """

    _attr_icon = "mdi:usb-port"

    def __init__(self, hub: PhcHub, which: str) -> None:
        super().__init__(hub, f"peha_poort_{which}", f"Poort {POORTEN[which]}")
        self._which = which
        self._attr_device_info = hub_device_info(hub.entry_id)

    @property
    def is_on(self) -> bool:
        return self._hub.enabled[self._which]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        gewenst = not (last is not None and last.state == "off")
        if gewenst != self._hub.enabled[self._which]:
            await self._hub.async_set_enabled(self._which, gewenst)

    async def async_turn_on(self, **kwargs) -> None:
        await self._hub.async_set_enabled(self._which, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._hub.async_set_enabled(self._which, False)


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
