# Peha PHC-integratie, versie 1.1.0
"""Eén cover per rolluikkanaal. Omhoog, stop en omlaag gaan altijd naar de module.

De module meldt geen positie. Daarom meldt de cover nooit 'open' of 'dicht': dat zou in Home
Assistant de bijbehorende knop uitschakelen. De cover toont alleen 'aan het openen', 'aan het
sluiten' of 'onbekend'. Een tweede druk op omlaag stuurt dus altijd het commando.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PehaConfigEntry
from .const import ROLLUIK_KANALEN, TYPE_ROLLUIK
from .entity import PehaEntity, uitvoeren
from .hub import PehaHub
from .model import Module


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PehaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    async_add_entities([
        PehaRolluikCover(entry, hub, module, kanaal)
        for module in hub.modules.values()
        if module.type == TYPE_ROLLUIK
        for kanaal in range(ROLLUIK_KANALEN)
    ])


class PehaRolluikCover(PehaEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    _attr_assumed_state = True  # de stand is afgeleid van commando's en terugmeldingen, niet gemeten

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, module: Module, kanaal: int) -> None:
        super().__init__(entry, hub, module, f"{entry.entry_id}_{module.adres:02x}_rolluik_{kanaal}")
        self._kanaal = kanaal
        self._attr_name = f"Kanaal {kanaal}"

    @property
    def _stand(self) -> dict[str, Any]:
        return self._hub.state[self._module.adres]["kanalen"][self._kanaal]

    @property
    def is_closed(self) -> bool | None:
        # Bewust altijd onbekend. Zie de toelichting bovenaan.
        return None

    @property
    def is_opening(self) -> bool:
        return self._stand["beweging"] == "omhoog"

    @property
    def is_closing(self) -> bool:
        return self._stand["beweging"] == "omlaag"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "laatste_terugmelding": self._stand["laatste"],
            "timer_actief": self._stand["timer"],
            "looptijd_s": self._module.looptijd(self._kanaal),
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        await uitvoeren(self._hub.rolluik_commando(
            self._module.adres, self._kanaal, "omhoog", tijd=self._module.looptijd(self._kanaal),
        ))

    async def async_close_cover(self, **kwargs: Any) -> None:
        await uitvoeren(self._hub.rolluik_commando(
            self._module.adres, self._kanaal, "omlaag", tijd=self._module.looptijd(self._kanaal),
        ))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await uitvoeren(self._hub.rolluik_commando(self._module.adres, self._kanaal, "stop"))
