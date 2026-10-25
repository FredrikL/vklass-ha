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
    Event,
    LunchDay,
    SchoolDay,
    VklassAuthError,
    VklassClient,
    VklassError,
    VklassParseError,
    next_school_day,
    schedule_ahead,
    upcoming_assignments,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChildData:
    """Raw events from the last fetch; views are derived for the current date.

    Fetches are twelve hours apart, so computing "today" at read time keeps the
    next school day and the assignment countdown correct across midnight.
    """

    child: Child
    events: list[Event]
    # Days the school has published a menu for (about today + 4 weekdays).
    lunches: list[LunchDay]

    @property
    def next_day(self) -> Optional[SchoolDay]:
        return next_school_day(self.events, dt_util.now().date())

    @property
    def schedule(self) -> list[SchoolDay]:
        return schedule_ahead(self.events, dt_util.now().date())

    @property
    def assignments(self) -> list[Assignment]:
        return upcoming_assignments(
            self.events, dt_util.now().date(), days=ASSIGNMENT_DAYS
        )


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
                    events=events,
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
