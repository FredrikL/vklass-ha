"""Exercise the vklass library against the real services.

    VKLASS_FEED_URL='https://cal.vklass.se/<id>.ics' \
    SKOLMATEN_URL='https://skolmaten.se/<school>' \
    .venv/bin/python scripts/live_check.py

VKLASS_FEED_URL is the secret link from Vklass's "Prenumerera på schema"; either
variable may be left out to check only the other.
"""

import asyncio
import os
import sys
from datetime import datetime

import aiohttp

from vklass import (
    Child,
    VklassClient,
    VklassError,
    normalize_feed_url,
    normalize_lunch_url,
    upcoming_assignments,
)
from vklass.client import DEFAULT_TZ


async def main() -> None:
    feed = os.environ.get("VKLASS_FEED_URL")
    lunch = os.environ.get("SKOLMATEN_URL")
    if not feed and not lunch:
        sys.exit("set VKLASS_FEED_URL and/or SKOLMATEN_URL")

    async with aiohttp.ClientSession() as session:
        client = VklassClient(
            session,
            normalize_feed_url(feed) if feed else "",
            lunch_url=normalize_lunch_url(lunch) if lunch else None,
        )
        if feed:
            events = await client.get_events(Child("live", "child"))
            print(f"{len(events)} events in the feed")
            for e in events[:8]:
                flag = " [CANCELLED]" if e.cancelled else ""
                print(f"  {e.start:%a %d/%m %H:%M} {e.kind.value:10} {e.title}{flag}")
            today = datetime.now(DEFAULT_TZ).date()
            print("\ntests and homework:")
            for a in upcoming_assignments(events, today, days=21):
                print(f"  {a.event.start:%a %d/%m %H:%M} {a.type.value:8} {a.event.title}")
        for day in await client.get_lunches():
            print(f"\nlunch {day.date:%a %d/%m}: " + " / ".join(day.dishes))


try:
    asyncio.run(main())
except VklassError as err:
    sys.exit(f"{type(err).__name__}: {err}")
