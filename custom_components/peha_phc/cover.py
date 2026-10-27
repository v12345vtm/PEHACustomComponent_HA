"""Rolluiken (JRM): 4 kanalen per module met open, dicht en stop."""
from __future__ import annotations

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import AANTAL_ROLLUIKEN, DOMAIN, MODULE_ROLLUIK
from .entity import PhcModuleEntity
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PhcRolluik(hub, module, channel)
        for module in hub.modules_of(MODULE_ROLLUIK)
        for channel in range(AANTAL_ROLLUIKEN)
    )


class PhcRolluik(PhcModuleEntity, CoverEntity, RestoreEntity):
    """Geen positie: de module meldt alleen 'klaar' of 'gestopt'.

    Commando's worden altijd verstuurd, ook tijdens een beweging.
    """

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, hub: PhcHub, module, channel: int) -> None:
        super().__init__(hub, module, f"kanaal{channel}", f"Kanaal {channel}")
        self._channel = channel

    async def async_added_to_hass(self) -> None:
        """Herstelt de laatst bekende positie na een herstart van Home Assistant."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and self._cover.closed is None:
            if last.state == "closed":
                self._cover.closed = True
            elif last.state == "open":
                self._cover.closed = False

    @property
    def _cover(self):
        return self._module.covers[self._channel]

    @property
    def is_opening(self) -> bool:
        return self._cover.moving == "omhoog"

    @property
    def is_closing(self) -> bool:
        return self._cover.moving == "omlaag"

    @property
    def is_closed(self) -> bool | None:
        return self._cover.closed

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "status": self._cover.status,
            "looptijd": self._module.runtimes[self._channel],
        }

    async def async_open_cover(self, **kwargs) -> None:
        await self._hub.async_cover(self._module, self._channel, "omhoog")

    async def async_close_cover(self, **kwargs) -> None:
        await self._hub.async_cover(self._module, self._channel, "omlaag")

    async def async_stop_cover(self, **kwargs) -> None:
        await self._hub.async_cover(self._module, self._channel, "stop")
