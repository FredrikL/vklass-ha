"""Constants for the Vklass integration."""

from datetime import timedelta

DOMAIN = "vklass"

# Be gentle with an unofficial scrape: schedules rarely change, so twice a day is
# plenty. Sensors recompute "today"/"next day" from the fetched events, so they do
# not go stale between fetches.
UPDATE_INTERVAL = timedelta(hours=12)
# How far ahead to fetch; must cover a school break so "next school day" resolves.
LOOKAHEAD_DAYS = 21
# Tests and homework are listed this many days ahead.
ASSIGNMENT_DAYS = 14
