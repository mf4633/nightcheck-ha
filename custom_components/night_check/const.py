"""Constants for Night Check."""

DOMAIN = "night_check"
DEFAULT_API_BASE = "https://nightcheck.hydrocomplete.com"

CONF_API_KEY = "api_key"
CONF_API_BASE = "api_base"  # tests / self-hosting only; not shown in the UI
CONF_GARAGE = "garage_cameras"
CONF_GATE = "gate_cameras"
CONF_BINS = "bin_cameras"
CONF_CHECK_TIME = "check_time"
CONF_PICKUP_DAYS = "pickup_days"
CONF_NOTIFY = "notify_service"
CONF_NOTIFY_WHEN = "notify_when"

DEFAULT_CHECK_TIME = "22:00:00"
NOTIFY_ALWAYS = "always"
NOTIFY_PROBLEMS = "problems"

# Python weekday numbers (Monday = 0), as strings for the selector.
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

ITEM_FOR_OPTION = {CONF_GARAGE: "garage", CONF_GATE: "gate", CONF_BINS: "bins"}

LEVELS = ["ok", "attention", "unknown", "inactive"]
EVENT_RESULT = "night_check_result"
SIGNAL_UPDATE = "night_check_update_{}"

# Pictures are scaled to this width before they are sent (smaller upload, same answer).
IMAGE_WIDTH = 1280
IMAGE_TIMEOUT = 20
