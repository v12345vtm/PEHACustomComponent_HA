# Peha PHC-integratie, versie 1.1.0
"""Installatie en opties van de Peha PHC-integratie.

Een module toevoegen vraagt alleen het PHC-nummer en een naam. Het aantal kanalen is vast
(relais 8, rolluik 4, ingangen 16). De looptijden van een rolluik stel je daarna per kanaal in.
"""
from __future__ import annotations

import dataclasses
import os
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_BUS_POORT,
    CONF_DEMO,
    CONF_MODULES,
    CONF_NAAM,
    CONF_STM_POORT,
    DOMAIN,
    LOOPTIJD_MAX,
    NUMMER_MAX,
    NUMMER_MIN,
    ROLLUIK_KANALEN,
    STANDAARD_BUS_POORT,
    STANDAARD_STM_POORT,
    TYPE_INGANG,
    TYPE_RELAIS,
    TYPE_ROLLUIK,
)
from .model import Module, module_adres


def _getal(minimum: float, maximum: float, stap: float = 1, eenheid: str | None = None):
    config: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "step": stap,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if eenheid:  # een lege eenheid maakt de selector ongeldig in Home Assistant
        config["unit_of_measurement"] = eenheid
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def _keuze(opties: list) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=opties, mode=selector.SelectSelectorMode.DROPDOWN,
    ))


async def _controleer_poorten(hass: HomeAssistant, stm: str, bus: str, demo: bool) -> str | None:
    """Geeft een foutcode, of None als de poorten goed zijn."""
    if demo:
        return None
    if stm == bus:
        return "zelfde_poort"
    for poort in (stm, bus):
        if not await hass.async_add_executor_job(os.path.exists, poort):
            return "poort_niet_gevonden"
    return None


class PehaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            stm = user_input[CONF_STM_POORT].strip()
            bus = user_input[CONF_BUS_POORT].strip()
            demo = bool(user_input.get(CONF_DEMO, False))
            fout = await _controleer_poorten(self.hass, stm, bus, demo)
            if fout:
                errors["base"] = fout
            else:
                await self.async_set_unique_id("demo" if demo else f"{stm}|{bus}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAAM].strip() or "Peha PHC",
                    data={CONF_STM_POORT: stm, CONF_BUS_POORT: bus, CONF_DEMO: demo},
                    options={CONF_MODULES: []},
                )

        schema = vol.Schema({
            vol.Required(CONF_NAAM, default="Peha PHC"): str,
            vol.Required(CONF_STM_POORT, default=STANDAARD_STM_POORT): str,
            vol.Required(CONF_BUS_POORT, default=STANDAARD_BUS_POORT): str,
            vol.Optional(CONF_DEMO, default=False): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> PehaOptionsFlow:
        return PehaOptionsFlow()


class PehaOptionsFlow(config_entries.OptionsFlow):
    _gekozen: int | None = None  # het rolluik dat je in de eerste stap van de looptijden koos

    def _modules(self) -> list[Module]:
        return [Module.van_dict(m) for m in self.config_entry.options.get(CONF_MODULES, [])]

    def _bewaar(self, modules: list[Module]):
        return self.async_create_entry(title="", data={CONF_MODULES: [m.naar_dict() for m in modules]})

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "relais_toevoegen",
                "rolluik_toevoegen",
                "ingang_toevoegen",
                "looptijden_rolluik",
                "module_verwijderen",
                "poorten",
            ],
        )

    async def async_step_relais_toevoegen(self, user_input: dict[str, Any] | None = None):
        return await self._toevoegen(TYPE_RELAIS, "relais_toevoegen", user_input)

    async def async_step_rolluik_toevoegen(self, user_input: dict[str, Any] | None = None):
        return await self._toevoegen(TYPE_ROLLUIK, "rolluik_toevoegen", user_input)

    async def async_step_ingang_toevoegen(self, user_input: dict[str, Any] | None = None):
        return await self._toevoegen(TYPE_INGANG, "ingang_toevoegen", user_input)

    async def _toevoegen(self, soort: str, step_id: str, user_input: dict[str, Any] | None):
        errors: dict[str, str] = {}
        if user_input is not None:
            naam = str(user_input.get("naam") or "").strip()
            modules = self._modules()
            try:
                nummer = int(user_input.get("nummer"))
                adres = module_adres(soort, nummer)
            except (TypeError, ValueError):
                errors["nummer"] = "ongeldig_nummer"
            else:
                if not naam:
                    errors["naam"] = "naam_verplicht"
                elif adres in {m.adres for m in modules}:
                    errors["nummer"] = "nummer_bezet"
                else:
                    return self._bewaar(modules + [Module(type=soort, nummer=nummer, naam=naam)])

        schema = vol.Schema({
            vol.Required("nummer", default=0): _getal(NUMMER_MIN, NUMMER_MAX),
            vol.Required("naam"): selector.TextSelector(),
        })
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_looptijden_rolluik(self, user_input: dict[str, Any] | None = None):
        rolluiken = [m for m in self._modules() if m.type == TYPE_ROLLUIK]
        if not rolluiken:
            return self.async_abort(reason="geen_rolluiken")
        if user_input is not None:
            self._gekozen = int(user_input["module"])
            return await self.async_step_looptijden_kanalen()
        schema = vol.Schema({
            vol.Required("module"): _keuze([
                selector.SelectOptionDict(value=str(m.nummer), label=f"{m.weergavenaam} (PHC-nummer {m.nummer})")
                for m in rolluiken
            ]),
        })
        return self.async_show_form(step_id="looptijden_rolluik", data_schema=schema)

    async def async_step_looptijden_kanalen(self, user_input: dict[str, Any] | None = None):
        modules = self._modules()
        gekozen = next(
            (m for m in modules if m.type == TYPE_ROLLUIK and m.nummer == self._gekozen), None
        )
        if gekozen is None:
            return self.async_abort(reason="geen_rolluiken")
        if user_input is not None:
            tijden = tuple(float(user_input.get(f"kanaal_{k}") or 0) for k in range(ROLLUIK_KANALEN))
            nieuw = dataclasses.replace(gekozen, looptijden=tijden)
            return self._bewaar([
                nieuw if (m.type == TYPE_ROLLUIK and m.nummer == gekozen.nummer) else m
                for m in modules
            ])
        schema = vol.Schema({
            vol.Required(f"kanaal_{k}", default=gekozen.looptijden[k]): _getal(0, LOOPTIJD_MAX, 0.5, "s")
            for k in range(ROLLUIK_KANALEN)
        })
        return self.async_show_form(step_id="looptijden_kanalen", data_schema=schema)

    async def async_step_module_verwijderen(self, user_input: dict[str, Any] | None = None):
        modules = self._modules()
        if not modules:
            return self.async_abort(reason="geen_modules")
        if user_input is not None:
            gekozen = user_input["module"]
            return self._bewaar([m for m in modules if f"{m.type}:{m.nummer}" != gekozen])
        keuzes = [
            selector.SelectOptionDict(
                value=f"{m.type}:{m.nummer}",
                label=f"{m.weergavenaam} ({m.type}, adres 0x{m.adres:02X})",
            )
            for m in modules
        ]
        schema = vol.Schema({vol.Required("module"): _keuze(keuzes)})
        return self.async_show_form(step_id="module_verwijderen", data_schema=schema)

    async def async_step_poorten(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        huidig = self.config_entry.data
        if user_input is not None:
            stm = user_input[CONF_STM_POORT].strip()
            bus = user_input[CONF_BUS_POORT].strip()
            fout = await _controleer_poorten(self.hass, stm, bus, bool(huidig.get(CONF_DEMO)))
            if fout:
                errors["base"] = fout
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**huidig, CONF_STM_POORT: stm, CONF_BUS_POORT: bus},
                )
                return self.async_create_entry(title="", data=dict(self.config_entry.options))

        schema = vol.Schema({
            vol.Required(CONF_STM_POORT, default=huidig.get(CONF_STM_POORT, STANDAARD_STM_POORT)): str,
            vol.Required(CONF_BUS_POORT, default=huidig.get(CONF_BUS_POORT, STANDAARD_BUS_POORT)): str,
        })
        return self.async_show_form(step_id="poorten", data_schema=schema, errors=errors)
