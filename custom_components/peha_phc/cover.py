# cover.py - Peha PHC versie 0.1.2
"""Rolluiken (JRM): cover-entiteiten die altijd bedienbaar blijven.

In rust staat de cover op onbekend, zodat Home Assistant geen knop grijs maakt. Tijdens een
beweging staat hij op opening of closing. De echte status (open, closed, halted) staat als
attribuut op de cover en in de sensor 'Kanaal N status'.
"""
from __future__ import annotations

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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


class PhcRolluik(PhcModuleEntity, CoverEntity):
    """Cover per kanaal. Commando's gaan altijd naar de module, ook tijdens een beweging."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, hub: PhcHub, module, channel: int) -> None:
        super().__init__(hub, module, f"kanaal{channel}", f"Kanaal {channel}")
        self._channel = channel

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
    def is_closed(self) -> None:
        """Altijd onbekend: in rust blijven de knoppen van Home Assistant dan aan."""
        return None

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
