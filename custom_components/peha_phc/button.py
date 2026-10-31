# button.py - Peha PHC versie 0.1.5
"""Knoppen: status opvragen, rolluik omhoog/omlaag en virtuele ingangen (klik)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AANTAL_ROLLUIKEN,
    CONF_ETHERNET,
    CONF_IP,
    CONF_STM,
    CONF_FUNCTIE,
    CONF_KANAAL,
    CONF_NAAM,
    CONF_PHC,
    DOMAIN,
    MODULE_INGANG,
    MODULE_ROLLUIK,
    SW_VERSION,
    ethernet_device_id,
    module_address,
    virtual_device_id,
)
from .entity import PhcHubAltijdBeschikbaar, PhcHubEntity, PhcModuleEntity
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []
    for module in hub.modules.values():
        entities.append(PhcStatusKnop(hub, module))
        if module.kind == MODULE_ROLLUIK:
            for channel in range(AANTAL_ROLLUIKEN):
                entities.append(PhcRolluikKnop(hub, module, channel, "omhoog"))
                entities.append(PhcRolluikKnop(hub, module, channel, "omlaag"))
    entities += [PhcVirtueleKnop(hub, cfg) for cfg in hub.virtual_buttons]
    entities += [PhcEthernetKnop(hub, cfg) for cfg in hub.ethernet_knoppen]
    async_add_entities(entities)


class PhcStatusKnop(PhcModuleEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, hub: PhcHub, module) -> None:
        super().__init__(hub, module, "status_opvragen", "Status opvragen")

    async def async_press(self) -> None:
        await self._hub.async_request_status(self._module.address)


class PhcRolluikKnop(PhcModuleEntity, ButtonEntity):
    """Vaste omhoog- of omlaagknop. Stuurt altijd een commando, ook tijdens een beweging."""

    def __init__(self, hub: PhcHub, module, channel: int, action: str) -> None:
        super().__init__(hub, module, f"kanaal{channel}_{action}", f"Kanaal {channel} {action}")
        self._channel = channel
        self._action = action
        self._attr_icon = "mdi:arrow-up-bold" if action == "omhoog" else "mdi:arrow-down-bold"

    async def async_press(self) -> None:
        await self._hub.async_cover(self._module, self._channel, self._action)


class PhcVirtueleKnop(PhcHubEntity, ButtonEntity):
    """Klik op een virtuele ingang: één commando, zoals de Node-RED IMD GENERATOR."""

    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, hub: PhcHub, cfg: dict) -> None:
        super().__init__(hub, f"peha_VIRT_{cfg[CONF_PHC]:02d}_{cfg[CONF_KANAAL]:02d}_{cfg[CONF_FUNCTIE]}", None)
        self._cfg = cfg
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, virtual_device_id(cfg))},
            name=cfg[CONF_NAAM],
            manufacturer="Peha",
            model=f"Virtuele ingang (adres 0x{module_address(MODULE_INGANG, cfg[CONF_PHC]):02X}, "
                  f"kanaal {cfg[CONF_KANAAL]})",
            sw_version=SW_VERSION,
        )

    async def async_press(self) -> None:
        await self._hub.async_virtual_click(
            module_address(MODULE_INGANG, self._cfg[CONF_PHC]),
            self._cfg[CONF_KANAAL],
            self._cfg[CONF_FUNCTIE],
        )


class PhcEthernetKnop(PhcHubAltijdBeschikbaar, ButtonEntity):
    """Knop die via de ethernetmodule een functie van een ingangsmodule stuurt. Eén opdracht per druk."""

    _attr_icon = "mdi:ethernet"

    def __init__(self, hub: PhcHub, cfg: dict) -> None:
        ip = cfg[CONF_ETHERNET]
        super().__init__(
            hub,
            f"peha_ETH_{ip.replace('.', '_')}_{cfg[CONF_PHC]:02d}_{cfg[CONF_KANAAL]:02d}_{cfg[CONF_FUNCTIE]}",
            cfg[CONF_NAAM],
        )
        self._cfg = cfg
        naam = next((m[CONF_NAAM] for m in hub.ethernet_modules if m[CONF_IP] == ip), ip)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ethernet_device_id(ip))},
            name=naam,
            manufacturer="Peha",
            model=f"Ethernetmodule ({ip})",
            sw_version=SW_VERSION,
        )

    async def async_press(self) -> None:
        ip = self._cfg[CONF_ETHERNET]
        module = next((m for m in self._hub.ethernet_modules if m[CONF_IP] == ip), None)
        if module is None:
            raise HomeAssistantError(f"Ethernetmodule {ip} staat niet in de configuratie")
        await self._hub.async_ethernet_knop(
            ip,
            module.get(CONF_STM, 0),
            self._cfg[CONF_PHC],
            self._cfg[CONF_KANAAL],
            self._cfg[CONF_FUNCTIE],
        )