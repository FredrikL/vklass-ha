"""Exercise the vklass library against the real service.

    VKLASS_USER=... VKLASS_PASS=... .venv/bin/python scripts/live_check.py
"""

import asyncio
import os
import sys

import aiohttp

from vklass import VklassClient, VklassError


async def main() -> None:
    user, password = os.environ.get("VKLASS_USER"), os.environ.get("VKLASS_PASS")
    if not user or not password:
        sys.exit("set VKLASS_USER and VKLASS_PASS")

    async with aiohttp.ClientSession() as session:
        client = VklassClient(session, user, password)
        children = await client.get_children()
        print("children:", [c.name for c in children])
        for child in children:
            events = await client.get_upcoming_events(child, days=21)
            print(f"\n{child.name}: {len(events)} events in the next 21 days")
            for e in events[:8]:
                flag = " [CANCELLED]" if e.cancelled else ""
                print(f"  {e.start:%a %d/%m %H:%M} {e.kind.value:10} {e.title}{flag}")


try:
    asyncio.run(main())
except VklassError as err:
    sys.exit(f"{type(err).__name__}: {err}")
