# Peha PHC-integratie, versie 1.1.0
"""Basis voor alle entiteiten: een apparaat per module, en bijwerken via de dispatcher."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, TYPE_NAMEN, signaal
from .hub import PehaError, PehaHub
from .model import Module


async def uitvoeren(awaitable: Any) -> None:
    """Zet een fout uit de hub om in een fout die Home Assistant netjes toont."""
    try:
        await awaitable
    except PehaError as err:
        raise HomeAssistantError(str(err)) from err


def _apparaat(entry: ConfigEntry, module: Module | None) -> DeviceInfo:
    hub_id = (DOMAIN, entry.entry_id)
    if module is None:
        return DeviceInfo(
            identifiers={hub_id},
            name=entry.title,
            manufacturer="Peha",
            model="PHC-bus (usbkabel STM + RS485-dongle)",
        )
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{module.adres:02x}")},
        name=module.weergavenaam,
        manufacturer="Peha",
        model=f"{TYPE_NAMEN[module.type]} (adres 0x{module.adres:02X})",
    )


class PehaEntity(Entity):
    """Gedeelde eigenschappen. De stand komt uit de hub; deze entiteit leest die alleen."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, hub: PehaHub, module: Module | None, unique_id: str) -> None:
        self._entry_id = entry.entry_id
        self._hub = hub
        self._module = module
        self._attr_unique_id = unique_id
        self._attr_device_info = _apparaat(entry, module)

    @property
    def available(self) -> bool:
        return self._hub.stm_ok

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signaal(self._entry_id, "conn"), self._ververs)
        )
        if self._module is None:
            self.async_on_remove(
                async_dispatcher_connect(self.hass, signaal(self._entry_id, "hub"), self._ververs)
            )
        else:
            self.async_on_remove(
                async_dispatcher_connect(self.hass, signaal(self._entry_id, "module"), self._module_ververs)
            )

    @callback
    def _ververs(self, _data: Any = None) -> None:
        self.async_write_ha_state()

    @callback
    def _module_ververs(self, adres: int) -> None:
        if self._module is not None and adres == self._module.adres:
            self.async_write_ha_state()
