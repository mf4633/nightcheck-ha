"""On when something needs a look (for automations)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightCheckConfigEntry
from .entity import NightCheckEntity


async def async_setup_entry(hass: HomeAssistant, entry: NightCheckConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([NightCheckAttention(entry.runtime_data)])


class NightCheckAttention(NightCheckEntity, BinarySensorEntity):
    """Problem = the last check found something open or bins not out."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, runner) -> None:
        super().__init__(runner, "needs_attention")

    @property
    def is_on(self) -> bool | None:
        level = (self.runner.result or {}).get("level")
        return None if level is None else level == "attention"
