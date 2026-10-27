# Peha PHC-integratie, versie 1.1.0
"""Peha PHC: relais, rolluiken en ingangen aansturen en de stand bijhouden via de RS485-bus."""
from __future__ import annotations

import os
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_BUS_POORT,
    CONF_DEMO,
    CONF_MODULES,
    CONF_STM_POORT,
    DOMAIN,
    EVENT_INGANG,
    NUMMER_MAX,
    NUMMER_MIN,
    RELAIS_KANALEN,
    ROLLUIK_KANALEN,
    TYPE_INGANG,
    TYPE_NAMEN,
    TYPE_RELAIS,
    TYPE_ROLLUIK,
    signaal,
)
from .hub import PehaError, PehaHub
from .model import Module, module_adres
from .protocol import ROLLUIK_BEWEGING, RELAIS_CODES, bus_frame
from .transport import DemoTransport, SerialTransport

PLATFORMS = [
    Platform.SWITCH,
    Platform.COVER,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
]

PehaConfigEntry = ConfigEntry[PehaHub]

RELAIS_ACTIES = [actie for actie in RELAIS_CODES if actie != "status"]
TYPES = [TYPE_RELAIS, TYPE_ROLLUIK, TYPE_INGANG]

HUB_VELD = {vol.Optional("hub"): cv.string}
NUMMER = vol.All(vol.Coerce(int), vol.Range(min=NUMMER_MIN, max=NUMMER_MAX))
KANAAL_RELAIS = vol.All(vol.Coerce(int), vol.Range(min=0, max=RELAIS_KANALEN - 1))
KANAAL_ROLLUIK = vol.All(vol.Coerce(int), vol.Range(min=0, max=ROLLUIK_KANALEN - 1))
TIJD = vol.All(vol.Coerce(float), vol.Range(min=0, max=6553))
PRIORITEIT = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))

