"""The evening answer as a sensor: ok, attention, unknown or inactive."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import NightCheckConfigEntry
from .const import LEVELS
from .entity import NightCheckEntity


async def async_setup_entry(hass: HomeAssistant, entry: NightCheckConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    runner = entry.runtime_data
    add([NightCheckResultSensor(runner), NightCheckLastSensor(runner)])


class NightCheckResultSensor(NightCheckEntity, SensorEntity, RestoreEntity):
    """ok / attention / unknown / inactive, with the message and per-camera rows."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = LEVELS

    def __init__(self, runner) -> None:
        super().__init__(runner, "result")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.runner.result is None and (last := await self.async_get_last_state()) and last.state in LEVELS:
            attrs = dict(last.attributes)
            self.runner.result = {
                "level": last.state,
                "subject": attrs.get("subject"),
                "text": attrs.get("text"),
                "cameras": attrs.get("cameras") or [],
                "checked_at": attrs.get("checked_at"),
            }

    @property
    def native_value(self) -> str | None:
        return (self.runner.result or {}).get("level")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self.runner.result or {}
        return {k: r.get(k) for k in ("subject", "text", "cameras", "checked_at")}


class NightCheckLastSensor(NightCheckEntity, SensorEntity):
    """When the last check ran."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, runner) -> None:
        super().__init__(runner, "last_check")

    @property
    def native_value(self) -> datetime | None:
        at = (self.runner.result or {}).get("checked_at")
        return dt_util.parse_datetime(at) if at else None
