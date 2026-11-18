# Night Check for Home Assistant

An evening reminder if the garage door or gate is open, or the bins aren't out the night before pickup,
from the cameras you already have in Home Assistant.

At the time you choose, Home Assistant takes one still picture from each camera you picked and sends it to the
Night Check service, which reads it and answers *open*, *closed*, *out* or *not out*. Pictures are read once
and not kept. The answer shows up as sensors, and you can have it sent to your phone.

Works with any camera Home Assistant can show: Reolink, UniFi Protect, Ring, Nest, Eufy, Amcrest, Wyze
(through a bridge), generic RTSP/ONVIF cameras and more.

Night Check is a paid service with a free trial: sign up at
<https://nightcheck.hydrocomplete.com/home-assistant> to get a key.

> Night Check is a reminder, not a security system. Each answer is an AI's reading of one picture and can be wrong.

## Install

1. In HACS, open the menu &rarr; **Custom repositories**, add `https://github.com/mf4633/nightcheck-ha` as type **Integration**.
2. Install **Night Check** and restart Home Assistant.
3. **Settings &rarr; Devices & services &rarr; Add integration &rarr; Night Check**, and paste your key.
4. Open the integration's **Configure** and choose:
   - the cameras that show a garage door, a gate, and the bins at the curb (up to 6 in all);
   - the check time (default 22:00);
   - your trash pickup days (bins are checked only on the evening before);
   - optionally a notify service for your phone (for example `mobile_app_my_phone`) and whether to be told
     every night or only when something needs a look.

## What you get

| Entity | Meaning |
|---|---|
| `sensor.night_check_result` | `ok`, `attention`, `unknown` (couldn't check) or `inactive` (subscription). Attributes: `subject`, `text`, `cameras` (per-camera answer), `checked_at`. |
| `binary_sensor.night_check_needs_attention` | On when the last check found something open or the bins not out. |
| `sensor.night_check_last_check` | When the last check ran. |
| `button.night_check_check_now` | Check straight away (bins included, no phone notification). |

Every check also fires the event `night_check_result`, for your own automations.

### Example: flash the porch light if the garage is open

```yaml
automation:
  - alias: Garage left open
    triggers:
      - trigger: state
        entity_id: binary_sensor.night_check_needs_attention
        to: "on"
    actions:
      - action: light.turn_on
        target: { entity_id: light.porch }
        data: { flash: long }
```

## Privacy

Only the pictures from the cameras you choose are sent, once per check. They are not stored. See the
[privacy notice](https://nightcheck.hydrocomplete.com/privacy.html#home-assistant).

## Development

Tests use `pytest-homeassistant-custom-component`, which needs Linux (Home Assistant doesn't run on Windows):

```sh
uv venv --python 3.13 ~/venvs/nightcheck-ha
uv pip install --python ~/venvs/nightcheck-ha/bin/python pytest-homeassistant-custom-component PyTurboJPEG
~/venvs/nightcheck-ha/bin/python -m pytest -q
```
