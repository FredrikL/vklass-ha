"""Constants for the Vklass integration."""

from datetime import timedelta

DOMAIN = "vklass"

# Be gentle with an unofficial scrape: hourly is plenty for a school schedule.
UPDATE_INTERVAL = timedelta(hours=1)
# How far ahead to fetch; must cover a school break so "next school day" resolves.
LOOKAHEAD_DAYS = 21
# Tests and homework are listed this many days ahead.
ASSIGNMENT_DAYS = 14
