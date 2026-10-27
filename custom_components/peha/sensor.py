# Peha PHC-integratie, versie 1.1.0
"""Sensoren.

Per module één statussensor, zoals de bus die meldt:
- Relais: 8 tekens, kanaal 0 eerst. 10010000 betekent kanaal 0 en 3 aan.
- Ingangen: 16 tekens voor de ingangen, een komma, 16 tekens voor de LED's.
- Rolluik: de laatste terugmelding van de module, bijvoorbeeld 'kanaal 2: omlaag gegaan'.
Een '?' betekent dat die waarde nog niet bekend is.

Per installatie komen er drie diagnostische tekstsensoren bij.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PehaConfigEntry
from .const import TYPE_INGANG, TYPE_RELAIS
from .entity import PehaEntity
from .hub import PehaHub
from .model import Module


def _bits(waarden: list[bool | None]) -> str:
    return "".join("1" if w is True else "0" if w is False else "?" for w in waarden)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PehaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    entities: list[SensorEntity] = [
        PehaTekstSensor(entry, hub, "bus", "Laatste busbericht"),
        PehaTekstSensor(entry, hub, "commando", "Laatste STM-commando"),
        PehaTekstSensor(entry, hub, "stm_antwoord", "Laatste STM-antwoord"),
    ]
    entities += [PehaModuleStatusSensor(entry, hub, module) for module in hub.modules.values()]
    async_add_entities(entities)


class PehaModuleStatusSensor(PehaEntity, SensorEntity):
    """De stand van één module. Hangt aan het apparaat van die module."""

    _attr_name = "Status"
    _attr_icon = "mdi:information-outline"

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, module: Module) -> None:
        super().__init__(entry, hub, module, f"{entry.entry_id}_{module.adres:02x}_toestand")

    @property
    def available(self) -> bool:
        return self._hub.bus_ok  # de stand komt van de bus, niet van de usbkabel

    @property
    def _stand(self) -> dict[str, Any]:
        return self._hub.state[self._module.adres]

    @property
    def native_value(self) -> str | None:
        stand = self._stand
        if self._module.type == TYPE_RELAIS:
            kanalen = stand["kanalen"]
            return None if all(k is None for k in kanalen) else _bits(kanalen)
        if self._module.type == TYPE_INGANG:
            if all(i is None for i in stand["ingangen"]):
                return None
            return f"{_bits(stand['ingangen'])},{_bits(stand['leds'])}"
        return stand["laatste"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stand = self._stand
        if self._module.type == TYPE_RELAIS:
            return {"kanalen_aan": [k for k, s in enumerate(stand["kanalen"]) if s is True]}
        if self._module.type == TYPE_INGANG:
            return {
                "ingangen_aan": [k for k, s in enumerate(stand["ingangen"]) if s is True],
                "leds_aan": [k for k, s in enumerate(stand["leds"]) if s is True],
            }
        return {"kanalen": {f"kanaal {k}": kan["laatste"] for k, kan in enumerate(stand["kanalen"])}}


class PehaTekstSensor(PehaEntity, SensorEntity):
    """Diagnostische tekst: het laatste busbericht, het laatste STM-commando en het STM-antwoord."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:message-text-outline"

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, soort: str, naam: str) -> None:
        super().__init__(entry, hub, None, f"{entry.entry_id}_{soort}")
        self._soort = soort
        self._attr_name = naam

    def _tekst(self) -> str:
        if self._soort == "bus":
            return self._hub.laatste_busregel
        if self._soort == "commando":
            return self._hub.laatste_commando
        return self._hub.laatste_stm_antwoord

    @property
    def native_value(self) -> str:
        return self._tekst()[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"volledig": self._tekst()}
