"""Async client for the Vklass guardian web UI.

Vklass has no public API, so this logs in like a browser and reads the same
endpoints the guardian SPA uses. See docs/api-notes.md.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
from yarl import URL

from .exceptions import (
    VklassAuthError,
    VklassConnectionError,
    VklassParseError,
)
from .models import Child, Event, LunchDay
from .parsing import (
    parse_children,
    parse_events,
    parse_lunches,
    parse_verification_token,
)

AUTH_URL = "https://auth.vklass.se"
BASE_URL = "https://custodian.vklass.se"
DEFAULT_TZ = ZoneInfo("Europe/Stockholm")
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class _SessionExpired(Exception):
    """Internal: the server wants us to log in again."""


class VklassClient:
    """Guardian-side Vklass client.

    Pass a session with its own cookie jar (in Home Assistant, one from
    ``async_create_clientsession``) so login cookies are not shared with
    other integrations. The client logs in lazily and transparently logs in
    again once if the session has expired.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        auth_url: str = AUTH_URL,
        base_url: str = BASE_URL,
        tz: tzinfo = DEFAULT_TZ,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._auth_url = auth_url.rstrip("/")
        self._base_url = base_url.rstrip("/")
        self._tz = tz
        self._logged_in = False
        self._login_lock = asyncio.Lock()

    async def login(self) -> None:
        """Log in. Raises VklassAuthError if the credentials are rejected."""
        async with self._login_lock:
            await self._login()

    async def _login(self) -> None:
        try:
            async with self._session.get(
                f"{self._auth_url}/credentials", timeout=_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                token = parse_verification_token(await resp.text())
            async with self._session.post(
                f"{self._auth_url}/credentials/signin",
                data={
                    "__RequestVerificationToken": token,
                    "Username": self._username,
                    "Password": self._password,
                    "RememberMe": "false",
                },
                allow_redirects=False,
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    # The form is re-rendered on bad credentials.
                    raise VklassAuthError("invalid username or password")
                if resp.status not in (301, 302, 303):
                    raise VklassConnectionError(
                        f"unexpected sign-in status {resp.status}"
                    )
                location = resp.headers.get("Location")
                if not location:
                    raise VklassConnectionError("sign-in redirect had no Location")
                next_url = resp.url.join(URL(location))
            await self._follow_login_redirects(next_url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VklassConnectionError(str(err)) from err
        self._logged_in = True

    async def _follow_login_redirects(self, url: URL) -> None:
        """Walk the post-login redirect chain so every host gets its cookies.

        Vklass clears cookies (LogoutRedirectURL, _vk-RememberMe) with expired,
        empty Set-Cookie headers. aiohttp's jar keeps those and sends them back,
        which makes auth.vklass.se/process answer 403, so drop empty cookies
        before every hop.
        """
        for _ in range(10):
            self._session.cookie_jar.clear(lambda cookie: not cookie.value)
            async with self._session.get(
                url, allow_redirects=False, timeout=_TIMEOUT
            ) as resp:
                location = resp.headers.get("Location")
                if resp.status in (301, 302, 303, 307, 308) and location:
                    url = resp.url.join(URL(location))
                    continue
                resp.raise_for_status()
                return
        raise VklassConnectionError("too many redirects during login")

    async def _call(
        self, method: str, path: str, data: Optional[dict[str, str]] = None
    ) -> str:
        """Request a custodian path, logging in first or again as needed."""
        for attempt in (1, 2):
            if not self._logged_in:
                await self.login()
            try:
                return await self._request(method, path, data)
            except _SessionExpired:
                self._logged_in = False
                if attempt == 2:
                    raise VklassAuthError("session rejected after re-login") from None
        raise AssertionError("unreachable")

    async def _request(
        self, method: str, path: str, data: Optional[dict[str, str]]
    ) -> str:
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                data=data,
                headers={"X-Requested-With": "XMLHttpRequest"},
                allow_redirects=False,
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308, 401, 403):
                    raise _SessionExpired
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VklassConnectionError(str(err)) from err

    async def get_children(self) -> list[Child]:
        html = await self._call("GET", "/Calendar/Schedule/")
        children = parse_children(html)
        if not children:
            raise VklassParseError("no children found on schedule page")
        return children

    async def get_events(
        self, child: Child, start: datetime, end: datetime
    ) -> list[Event]:
        body = await self._call(
            "POST",
            "/Events/FullCalendar",
            {
                "students": str(child.id),
                "start": start.replace(tzinfo=None).isoformat(),
                "end": end.replace(tzinfo=None).isoformat(),
            },
        )
        try:
            data = json.loads(body)
        except ValueError as err:
            raise VklassParseError("calendar response is not JSON") from err
        return parse_events(data, child.id, self._tz)

    async def get_upcoming_events(
        self, child: Child, days: int = 14, today: Optional[date] = None
    ) -> list[Event]:
        """Events from the start of today through `days` days ahead."""
        day = today or datetime.now(self._tz).date()
        start = datetime(day.year, day.month, day.day)
        return await self.get_events(child, start, start + timedelta(days=days))

    async def get_lunches(
        self, children: list[Child], today: Optional[date] = None
    ) -> dict[int, list[LunchDay]]:
        """School lunch menus per child id, for the days the welcome page lists.

        Vklass shows roughly today plus the next four weekdays, and only days
        where the school has published a menu. Cards are matched to children by
        name; a child whose card is missing gets an empty list.
        """
        day = today or datetime.now(self._tz).date()
        cards = parse_lunches(await self._call("GET", "/Home/Welcome"), day)
        by_name = {}
        for name, lunches in cards:
            by_name.setdefault(name, lunches)  # first card wins on duplicate names
        return {child.id: by_name.get(child.name, []) for child in children}
