# Peha PHC-integratie, versie 1.1.0
"""Eén schakelaar per relaiskanaal. Aan en uit gaan via de STM; de stand komt van de bus."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PehaConfigEntry
from .const import RELAIS_KANALEN, TYPE_RELAIS
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
        PehaRelaisSwitch(entry, hub, module, kanaal)
        for module in hub.modules.values()
        if module.type == TYPE_RELAIS
        for kanaal in range(RELAIS_KANALEN)
    ])


class PehaRelaisSwitch(PehaEntity, SwitchEntity):
    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, module: Module, kanaal: int) -> None:
        super().__init__(entry, hub, module, f"{entry.entry_id}_{module.adres:02x}_kanaal_{kanaal}")
        self._kanaal = kanaal
        self._attr_name = f"Kanaal {kanaal}"

    @property
    def is_on(self) -> bool | None:
        return self._hub.state[self._module.adres]["kanalen"][self._kanaal]

    async def async_turn_on(self, **kwargs: Any) -> None:
        await uitvoeren(self._hub.relais_commando(self._module.adres, self._kanaal, "aan"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await uitvoeren(self._hub.relais_commando(self._module.adres, self._kanaal, "uit"))
