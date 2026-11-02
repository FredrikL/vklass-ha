"""School lunch menus from Skolmaten's public RSS feed.

Vklass no longer exposes the menu to anything but a browser session, so lunch
comes from skolmaten.se, which most schools publish their menu through. The feed
is per school, not per child.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from yarl import URL

from .exceptions import VklassInvalidUrl, VklassParseError
from .models import LunchDay

LUNCH_HOSTS = ("skolmaten.se", "www.skolmaten.se")
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def normalize_lunch_url(url: str) -> str:
    """Canonical RSS link for a Skolmaten school.

    Accepts the RSS link itself (``/api/4/rss/week/<school>``) or the school's
    page (``skolmaten.se/<school>``). Only skolmaten.se is accepted.
    """
    try:
        parsed = URL(url.strip())
    except ValueError as err:
        raise VklassInvalidUrl(str(err)) from err
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.host not in LUNCH_HOSTS or parsed.scheme not in ("http", "https"):
        raise VklassInvalidUrl("expected a link on skolmaten.se")
    if parts[:3] == ["api", "4", "rss"] and len(parts) == 5:
        slug = parts[4]
    elif len(parts) == 1:
        slug = parts[0]
    else:
        raise VklassInvalidUrl(
            "expected a link like https://skolmaten.se/<school> "
            "or https://skolmaten.se/api/4/rss/week/<school>"
        )
    if not _SLUG_RE.match(slug):
        raise VklassInvalidUrl("unexpected school name in the Skolmaten link")
    return f"https://skolmaten.se/api/4/rss/week/{slug}?locale=sv"


def _dishes(description: str) -> list[str]:
    """Dishes are separated by ``<br/>`` (after a trailing comma)."""
    dishes = []
    for part in _BR_RE.split(description):
        text = " ".join(_TAG_RE.sub("", part).split()).strip(" ,")
        if text:
            dishes.append(text)
    return dishes


def parse_lunches(xml_text: str) -> list[LunchDay]:
    """Days that have a menu, oldest first. Days without dishes are left out."""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError as err:
        raise VklassParseError("lunch response is not valid XML") from err
    if root.tag != "rss":
        raise VklassParseError("lunch response is not an RSS feed")
    days = {}
    for item in root.iter("item"):
        pub = item.findtext("pubDate")
        if not pub:
            raise VklassParseError("lunch item has no pubDate")
        try:
            day = parsedate_to_datetime(pub).date()
        except (TypeError, ValueError) as err:
            raise VklassParseError(f"unexpected lunch date: {pub!r}") from err
        dishes = _dishes(item.findtext("description") or "")
        if dishes:
            days[day] = dishes
    return [LunchDay(day, days[day]) for day in sorted(days)]
