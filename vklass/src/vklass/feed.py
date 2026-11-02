"""The per-child calendar feed ("Prenumerera på schema") that Vklass publishes.

The feed is an iCalendar file at ``https://cal.vklass.se/<guid>.ics`` meant for
calendar apps, so it needs no login. The GUID in the URL is the only secret.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time, timezone, tzinfo
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

from yarl import URL

from .exceptions import VklassInvalidUrl, VklassParseError
from .models import Event, EventKind
from .schedule import AssignmentType, classify_assignment

FEED_HOST = "cal.vklass.se"
_PATH_RE = re.compile(
    r"^/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.ics$",
    re.IGNORECASE,
)


def _feed_guid(url: str) -> str:
    """The GUID from a feed URL; raises VklassInvalidUrl if it is not one."""
    parsed = URL(url.strip().replace("webcal://", "https://", 1))
    match = _PATH_RE.match(parsed.path)
    if parsed.host != FEED_HOST or not match:
        raise VklassInvalidUrl(
            f"expected a link like https://{FEED_HOST}/<id>.ics from "
            "Vklass's 'Prenumerera på schema'"
        )
    return match.group(1).lower()


def normalize_feed_url(url: str) -> str:
    """Canonical feed URL for a pasted link (``webcal://`` links work too).

    Only the Vklass calendar host is accepted, so the integration cannot be
    pointed at arbitrary addresses. Lessons are always included, since without
    them the feed holds nothing but tests and homework.
    """
    try:
        guid = _feed_guid(url)
    except ValueError as err:  # yarl raises ValueError for malformed URLs
        raise VklassInvalidUrl(str(err)) from err
    return f"https://{FEED_HOST}/{guid}.ics?includeLectures=true"


def feed_id(url: str) -> str:
    """A stable identifier for a feed that does not reveal its secret URL."""
    return hashlib.sha256(_feed_guid(url).encode()).hexdigest()[:16]


# Vklass writes Windows zone names. Anything unknown falls back to the caller's zone.
_WINDOWS_ZONES = {"W. Europe Standard Time": "Europe/Stockholm"}

_LINE_RE = re.compile(r'^([A-Za-z0-9-]+)((?:;[^:;=]+=(?:"[^"]*"|[^:;"]*))*):(.*)$')
_DUE_TIME_RE = re.compile(r"\bkl:?\s*(\d{1,2}):(\d{2})")


def _iter_vevents(text: str) -> Iterator[dict[str, tuple[dict[str, str], str]]]:
    """Raw properties of every VEVENT; everything else (timezones, ...) is skipped."""
    props: Optional[dict[str, tuple[dict[str, str], str]]] = None
    for line in re.sub(r"\r?\n[ \t]", "", text).splitlines():
        if line == "BEGIN:VEVENT":
            props = {}
        elif line == "END:VEVENT":
            if props is not None:
                yield props
            props = None
        elif props is not None:
            match = _LINE_RE.match(line)
            if match:
                params = {}
                for part in match.group(2).split(";"):
                    key, sep, val = part.partition("=")
                    if sep:
                        params[key.upper()] = val
                # First occurrence wins, so a nested VALARM cannot override the event.
                props.setdefault(match.group(1).upper(), (params, match.group(3)))


def _unescape(value: str) -> str:
    return re.sub(
        r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value
    )


def _zone(tzid: Optional[str], default: tzinfo) -> tzinfo:
    if not tzid:
        return default
    try:
        return ZoneInfo(_WINDOWS_ZONES.get(tzid, tzid))
    except (KeyError, ValueError, OSError):
        return default


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as err:
        raise VklassParseError(f"unexpected date format: {value!r}") from err


def _parse_datetime(value: str, params: dict[str, str], tz: tzinfo) -> datetime:
    try:
        if value.endswith("Z"):
            parsed = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S")
            return parsed.replace(tzinfo=timezone.utc).astimezone(tz)
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError as err:
        raise VklassParseError(f"unexpected time format: {value!r}") from err
    return parsed.replace(tzinfo=_zone(params.get("TZID"), tz)).astimezone(tz)


def _is_all_day(params: dict[str, str], value: str) -> bool:
    return params.get("VALUE", "").upper() == "DATE" or len(value) == 8


def _assignment_start(day: date, description: str, tz: tzinfo) -> datetime:
    """Tests and homework are all-day entries; the due time is in the description."""
    match = _DUE_TIME_RE.search(description)
    due = time(0, 0)
    if match and int(match.group(1)) < 24 and int(match.group(2)) < 60:
        due = time(int(match.group(1)), int(match.group(2)))
    return datetime.combine(day, due, tzinfo=tz)


def _lesson_fields(summary: str, location: str) -> tuple[str, str, str]:
    """(title, code, location) from the three-line summary Vklass writes.

    ``Svenska (9A/SV)\\nSV \\nABC`` is title, short code and teacher. The room is
    in LOCATION; the combined ``room | teacher`` matches the old calendar view.
    """
    lines = [line.strip() for line in summary.split("\n")]
    title = lines[0]
    code = lines[1] if len(lines) > 1 else ""
    teacher = lines[2] if len(lines) > 2 else ""
    return title, code, " | ".join(part for part in (location.strip(), teacher) if part)


def _event(props: dict[str, tuple[dict[str, str], str]], child_id: str, tz: tzinfo) -> Event:
    def text(name: str) -> str:
        return _unescape(props[name][1]) if name in props else ""

    if "DTSTART" not in props:
        raise VklassParseError("calendar event has no DTSTART")
    start_params, start_value = props["DTSTART"]
    summary = text("SUMMARY")
    uid_value = text("UID")
    cancelled = text("STATUS").upper() == "CANCELLED"
    all_day = _is_all_day(start_params, start_value)

    if all_day:
        title = summary.split("\n")[0].strip()
        start = _assignment_start(_parse_date(start_value[:8]), text("DESCRIPTION"), tz)
        end = None
        code = location = ""
        is_assignment = (
            "ExamInfo" in text("URL")
            or classify_assignment(title) is not AssignmentType.OTHER
        )
        kind = EventKind.ASSIGNMENT if is_assignment else EventKind.OTHER
    else:
        title, code, location = _lesson_fields(summary, text("LOCATION"))
        start = _parse_datetime(start_value, start_params, tz)
        end = None
        if "DTEND" in props:
            end = _parse_datetime(props["DTEND"][1], props["DTEND"][0], tz)
        kind = EventKind.LESSON

    if not uid_value:
        digest = hashlib.sha1(f"{start.isoformat()}|{title}".encode()).hexdigest()
        uid_value = digest[:16]
    return Event(
        uid=f"{child_id}-{uid_value}",
        child_id=child_id,
        kind=kind,
        title=title,
        code=code,
        start=start,
        end=end,
        all_day=all_day,
        location=location,
        cancelled=cancelled,
        substitute=False,
    )


def parse_feed(text: str, child_id: str, tz: tzinfo) -> list[Event]:
    """Events in a feed, soonest first."""
    if "BEGIN:VCALENDAR" not in text:
        raise VklassParseError("response is not a calendar feed")
    events = [_event(props, child_id, tz) for props in _iter_vevents(text)]
    events.sort(key=lambda e: e.start)
    return events
