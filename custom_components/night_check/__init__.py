"""Night Check: an evening reminder if the garage door or gate is open, or the bins aren't out."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.camera import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .api import NightCheckApi, NightCheckAuthError, NightCheckError, NightCheckInactive
from .const import (
    CONF_API_BASE,
    CONF_API_KEY,
    CONF_BINS,
    CONF_CHECK_TIME,
    CONF_NOTIFY,
    CONF_NOTIFY_WHEN,
    CONF_PICKUP_DAYS,
    DEFAULT_API_BASE,
    DEFAULT_CHECK_TIME,
    DOMAIN,
    EVENT_RESULT,
    IMAGE_TIMEOUT,
    IMAGE_WIDTH,
    ITEM_FOR_OPTION,
    NOTIFY_ALWAYS,
    SIGNAL_UPDATE,
    WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

type NightCheckConfigEntry = ConfigEntry[NightCheckRunner]


def parse_time(value: str | None) -> tuple[int, int]:
    """'HH:MM[:SS]' -> (hour, minute); falls back to 22:00."""
    try:
        parts = str(value or DEFAULT_CHECK_TIME).split(":")
        hour, minute = int(parts[0]), int(parts[1])
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    except (ValueError, IndexError):
        pass
    return 22, 0


def is_pickup_eve(now: datetime, pickup_days: list[str]) -> bool:
    """True when tomorrow (local) is a pickup day."""
    tomorrow = WEEKDAYS[(now + timedelta(days=1)).weekday()]
    return tomorrow in (pickup_days or [])


def cameras_to_check(options: dict[str, Any], include_bins: bool) -> list[tuple[str, str]]:
    """[(entity_id, item)] in a stable order; bins only when asked."""
    out: list[tuple[str, str]] = []
    for option, item in ITEM_FOR_OPTION.items():
        if option == CONF_BINS and not include_bins:
            continue
        for entity_id in options.get(option) or []:
            out.append((entity_id, item))
    return out


class NightCheckRunner:
    """Takes the pictures, asks the service, publishes the answer."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: NightCheckApi) -> None:
        self.hass = hass
        self.entry = entry
        self.api = api
        self.result: dict[str, Any] | None = None
        self._unsub = None

    @property
    def options(self) -> dict[str, Any]:
        return dict(self.entry.options)

    @callback
    def schedule(self) -> None:
        """(Re)arm the nightly check at the chosen local time."""
        if self._unsub:
            self._unsub()
        hour, minute = parse_time(self.options.get(CONF_CHECK_TIME))
        self._unsub = async_track_time_change(self.hass, self._scheduled, hour=hour, minute=minute, second=0)

    @callback
    def unschedule(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _scheduled(self, now: datetime) -> None:
        await self.async_run(manual=False)

    async def _picture(self, entity_id: str) -> tuple[bytes | None, str | None]:
        try:
            image = await async_get_image(self.hass, entity_id, timeout=IMAGE_TIMEOUT, width=IMAGE_WIDTH)
        except HomeAssistantError as err:
            _LOGGER.warning("Night Check: no picture from %s: %s", entity_id, err)
            return None, "unavailable"
        if "jpeg" not in (image.content_type or "") and "jpg" not in (image.content_type or ""):
            return None, "not a jpeg"
        return image.content, None

    async def async_run(self, manual: bool) -> dict[str, Any] | None:
        """One check. Manual checks include the bins; scheduled ones only on pickup eve."""
        opts = self.options
        include_bins = manual or is_pickup_eve(dt_util.now(), opts.get(CONF_PICKUP_DAYS, []))
        wanted = cameras_to_check(opts, include_bins)
        if not wanted:
            _LOGGER.info("Night Check: no cameras chosen for this check; open Configure to pick some")
            return None

        cameras = []
        for entity_id, item in wanted:
            state = self.hass.states.get(entity_id)
            name = (state and state.attributes.get("friendly_name")) or entity_id
            image, error = await self._picture(entity_id)
            cameras.append({"name": name, "item": item, "image": image, "error": error, "entity_id": entity_id})

        try:
            result = await self.api.check(cameras)
        except NightCheckAuthError:
            self.entry.async_start_reauth(self.hass)
            result = self._local_result("unknown", "Night Check key isn't valid", "Reconnect Night Check with a new key.")
        except NightCheckInactive as err:
            result = self._local_result("inactive", "Night Check subscription isn't active", str(err))
        except NightCheckError as err:
            _LOGGER.warning("Night Check: %s", err)
            result = self._local_result("unknown", "Night Check couldn't check tonight", "The Night Check service didn't answer. Please take a look yourself.")

        # Keep the entity ids next to the service's answer, in the same order.
        for cam, row in zip(cameras, result.get("cameras", [])):
            row["entity_id"] = cam["entity_id"]
        result["manual"] = manual
        self.result = result
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))
        self.hass.bus.async_fire(EVENT_RESULT, {k: result.get(k) for k in ("level", "subject", "text", "cameras", "checked_at", "manual")})
        await self._notify(result, manual)
        return result

    def _local_result(self, level: str, subject: str, text: str) -> dict[str, Any]:
        return {"level": level, "subject": subject, "text": text, "cameras": [], "checked_at": dt_util.utcnow().isoformat()}

    async def _notify(self, result: dict[str, Any], manual: bool) -> None:
        service = (self.options.get(CONF_NOTIFY) or "").strip()
        if not service or manual:
            return
        if result.get("level") == "ok" and self.options.get(CONF_NOTIFY_WHEN) != NOTIFY_ALWAYS:
            return
        service = service.removeprefix("notify.")
        if not self.hass.services.has_service("notify", service):
            _LOGGER.warning("Night Check: notify.%s doesn't exist; check the integration's options", service)
            return
        await self.hass.services.async_call(
            "notify", service, {"title": result.get("subject", "Night Check"), "message": result.get("text", "")}, blocking=False
        )


async def async_setup_entry(hass: HomeAssistant, entry: NightCheckConfigEntry) -> bool:
    api = NightCheckApi(async_get_clientsession(hass), entry.data[CONF_API_KEY], entry.data.get(CONF_API_BASE) or DEFAULT_API_BASE)
    runner = NightCheckRunner(hass, entry, api)
    entry.runtime_data = runner
    runner.schedule()
    entry.async_on_unload(runner.unschedule)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: NightCheckConfigEntry) -> None:
    entry.runtime_data.schedule()


async def async_unload_entry(hass: HomeAssistant, entry: NightCheckConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
