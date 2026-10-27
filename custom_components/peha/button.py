# Peha PHC-integratie, versie 1.1.0
"""Knoppen: de stand van één module opvragen, of van alle modules tegelijk."""
from __future__ import annotations


from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PehaConfigEntry
from .entity import PehaEntity, uitvoeren
from .hub import PehaHub
from .model import Module


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PehaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    entities: list[ButtonEntity] = [PehaStatusAllesButton(entry, hub)]
    entities += [PehaStatusButton(entry, hub, module) for module in hub.modules.values()]
    async_add_entities(entities)


class PehaStatusAllesButton(PehaEntity, ButtonEntity):
    _attr_name = "Status alle modules opvragen"

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub) -> None:
        super().__init__(entry, hub, None, f"{entry.entry_id}_status_alles")

    async def async_press(self) -> None:
        await uitvoeren(self._hub.vraag_status_alles())


class PehaStatusButton(PehaEntity, ButtonEntity):
    _attr_name = "Status opvragen"

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, module: Module) -> None:
        super().__init__(entry, hub, module, f"{entry.entry_id}_{module.adres:02x}_status")

    async def async_press(self) -> None:
        await uitvoeren(self._hub.vraag_status(self._module.adres))