SCHEMA_RELAIS = vol.Schema({
    **HUB_VELD,
    vol.Required("module"): NUMMER,
    vol.Required("kanaal"): KANAAL_RELAIS,
    vol.Required("actie"): vol.In(RELAIS_ACTIES),
    vol.Optional("tijd"): TIJD,
})
SCHEMA_ROLLUIK = vol.Schema({
    **HUB_VELD,
    vol.Required("module"): NUMMER,
    vol.Required("kanaal"): KANAAL_ROLLUIK,
    vol.Required("actie"): vol.In(ROLLUIK_BEWEGING),
    vol.Optional("tijd", default=0): TIJD,
    vol.Optional("prioriteit", default=7): PRIORITEIT,
})
SCHEMA_STATUS = vol.Schema({
    **HUB_VELD,
    vol.Optional("module"): NUMMER,
    vol.Optional("type"): vol.In(TYPES),
})
SCHEMA_RUW = vol.Schema({
    **HUB_VELD,
    vol.Required("adres"): cv.string,
    vol.Required("payload"): cv.string,
})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """De services registreren we één keer, ook als er meerdere installaties zijn."""

    async def relais_commando(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("hub"))
        adres = _adres_van(hub, call.data["module"], TYPE_RELAIS)
        await _uitvoeren(hub.relais_commando(
            adres, call.data["kanaal"], call.data["actie"], call.data.get("tijd"),
        ))

    async def rolluik_beweeg(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("hub"))
        adres = _adres_van(hub, call.data["module"], TYPE_ROLLUIK)
        await _uitvoeren(hub.rolluik_commando(
            adres, call.data["kanaal"], call.data["actie"],
            call.data.get("tijd", 0.0), call.data.get("prioriteit", 7),
        ))

    async def status_opvragen(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("hub"))
        nummer, soort = call.data.get("module"), call.data.get("type")
        if nummer is None and soort is None:
            await _uitvoeren(hub.vraag_status_alles())
            return
        doelen = [
            m.adres for m in hub.modules.values()
            if (nummer is None or m.nummer == nummer) and (soort is None or m.type == soort)
        ]
        if not doelen:
            raise HomeAssistantError("Geen module die bij deze gegevens past")
        for adres in doelen:
            await _uitvoeren(hub.vraag_status(adres))

    async def stuur_commando(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("hub"))
        await _uitvoeren(hub.stuur_ruw(_adres(call.data["adres"]), _bytes(call.data["payload"])))

    async def simuleer_busbericht(call: ServiceCall) -> None:
        """Voert een busbericht in de parser in, alsof het van de bus kwam. Handig om opnames te testen."""
        hub = _hub(hass, call.data.get("hub"))
        payload = _bytes(call.data["payload"])
        if not 1 <= len(payload) <= 127:
            raise HomeAssistantError("payload moet 1 t/m 127 bytes zijn")
        hub.verwerk_busbytes(bus_frame(_adres(call.data["adres"]), payload))

    hass.services.async_register(DOMAIN, "relais_commando", relais_commando, schema=SCHEMA_RELAIS)
    hass.services.async_register(DOMAIN, "rolluik_beweeg", rolluik_beweeg, schema=SCHEMA_ROLLUIK)
    hass.services.async_register(DOMAIN, "status_opvragen", status_opvragen, schema=SCHEMA_STATUS)
    hass.services.async_register(DOMAIN, "stuur_commando", stuur_commando, schema=SCHEMA_RUW)
    hass.services.async_register(DOMAIN, "simuleer_busbericht", simuleer_busbericht, schema=SCHEMA_RUW)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PehaConfigEntry) -> bool:
    modules = [Module.van_dict(m) for m in entry.options.get(CONF_MODULES, [])]
    if entry.data.get(CONF_DEMO):
        demo = DemoTransport(modules)
        stm = bus = demo
    else:
        stm_poort = entry.data[CONF_STM_POORT]
        bus_poort = entry.data[CONF_BUS_POORT]
        for poort in (stm_poort, bus_poort):
            if not await hass.async_add_executor_job(os.path.exists, poort):
                raise ConfigEntryNotReady(f"poort {poort} bestaat (nog) niet")
        stm = SerialTransport(stm_poort)
        bus = SerialTransport(bus_poort)

    hub = PehaHub(entry.title, modules, stm, bus, _maak_notify(hass, entry.entry_id))
    await hub.start()
    entry.runtime_data = hub
    entry.async_on_unload(entry.add_update_listener(_opties_bijgewerkt))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await hub.stop()
        raise
    hass.async_create_background_task(hub.vraag_status_alles(), f"peha_status_{entry.entry_id}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PehaConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.stop()
    return ok


async def _opties_bijgewerkt(hass: HomeAssistant, entry: PehaConfigEntry) -> None:
    """Modules of poorten zijn gewijzigd: herlaad, zodat de entiteiten kloppen."""
    await hass.config_entries.async_reload(entry.entry_id)


def _maak_notify(hass: HomeAssistant, entry_id: str):
    def notify(soort: str, data: Any) -> None:
        if soort == "event":
            hass.bus.async_fire(EVENT_INGANG, data)
        else:
            async_dispatcher_send(hass, signaal(entry_id, soort), data)

    return notify


def _hub(hass: HomeAssistant, naam: str | None) -> PehaHub:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if naam:
        entries = [e for e in entries if e.title.lower() == naam.lower()]
    if not entries:
        raise HomeAssistantError("Geen geladen Peha PHC-installatie gevonden" + (f" met naam {naam}" if naam else ""))
    if len(entries) > 1:
        raise HomeAssistantError("Meerdere Peha PHC-installaties: geef de naam mee met 'hub'")
    return entries[0].runtime_data


def _adres_van(hub: PehaHub, nummer: int, soort: str) -> int:
    adres = module_adres(soort, nummer)
    module = hub.modules.get(adres)
    if module is None or module.type != soort:
        raise HomeAssistantError(f"Geen {TYPE_NAMEN[soort].lower()} met nummer {nummer} ingesteld")
    return adres


def _adres(tekst: str) -> int:
    try:
        waarde = int(str(tekst).strip(), 16)
    except ValueError as err:
        raise HomeAssistantError(f"'{tekst}' is geen geldig hexadecimaal adres") from err
    if not 0 <= waarde <= 0xFF:
        raise HomeAssistantError("adres moet tussen 00 en FF liggen")
    return waarde


def _bytes(tekst: str) -> bytes:
    try:
        return bytes.fromhex(str(tekst).replace(" ", ""))
    except ValueError as err:
        raise HomeAssistantError(f"'{tekst}' is geen geldige hex-tekst") from err


async def _uitvoeren(awaitable) -> None:
    try:
        await awaitable
    except PehaError as err:
        raise HomeAssistantError(str(err)) from err
