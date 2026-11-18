"""Night Check integration: config flow, options, a check end to end, failures."""

from datetime import datetime
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.camera import Image
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.night_check import cameras_to_check, is_pickup_eve, parse_time
from custom_components.night_check.const import DEFAULT_API_BASE, DOMAIN, EVENT_RESULT

BASE = DEFAULT_API_BASE
KEY = "nc_testkey"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
ACCOUNT = {"status": "trialing", "active": True, "checks_today": 0, "daily_limit": 24}
ANSWER = {
    "level": "attention",
    "subject": "Check the garage door",
    "text": "Garage: the garage door looks OPEN.",
    "cameras": [
        {"name": "Garage", "item": "garage", "verdict": "attention", "state": "open"},
        {"name": "Gate", "item": "gate", "verdict": "unknown", "state": None, "reason": "no picture"},
    ],
    "checked_at": "2026-11-18T03:00:00+00:00",
}


def test_helpers():
    assert parse_time("21:30:00") == (21, 30)
    assert parse_time("bad") == (22, 0)
    # 2026-11-17 is a Tuesday: tomorrow is Wednesday.
    assert is_pickup_eve(datetime(2026, 11, 17, 21, 0), ["wed"])
    assert not is_pickup_eve(datetime(2026, 11, 17, 21, 0), ["tue"])
    opts = {"garage_cameras": ["camera.g"], "gate_cameras": ["camera.x"], "bin_cameras": ["camera.b"]}
    assert cameras_to_check(opts, False) == [("camera.g", "garage"), ("camera.x", "gate")]
    assert ("camera.b", "bins") in cameras_to_check(opts, True)


async def test_config_flow_bad_then_good_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/ha/v1/account", json=ACCOUNT)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "wrong"})
    assert result["errors"] == {"base": "invalid_key"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": KEY})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"api_key": KEY}


async def test_config_flow_rejected_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/ha/v1/account", status=401, json={"message": "nope"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": KEY})
    assert result["errors"] == {"base": "invalid_key"}


async def _setup(hass, options):
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": KEY}, options=options, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_flow_validates(hass: HomeAssistant):
    entry = await _setup(hass, {"check_time": "22:00:00", "notify_when": "problems"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"garage_cameras": [f"camera.c{i}" for i in range(7)], "check_time": "21:00:00", "notify_when": "problems"},
    )
    assert result["errors"] == {"base": "too_many_cameras"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"garage_cameras": ["camera.g"], "check_time": "21:00:00", "notify_service": "notify.nope", "notify_when": "problems"},
    )
    assert result["errors"] == {"notify_service": "unknown_notify"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"garage_cameras": ["camera.g"], "check_time": "21:00:00", "notify_when": "problems"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["check_time"] == "21:00:00"


async def test_check_now_end_to_end(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.post(f"{BASE}/ha/v1/check", json=ANSWER)
    notes = async_mock_service(hass, "notify", "mobile_app_phone")
    events = []
    hass.bus.async_listen(EVENT_RESULT, lambda e: events.append(e))
    hass.states.async_set("camera.garage", "idle", {"friendly_name": "Garage"})
    hass.states.async_set("camera.gate", "idle", {"friendly_name": "Gate"})
    await _setup(hass, {
        "garage_cameras": ["camera.garage"], "gate_cameras": ["camera.gate"], "bin_cameras": [],
        "check_time": "22:00:00", "notify_service": "mobile_app_phone", "notify_when": "problems",
    })

    async def fake_image(hass_, entity_id, timeout=10, width=None, height=None):
        if entity_id == "camera.gate":
            raise HomeAssistantError("offline")
        return Image("image/jpeg", JPEG)

    with patch("custom_components.night_check.async_get_image", side_effect=fake_image):
        await hass.services.async_call("button", "press", {"entity_id": "button.night_check_check_now"}, blocking=True)
        await hass.async_block_till_done()

    sent = aioclient_mock.mock_calls[-1][2]["cameras"]
    assert sent[0]["name"] == "Garage" and sent[0]["item"] == "garage" and "image" in sent[0]
    assert sent[1]["error"] == "unavailable" and "image" not in sent[1]

    assert hass.states.get("sensor.night_check_result").state == "attention"
    assert hass.states.get("sensor.night_check_result").attributes["subject"] == "Check the garage door"
    assert hass.states.get("binary_sensor.night_check_needs_attention").state == "on"
    assert hass.states.get("sensor.night_check_last_check").state.startswith("2026-11-18T03:00")
    assert len(events) == 1 and events[0].data["manual"] is True
    assert notes == []  # manual checks never notify the phone


async def test_scheduled_check_notifies(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.post(f"{BASE}/ha/v1/check", json=ANSWER)
    notes = async_mock_service(hass, "notify", "mobile_app_phone")
    hass.states.async_set("camera.garage", "idle", {"friendly_name": "Garage"})
    entry = await _setup(hass, {
        "garage_cameras": ["camera.garage"], "check_time": "22:00:00",
        "notify_service": "mobile_app_phone", "notify_when": "problems",
    })
    with patch("custom_components.night_check.async_get_image", return_value=Image("image/jpeg", JPEG)):
        await entry.runtime_data.async_run(manual=False)
        await hass.async_block_till_done()
    assert len(notes) == 1
    assert notes[0].data["title"] == "Check the garage door"


async def test_inactive_and_offline(hass: HomeAssistant, aioclient_mock):
    hass.states.async_set("camera.garage", "idle", {"friendly_name": "Garage"})
    entry = await _setup(hass, {"garage_cameras": ["camera.garage"], "check_time": "22:00:00", "notify_when": "problems"})
    with patch("custom_components.night_check.async_get_image", return_value=Image("image/jpeg", JPEG)):
        aioclient_mock.post(f"{BASE}/ha/v1/check", status=402, json={"message": "renew"})
        await entry.runtime_data.async_run(manual=True)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.night_check_result").state == "inactive"

        aioclient_mock.clear_requests()
        aioclient_mock.post(f"{BASE}/ha/v1/check", status=500, json={})
        await entry.runtime_data.async_run(manual=True)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.night_check_result").state == "unknown"
        assert hass.states.get("binary_sensor.night_check_needs_attention").state == "off"


async def test_bad_key_starts_reauth(hass: HomeAssistant, aioclient_mock):
    hass.states.async_set("camera.garage", "idle", {"friendly_name": "Garage"})
    entry = await _setup(hass, {"garage_cameras": ["camera.garage"], "check_time": "22:00:00", "notify_when": "problems"})
    aioclient_mock.post(f"{BASE}/ha/v1/check", status=401, json={"message": "bad"})
    with patch("custom_components.night_check.async_get_image", return_value=Image("image/jpeg", JPEG)):
        await entry.runtime_data.async_run(manual=True)
        await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
