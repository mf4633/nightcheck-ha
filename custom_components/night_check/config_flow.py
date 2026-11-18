"""Config flow for Night Check: paste a key, then pick cameras in the options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .api import NightCheckApi, NightCheckAuthError, NightCheckError
from .const import (
    CONF_API_BASE,
    CONF_API_KEY,
    CONF_BINS,
    CONF_CHECK_TIME,
    CONF_GARAGE,
    CONF_GATE,
    CONF_NOTIFY,
    CONF_NOTIFY_WHEN,
    CONF_PICKUP_DAYS,
    DEFAULT_API_BASE,
    DEFAULT_CHECK_TIME,
    DOMAIN,
    NOTIFY_ALWAYS,
    NOTIFY_PROBLEMS,
    WEEKDAYS,
)

KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})


async def _validate(hass, key: str, base: str) -> str | None:
    """None if the key works, else an error code for the form."""
    if not key.startswith("nc_"):
        return "invalid_key"
    try:
        await NightCheckApi(async_get_clientsession(hass), key, base).account()
    except NightCheckAuthError:
        return "invalid_key"
    except NightCheckError:
        return "cannot_connect"
    return None


class NightCheckConfigFlow(ConfigFlow, domain=DOMAIN):
    """One Night Check per Home Assistant."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            base = user_input.get(CONF_API_BASE) or DEFAULT_API_BASE
            if (err := await _validate(self.hass, key, base)) is None:
                data = {CONF_API_KEY: key}
                if base != DEFAULT_API_BASE:
                    data[CONF_API_BASE] = base
                return self.async_create_entry(
                    title="Night Check",
                    data=data,
                    options={CONF_CHECK_TIME: DEFAULT_CHECK_TIME, CONF_NOTIFY_WHEN: NOTIFY_PROBLEMS},
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="user",
            data_schema=KEY_SCHEMA,
            errors=errors,
            description_placeholders={"signup_url": f"{DEFAULT_API_BASE}/home-assistant"},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._new_key("reauth_confirm", self._get_reauth_entry(), user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._new_key("reconfigure", self._get_reconfigure_entry(), user_input)

    async def _new_key(self, step_id: str, entry: ConfigEntry, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            if (err := await _validate(self.hass, key, entry.data.get(CONF_API_BASE) or DEFAULT_API_BASE)) is None:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: key})
            errors["base"] = err
        return self.async_show_form(
            step_id=step_id,
            data_schema=KEY_SCHEMA,
            errors=errors,
            description_placeholders={"signup_url": f"{DEFAULT_API_BASE}/home-assistant"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NightCheckOptionsFlow()


def options_schema(current: Mapping[str, Any]) -> vol.Schema:
    cams = EntitySelector(EntitySelectorConfig(domain="camera", multiple=True))
    return vol.Schema(
        {
            vol.Optional(CONF_GARAGE, default=current.get(CONF_GARAGE, [])): cams,
            vol.Optional(CONF_GATE, default=current.get(CONF_GATE, [])): cams,
            vol.Optional(CONF_BINS, default=current.get(CONF_BINS, [])): cams,
            vol.Required(CONF_CHECK_TIME, default=current.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME)): TimeSelector(),
            vol.Optional(CONF_PICKUP_DAYS, default=current.get(CONF_PICKUP_DAYS, [])): SelectSelector(
                SelectSelectorConfig(options=WEEKDAYS, multiple=True, mode=SelectSelectorMode.LIST, translation_key="weekday")
            ),
            vol.Optional(CONF_NOTIFY, description={"suggested_value": current.get(CONF_NOTIFY, "")}): TextSelector(),
            vol.Required(CONF_NOTIFY_WHEN, default=current.get(CONF_NOTIFY_WHEN, NOTIFY_PROBLEMS)): SelectSelector(
                SelectSelectorConfig(options=[NOTIFY_PROBLEMS, NOTIFY_ALWAYS], mode=SelectSelectorMode.LIST, translation_key="notify_when")
            ),
        }
    )


class NightCheckOptionsFlow(OptionsFlow):
    """Cameras, time, pickup days, phone notification."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            total = sum(len(user_input.get(k) or []) for k in (CONF_GARAGE, CONF_GATE, CONF_BINS))
            notify = (user_input.get(CONF_NOTIFY) or "").strip().removeprefix("notify.")
            if total > 6:
                errors["base"] = "too_many_cameras"
            elif notify and not self.hass.services.has_service("notify", notify):
                errors[CONF_NOTIFY] = "unknown_notify"
            else:
                user_input[CONF_NOTIFY] = notify
                return self.async_create_entry(data=user_input)
        current = user_input or self.config_entry.options
        return self.async_show_form(step_id="init", data_schema=options_schema(current), errors=errors)
