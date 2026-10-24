"""Data update coordinator for Vklass."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import ASSIGNMENT_DAYS, DOMAIN, LOOKAHEAD_DAYS, UPDATE_INTERVAL
from .vklass_api import (
    Assignment,
    Child,
    LunchDay,
    SchoolDay,
    VklassAuthError,
    VklassClient,
    VklassError,
    VklassParseError,
    next_school_day,
    upcoming_assignments,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChildData:
    child: Child
    next_day: Optional[SchoolDay]
    assignments: list[Assignment]
    # Days the school has published a menu for (about today + 4 weekdays).
    lunches: list[LunchDay]


class VklassCoordinator(DataUpdateCoordinator[dict[int, ChildData]]):
    """Fetches every child's schedule and derives what the sensors show."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VklassClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[int, ChildData]:
        today = dt_util.now().date()
        try:
            children = await self.client.get_children()
            lunches = await self._get_lunches(children, today)
            data = {}
            for child in children:
                events = await self.client.get_upcoming_events(
                    child, days=LOOKAHEAD_DAYS, today=today
                )
                data[child.id] = ChildData(
                    child=child,
                    next_day=next_school_day(events, today),
                    assignments=upcoming_assignments(
                        events, today, days=ASSIGNMENT_DAYS
                    ),
                    lunches=lunches.get(child.id, []),
                )
            return data
        except VklassAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VklassError as err:
            raise UpdateFailed(str(err)) from err

    async def _get_lunches(self, children, today):
        """Lunch is a nice-to-have scraped from HTML; never fail the schedule on it."""
        try:
            return await self.client.get_lunches(children, today)
        except VklassParseError as err:
            _LOGGER.warning("Could not read lunch menu from Vklass: %s", err)
            return {}
