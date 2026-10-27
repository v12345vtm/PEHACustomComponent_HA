# Peha PHC-integratie, versie 1.1.0
"""Binary sensors: de ingangen (knoppen), de LED-stand, en de verbinding met de bus en de STM."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PehaConfigEntry
from .const import TYPE_INGANG
from .entity import PehaEntity
from .hub import PehaHub
from .model import Module


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PehaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        PehaVerbindingSensor(entry, hub, "bus", "Bus verbonden"),
        PehaVerbindingSensor(entry, hub, "stm", "Usbkabel (STM) verbonden"),
    ]
    for module in hub.modules.values():
        if module.type == TYPE_INGANG:
            for nummer in range(module.kanalen):
                entities.append(PehaIngangSensor(entry, hub, module, nummer))
                entities.append(PehaLedSensor(entry, hub, module, nummer))
    async_add_entities(entities)


class PehaVerbindingSensor(PehaEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, soort: str, naam: str) -> None:
        super().__init__(entry, hub, None, f"{entry.entry_id}_{soort}_verbonden")
        self._soort = soort
        self._attr_name = naam

    @property
    def available(self) -> bool:
        return True  # een verbindingssensor is altijd beschikbaar, ook als de verbinding weg is

    @property
    def is_on(self) -> bool:
        return self._hub.bus_ok if self._soort == "bus" else self._hub.stm_ok


class PehaIngangSensor(PehaEntity, BinarySensorEntity):
    """Aan betekent: bit 1 op de bus voor deze ingang (de knop is actief)."""

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, module: Module, nummer: int) -> None:
        super().__init__(entry, hub, module, f"{entry.entry_id}_{module.adres:02x}_ingang_{nummer}")
        self._nummer = nummer
        self._attr_name = f"Ingang {nummer}"

    @property
    def available(self) -> bool:
        return self._hub.bus_ok  # ingangen komen van de bus, niet van de usbkabel

    @property
    def is_on(self) -> bool | None:
        return self._hub.state[self._module.adres]["ingangen"][self._nummer]


class PehaLedSensor(PehaEntity, BinarySensorEntity):
    """De LED-stand van de ingangsmodule. Standaard uitgeschakeld; zet hem aan in de entiteitsinstellingen."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: PehaConfigEntry, hub: PehaHub, module: Module, nummer: int) -> None:
        super().__init__(entry, hub, module, f"{entry.entry_id}_{module.adres:02x}_led_{nummer}")
        self._nummer = nummer
        self._attr_name = f"LED {nummer}"

    @property
    def available(self) -> bool:
        return self._hub.bus_ok

    @property
    def is_on(self) -> bool | None:
        return self._hub.state[self._module.adres]["leds"][self._nummer]
