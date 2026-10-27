"""Looptijd per rolluikkanaal: 4 schuifregelaars van 3 tot 180 seconden."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import AANTAL_ROLLUIKEN, DOMAIN, MAX_LOOPTIJD, MIN_LOOPTIJD, MODULE_ROLLUIK
from .entity import PhcModuleEntity
from .hub import PhcHub


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PhcHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PhcLooptijd(hub, module, channel)
        for module in hub.modules_of(MODULE_ROLLUIK)
        for channel in range(AANTAL_ROLLUIKEN)
    )


class PhcLooptijd(PhcModuleEntity, NumberEntity, RestoreEntity):
    _attr_native_min_value = MIN_LOOPTIJD
    _attr_native_max_value = MAX_LOOPTIJD
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, hub: PhcHub, module, channel: int) -> None:
        super().__init__(hub, module, f"looptijd{channel}", f"Looptijd kanaal {channel}")
        self._channel = channel

    @property
    def native_value(self) -> float:
        return self._module.runtimes[self._channel]

    async def async_set_native_value(self, value: float) -> None:
        self._module.runtimes[self._channel] = float(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._module.runtimes[self._channel] = float(last.state)
            except ValueError:
                pass
