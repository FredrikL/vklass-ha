"""Async client for the Vklass calendar feed and Skolmaten lunch menus.

Vklass has no public API, and its guardian site sits behind bot protection, so
this reads the per-child calendar subscription ("Prenumerera på schema") that
Vklass publishes for calendar apps. See docs/api-notes.md.
"""

from __future__ import annotations

import asyncio
from datetime import tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp

from .exceptions import (
    VklassAuthError,
    VklassConnectionError,
    VklassError,
)
from .feed import parse_feed
from .lunch import parse_lunches
from .models import Child, Event, LunchDay

DEFAULT_TZ = ZoneInfo("Europe/Stockholm")
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class VklassClient:
    """Reads one child's calendar feed and, optionally, a school's lunch menu.

    ``feed_url`` is the child's secret link; keep it out of logs. Use
    ``normalize_feed_url`` / ``normalize_lunch_url`` on user input first.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        feed_url: str,
        *,
        lunch_url: Optional[str] = None,
        tz: tzinfo = DEFAULT_TZ,
    ) -> None:
        self._session = session
        self._feed_url = feed_url
        self._lunch_url = lunch_url
        self._tz = tz

    @property
    def has_lunch(self) -> bool:
        return bool(self._lunch_url)

    async def _get(self, url: str, accept: str) -> str:
        try:
            async with self._session.get(
                url, headers={"Accept": accept}, timeout=_TIMEOUT
            ) as resp:
                if resp.status in (404, 410):
                    raise VklassAuthError("Vklass does not recognise this link")
                if resp.status == 403:
                    raise VklassConnectionError(
                        "request refused (403), possibly by bot protection"
                    )
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VklassConnectionError(type(err).__name__) from err

    async def get_events(self, child: Child) -> list[Event]:
        """Every event in the child's feed (about a month), soonest first."""
        body = await self._get(self._feed_url, "text/calendar")
        if not body.strip():
            # Vklass answers 200 with an empty body for a link it does not know.
            raise VklassAuthError("Vklass does not recognise this calendar link")
        if "BEGIN:VCALENDAR" not in body:
            raise VklassConnectionError(
                "response is not a calendar, possibly bot protection"
            )
        return parse_feed(body, child.id, self._tz)

    async def get_lunches(self) -> list[LunchDay]:
        """The school's published menus; empty when no lunch link is configured."""
        if not self._lunch_url:
            return []
        try:
            return parse_lunches(await self._get(self._lunch_url, "application/rss+xml"))
        except VklassAuthError as err:
            raise VklassError("Skolmaten does not know this school") from err
