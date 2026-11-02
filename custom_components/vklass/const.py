"""Constants for the Vklass integration."""

from datetime import timedelta

DOMAIN = "vklass"

# Optional Skolmaten school menu; the child's name and calendar link use the
# standard CONF_NAME and CONF_URL keys.
CONF_LUNCH_URL = "lunch_url"

# Schedules rarely change, so twice a day is plenty. Sensors recompute "today"/"next
# day" from the fetched events, so they do not go stale between fetches.
UPDATE_INTERVAL = timedelta(hours=12)
# Tests and homework are listed this many days ahead.
ASSIGNMENT_DAYS = 14
