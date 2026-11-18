"""Check now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightCheckConfigEntry
from .entity import NightCheckEntity


async def async_setup_entry(hass: HomeAssistant, entry: NightCheckConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([NightCheckNowButton(entry.runtime_data)])


class NightCheckNowButton(NightCheckEntity, ButtonEntity):
    """Runs a check straight away, bins included; no phone notification."""

    def __init__(self, runner) -> None:
        super().__init__(runner, "check_now")

    async def async_press(self) -> None:
        await self.runner.async_run(manual=True)
