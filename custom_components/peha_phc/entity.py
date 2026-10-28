# entity.py - Peha PHC versie 0.1.2
"""Basisklassen voor de entiteiten van Peha PHC."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SW_VERSION
from .hub import PhcHub
from .models import PhcModule


def hub_device_info(entry_id: str) -> DeviceInfo:
    """Het apparaat 'Peha PHC' met de poortschakelaars en de logsensoren."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Peha PHC",
        manufacturer="Peha",
        model="USB-kabel (STM) + RS485-busdongle",
        sw_version=SW_VERSION,
    )


class PhcHubEntity(Entity):
    """Entiteit die wordt bijgewerkt zodra de hub iets verandert."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, hub: PhcHub, unique_id: str, name: str | None) -> None:
        self._hub = hub
        self._attr_unique_id = unique_id
        # Entity-id blijft het PHC-nummer bevatten, bijvoorbeeld switch.peha_amd_00_kanaal0
        self._attr_suggested_object_id = unique_id
        self._attr_name = name

    @property
    def available(self) -> bool:
        return self._hub.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._hub.signal, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class PhcHubAltijdBeschikbaar(PhcHubEntity):
    """Hub-entiteit die beschikbaar blijft, ook als een poort gesloten is.

    Anders kun je een gesloten poort niet meer met de schakelaar weer openen.
    """

    @property
    def available(self) -> bool:
        return True


class PhcModuleEntity(PhcHubEntity):
    """Entiteit die bij een module hoort en op het apparaat van die module staat."""

    def __init__(self, hub: PhcHub, module: PhcModule, key: str, name: str | None) -> None:
        super().__init__(hub, f"peha_{module.code}_{module.phc:02d}_{key}", name)
        self._module = module
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, module.device_id)},
            name=module.name,
            manufacturer="Peha",
            model=module.model,
            sw_version=SW_VERSION,
        )
