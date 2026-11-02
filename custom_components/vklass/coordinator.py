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

from .const import ASSIGNMENT_DAYS, DOMAIN, UPDATE_INTERVAL
from .vklass_api import (
    Assignment,
    Child,
    Event,
    LunchDay,
    SchoolDay,
    VklassAuthError,
    VklassClient,
    VklassError,
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
    # Days the school has published a menu for (empty without a lunch link).
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


class VklassCoordinator(DataUpdateCoordinator[ChildData]):
    """Fetches one child's calendar feed (and the school menu, if configured)."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: VklassClient,
        child: Child,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {child.name}",
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.child = child
        self._lunches: list[LunchDay] = []

    async def _async_update_data(self) -> ChildData:
        try:
            events = await self.client.get_events(self.child)
        except VklassAuthError as err:
            # The calendar link was revoked or is wrong: ask for a new one.
            raise ConfigEntryAuthFailed(str(err)) from err
        except VklassError as err:
            raise UpdateFailed(str(err)) from err
        return ChildData(self.child, events, await self._get_lunches())

    async def _get_lunches(self) -> list[LunchDay]:
        """Lunch is a nice-to-have; never fail the schedule on it.

        If Skolmaten is down, the last menu stays, and stale days drop out by date.
        """
        try:
            self._lunches = await self.client.get_lunches()
        except VklassError as err:
            _LOGGER.warning("Could not read the lunch menu: %s", err)
        return self._lunches


VklassConfigEntry = ConfigEntry[VklassCoordinator]
