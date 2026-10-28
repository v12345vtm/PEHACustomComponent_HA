# config_flow.py - Peha PHC versie 0.1.2
"""Configuratie- en optiesflow voor Peha PHC."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    AANTAL_INGANGEN,
    CONF_BUS_PORT,
    CONF_FUNCTIE,
    CONF_KANAAL,
    CONF_MODULES,
    CONF_NAAM,
    CONF_PHC,
    CONF_STM_PORT,
    CONF_TYPE,
    DEFAULT_BUS_PORT,
    DEFAULT_STM_PORT,
    DOMAIN,
    MODULE_INGANG,
    MODULE_LABELS,
    MODULE_RELAIS,
    MODULE_ROLLUIK,
    MODULE_VIRTUEEL,
    PHC_MAX,
    PHC_MIN,
    SERIAL_OPTIONS,
    VIRTUAL_FUNCTIES,
    module_address,
    module_key,
)


async def _async_port_ok(hass: HomeAssistant, port: str) -> bool:
    """Probeert de poort kort te openen en weer te sluiten."""

    def _try() -> bool:
        import serial  # pylint: disable=import-outside-toplevel

        try:
            serial.Serial(port, baudrate=SERIAL_OPTIONS["baudrate"], timeout=0.2).close()
            return True
        except (serial.SerialException, OSError):
            return False

    return await hass.async_add_executor_job(_try)


def _port_schema(stm: str, bus: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_STM_PORT, default=stm): TextSelector(),
            vol.Required(CONF_BUS_PORT, default=bus): TextSelector(),
        }
    )


def _phc_field() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=PHC_MIN, max=PHC_MAX, step=1, mode=NumberSelectorMode.BOX)
    )


def _kanaal_field() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=0, max=AANTAL_INGANGEN - 1, step=1, mode=NumberSelectorMode.BOX)
    )


def _functie_field() -> SelectSelector:
    options = [SelectOptionDict(value=k, label=v) for k, v in VIRTUAL_FUNCTIES.items()]
    return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))


def _address_in_use(modules: list[dict], kind: str, phc: int) -> bool:
    """Relais en rolluik delen dezelfde adresruimte (0x40 + PHC-nummer)."""
    address = module_address(kind, phc)
    return any(
        m[CONF_TYPE] != MODULE_VIRTUEEL and module_address(m[CONF_TYPE], m[CONF_PHC]) == address
        for m in modules
    )


def _label(item: dict) -> str:
    if item[CONF_TYPE] == MODULE_VIRTUEEL:
        return (
            f"{item[CONF_NAAM]} (virtueel, ingang {item[CONF_PHC]}, "
            f"kanaal {item[CONF_KANAAL]}, {VIRTUAL_FUNCTIES.get(item[CONF_FUNCTIE], item[CONF_FUNCTIE])})"
        )
    return f"{item[CONF_NAAM]} ({MODULE_LABELS[item[CONF_TYPE]]} {item[CONF_PHC]})"


class PhcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Eerste instelling: de twee poorten."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_STM_PORT]}|{user_input[CONF_BUS_PORT]}")
            self._abort_if_unique_id_configured()
            if await _async_port_ok(self.hass, user_input[CONF_STM_PORT]) and await _async_port_ok(
                self.hass, user_input[CONF_BUS_PORT]
            ):
                return self.async_create_entry(title="Peha PHC", data=user_input)
            errors["base"] = "cannot_connect"

        schema = _port_schema(
            (user_input or {}).get(CONF_STM_PORT, DEFAULT_STM_PORT),
            (user_input or {}).get(CONF_BUS_PORT, DEFAULT_BUS_PORT),
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PhcOptionsFlow()


class PhcOptionsFlow(OptionsFlow):
    """Modules toevoegen, verwijderen en poorten wijzigen."""

    @property
    def _modules(self) -> list[dict]:
        return list(self.config_entry.options.get(CONF_MODULES, []))

    def _save(self, modules: list[dict]):
        return self.async_create_entry(title="", data={**self.config_entry.options, CONF_MODULES: modules})

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["relais", "rolluik", "ingang", "virtueel", "verwijder", "poorten"],
        )

    async def async_step_relais(self, user_input: dict[str, Any] | None = None):
        return await self._async_add_module(MODULE_RELAIS, "relais", user_input)

    async def async_step_rolluik(self, user_input: dict[str, Any] | None = None):
        return await self._async_add_module(MODULE_ROLLUIK, "rolluik", user_input)

    async def async_step_ingang(self, user_input: dict[str, Any] | None = None):
        return await self._async_add_module(MODULE_INGANG, "ingang", user_input)

    async def _async_add_module(self, kind: str, step: str, user_input: dict[str, Any] | None):
        errors: dict[str, str] = {}
        if user_input is not None:
            phc = int(user_input[CONF_PHC])
            item = {CONF_TYPE: kind, CONF_PHC: phc, CONF_NAAM: user_input[CONF_NAAM].strip()}
            if _address_in_use(self._modules, kind, phc):
                errors["base"] = "adres_bezet"
            else:
                return self._save([*self._modules, item])

        schema = vol.Schema({vol.Required(CONF_PHC): _phc_field(), vol.Required(CONF_NAAM): TextSelector()})
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    async def async_step_virtueel(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            item = {
                CONF_TYPE: MODULE_VIRTUEEL,
                CONF_PHC: int(user_input[CONF_PHC]),
                CONF_KANAAL: int(user_input[CONF_KANAAL]),
                CONF_FUNCTIE: user_input[CONF_FUNCTIE],
                CONF_NAAM: user_input[CONF_NAAM].strip(),
            }
            if any(module_key(m) == module_key(item) for m in self._modules):
                errors["base"] = "dubbel"
            else:
                return self._save([*self._modules, item])

        schema = vol.Schema(
            {
                vol.Required(CONF_PHC): _phc_field(),
                vol.Required(CONF_KANAAL): _kanaal_field(),
                vol.Required(CONF_FUNCTIE, default="kort"): _functie_field(),
                vol.Required(CONF_NAAM): TextSelector(),
            }
        )
        return self.async_show_form(step_id="virtueel", data_schema=schema, errors=errors)

    async def async_step_verwijder(self, user_input: dict[str, Any] | None = None):
        modules = self._modules
        if not modules:
            return self.async_abort(reason="geen_modules")
        if user_input is not None:
            remove = user_input["module"]
            return self._save([m for m in modules if module_key(m) != remove])

        options = [SelectOptionDict(value=module_key(m), label=_label(m)) for m in modules]
        schema = vol.Schema(
            {
                vol.Required("module"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="verwijder", data_schema=schema)

    async def async_step_poorten(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            if await _async_port_ok(self.hass, user_input[CONF_STM_PORT]) and await _async_port_ok(
                self.hass, user_input[CONF_BUS_PORT]
            ):
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data={**self.config_entry.data, **user_input}
                )
                return self._save(self._modules)
            errors["base"] = "cannot_connect"

        current = {**self.config_entry.data, **(user_input or {})}
        schema = _port_schema(current[CONF_STM_PORT], current[CONF_BUS_PORT])
        return self.async_show_form(step_id="poorten", data_schema=schema, errors=errors)
