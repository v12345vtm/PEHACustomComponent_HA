"""Knoppen: status opvragen per module, rolluik omhoog/omlaag en virtuele ingangen (klik)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AANTAL_ROLLUIKEN,
    CONF_FUNCTIE,
    CONF_KANAAL,
    CONF_NAAM,
    CONF_PHC,
    DOMAIN,
    MODULE_INGANG,
    MODULE_ROLLUIK,
    module_address,
    virtual_device_id,
)
from .entity import PhcHubEntity, PhcModuleEntity
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
    async_add_entities(entities)


class PhcStatusKnop(PhcModuleEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, hub: PhcHub, module) -> None:
        super().__init__(hub, module, "status_opvragen", "Status opvragen")

    async def async_press(self) -> None:
        await self._hub.async_request_status(self._module.address)


class PhcRolluikKnop(PhcModuleEntity, ButtonEntity):
    """Omhoog of omlaag, die altijd een commando stuurt.

    De standaard covers-bediening van Home Assistant zet de knop 'dicht' meestal uit zodra
    de cover als dicht gemeld staat. Met deze knoppen kun je altijd verder omlaag of omhoog.
    """

    def __init__(self, hub: PhcHub, module, channel: int, action: str) -> None:
        super().__init__(hub, module, f"kanaal{channel}_{action}", f"Kanaal {channel} {action}")
        self._channel = channel
        self._action = action
        self._attr_icon = "mdi:arrow-up-bold" if action == "omhoog" else "mdi:arrow-down-bold"

    async def async_press(self) -> None:
        await self._hub.async_cover(self._module, self._channel, self._action)


class PhcVirtueleKnop(PhcHubEntity, ButtonEntity):
    """Klik op een virtuele ingang: indrukken, wachten en loslaten."""

    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, hub: PhcHub, cfg: dict) -> None:
        super().__init__(hub, f"peha_VIRT_{cfg[CONF_PHC]:02d}_{cfg[CONF_KANAAL]:02d}_{cfg[CONF_FUNCTIE]}", None)
        self._cfg = cfg
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, virtual_device_id(cfg))},
            name=cfg[CONF_NAAM],
            manufacturer="Peha",
            model=f"Virtuele ingang (adres 0x{module_address(MODULE_INGANG, cfg[CONF_PHC]):02X}, kanaal {cfg[CONF_KANAAL]})",
        )

    async def async_press(self) -> None:
        await self._hub.async_virtual_click(
            module_address(MODULE_INGANG, self._cfg[CONF_PHC]),
            self._cfg[CONF_KANAAL],
            self._cfg[CONF_FUNCTIE],
        )
