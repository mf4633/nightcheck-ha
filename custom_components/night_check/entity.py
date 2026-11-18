"""Shared base for Night Check entities."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import NightCheckRunner
from .const import DOMAIN, SIGNAL_UPDATE


class NightCheckEntity(Entity):
    """Belongs to the one Night Check service device and redraws after each check."""

    _attr_has_entity_name = True

    def __init__(self, runner: NightCheckRunner, key: str) -> None:
        self.runner = runner
        self._attr_unique_id = f"{runner.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runner.entry.entry_id)},
            name="Night Check",
            manufacturer="HydroComplete, LLC",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://nightcheck.hydrocomplete.com/home-assistant",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE.format(self.runner.entry.entry_id), self._updated)
        )

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()
