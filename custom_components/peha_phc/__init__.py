# __init__.py - Peha PHC versie 0.1.5
"""Peha PHC: koppeling met de Peha PHC-bus via de STM-stuureenheid en een busdongle."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    AANTAL_INGANGEN,
    CONF_BUS_PORT,
    CONF_IP,
    CONF_MODULES,
    CONF_STM_PORT,
    DOMAIN,
    MODULE_INGANG,
    PHC_MAX,
    PHC_MIN,
    ethernet_device_id,
    module_address,
    module_key,
)
from .hub import PhcHub
from .protocol import virtual_functie

PLATFORMS = [
    Platform.SWITCH,
    Platform.COVER,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.BUTTON,
]

SERVICE_RAW = "stuur_commando"
SERVICE_VIRTUAL = "virtuele_ingang"

RAW_SCHEMA = vol.Schema({vol.Required("adres"): cv.string, vol.Required("data"): cv.string})
VIRTUAL_SCHEMA = vol.Schema(
    {
        vol.Required("adres"): vol.All(vol.Coerce(int), vol.Range(min=PHC_MIN, max=PHC_MAX)),
        vol.Required("kanaal"): vol.All(vol.Coerce(int), vol.Range(min=0, max=AANTAL_INGANGEN - 1)),
        vol.Required("functie"): cv.string,
    }
)


def _get_hub(hass: HomeAssistant) -> PhcHub:
    hubs = hass.data.get(DOMAIN, {})
    if not hubs:
        raise HomeAssistantError("Peha PHC is niet geladen")
    return next(iter(hubs.values()))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Registreert de services één keer voor het hele domein."""

    async def _raw_service(call: ServiceCall) -> None:
        hub = _get_hub(hass)
        try:
            address = int(str(call.data["adres"]).strip(), 16)
            data = bytes.fromhex(str(call.data["data"]).replace(" ", ""))
        except ValueError as err:
            raise HomeAssistantError(f"Ongeldige hex-waarde: {err}") from err
        await hub.async_raw(address, data)

    async def _virtual_service(call: ServiceCall) -> None:
        hub = _get_hub(hass)
        functie = virtual_functie(call.data["functie"])
        if functie is None:
            raise HomeAssistantError(f"Onbekende virtuele functie: {call.data['functie']}")
        address = module_address(MODULE_INGANG, call.data["adres"])
        await hub.async_virtual_click(address, call.data["kanaal"], functie)

    hass.services.async_register(DOMAIN, SERVICE_RAW, _raw_service, schema=RAW_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_VIRTUAL, _virtual_service, schema=VIRTUAL_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = PhcHub(hass, entry.entry_id)
    hub.configure(
        list(entry.options.get(CONF_MODULES, [])),
        entry.data[CONF_STM_PORT],
        entry.data[CONF_BUS_PORT],
    )
    _async_cleanup_devices(hass, entry, hub)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    # De poortschakelaars herstellen hun stand vóór de poorten geopend worden.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await hub.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_stop()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_cleanup_devices(hass: HomeAssistant, entry: ConfigEntry, hub: PhcHub) -> None:
    """Verwijdert apparaten van modules die uit de configuratie zijn gehaald.

    Het hub-apparaat (poorten en logs) blijft altijd staan.
    """
    registry = dr.async_get(hass)
    keep = {(DOMAIN, entry.entry_id)}
    keep |= {(DOMAIN, m.device_id) for m in hub.modules.values()}
    keep |= {(DOMAIN, module_key(v)) for v in hub.virtual_buttons}
    keep |= {(DOMAIN, ethernet_device_id(m[CONF_IP])) for m in hub.ethernet_modules}
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        ids = {identifier for identifier in device.identifiers if identifier[0] == DOMAIN}
        if ids and not ids & keep:
            registry.async_remove_device(device.id)
