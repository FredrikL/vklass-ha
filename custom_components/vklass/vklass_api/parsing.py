"""Pure functions that turn Vklass responses into models."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, tzinfo
from html.parser import HTMLParser
from typing import Any, Optional

from .exceptions import VklassParseError
from .models import EVENT_KINDS, Child, Event, EventKind, LunchDay

_TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'
    r'|value="([^"]+)"[^>]*name="__RequestVerificationToken"'
)
# `\s` keeps this from matching `disabled-text=""`, which precedes it.
# Each child is a <vkau-checkable-list-item text="Name"> wrapping the checkbox.
_CHILD_RE = re.compile(
    r'\stext="([^"]*)"[^>]*>\s*<input[^>]*name="SelectedStudentIds"[^>]*value="(\d+)"'
)


def parse_verification_token(html: str) -> str:
    m = _TOKEN_RE.search(html)
    if not m:
        raise VklassParseError("no __RequestVerificationToken on login page")
    return m.group(1) or m.group(2)


def parse_children(html: str) -> list[Child]:
    return [Child(id=int(sid), name=name) for name, sid in _CHILD_RE.findall(html)]


def _parse_time(value: Optional[str], tz: tzinfo) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError as err:
        raise VklassParseError(f"unexpected time format: {value!r}") from err


def _uid(child_id: int, start: str, title: str) -> str:
    digest = hashlib.sha1(f"{child_id}|{start}|{title}".encode()).hexdigest()
    return f"{child_id}-{digest[:16]}"


def parse_event(raw: dict[str, Any], child_id: int, tz: tzinfo) -> Event:
    try:
        start = _parse_time(raw["start"], tz)
        title = raw["title"]
    except KeyError as err:
        raise VklassParseError(f"event missing field {err}") from err
    if start is None:
        raise VklassParseError("event has no start time")
    return Event(
        uid=_uid(child_id, raw["start"], title),
        child_id=child_id,
        kind=EVENT_KINDS.get(raw.get("eventType"), EventKind.OTHER),
        title=title,
        code=raw.get("text") or "",
        start=start,
        end=_parse_time(raw.get("end"), tz),
        all_day=bool(raw.get("allDay")),
        location=raw.get("location") or "",
        cancelled=bool(raw.get("cancelled")),
        substitute=bool(raw.get("isSubstitute")),
    )


def parse_events(data: Any, child_id: int, tz: tzinfo) -> list[Event]:
    if not isinstance(data, list):
        raise VklassParseError("calendar response is not a JSON array")
    events = [parse_event(raw, child_id, tz) for raw in data]
    events.sort(key=lambda e: e.start)
    return events


_WEEKDAYS = {
    "måndag": 0,
    "tisdag": 1,
    "onsdag": 2,
    "torsdag": 3,
    "fredag": 4,
    "lördag": 5,
    "söndag": 6,
}


class _WelcomeParser(HTMLParser):
    """Collects (child name, [(day label, [dishes])]) from the welcome page.

    Markup (Aurelia-rendered, verified 2026-10): one `div.vk-student-card` per
    child with `h2.vk-student-card-header__text`; inside, one
    `div.vk-student-card__day` per day with an `h3` label and an optional
    `div.vk-student-card__day__food` holding `li` dishes.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, list[tuple[str, list[str]]]]] = []
        self._name = ""
        self._days: list[tuple[str, list[str]]] = []
        self._capture: Optional[str] = None  # "name" | "label" | "dish"
        self._buf: list[str] = []
        self._label = ""
        self._dishes: list[str] = []
        self._in_card = False
        self._in_day = False
        self._in_food = False
        # Open-div depth at which the current card/day/food started.
        self._depth = 0
        self._card_depth = self._day_depth = self._food_depth = -1

    def _flush_card(self) -> None:
        self._flush_day()
        if self._in_card:
            self.cards.append((self._name, self._days))
        self._in_card = False
        self._name, self._days = "", []

    def _flush_day(self) -> None:
        if self._in_day:
            self._days.append((self._label, self._dishes))
        self._in_day = self._in_food = False
        self._label, self._dishes = "", []

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div":
            self._depth += 1
            if "vk-student-card" in classes:
                self._flush_card()
                self._in_card, self._card_depth = True, self._depth
            elif "vk-student-card__day" in classes and self._in_card:
                self._flush_day()
                self._in_day, self._day_depth = True, self._depth
            elif "vk-student-card__day__food" in classes and self._in_day:
                self._in_food, self._food_depth = True, self._depth
        elif tag == "h2" and "vk-student-card-header__text" in classes:
            self._capture, self._buf = "name", []
        elif tag == "h3" and self._in_day:
            self._capture, self._buf = "label", []
        elif tag == "li" and self._in_food:
            self._capture, self._buf = "dish", []

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "div":
            if self._in_food and self._depth == self._food_depth:
                self._in_food = False
            if self._in_day and self._depth == self._day_depth:
                self._flush_day()
            if self._in_card and self._depth == self._card_depth:
                self._flush_card()
            self._depth -= 1
        elif tag in ("h2", "h3", "li") and self._capture:
            text = " ".join("".join(self._buf).split())
            if self._capture == "name":
                self._name = text
            elif self._capture == "label":
                self._label = text.casefold()
            elif text:
                self._dishes.append(text)
            self._capture = None

    def close(self):
        super().close()
        self._flush_card()


def _resolve_day_dates(labels: list[str], today: date) -> list[Optional[date]]:
    """Turn 'Idag', 'måndag', ... into dates; weekday names are relative.

    Days are listed in order, so each weekday name is the first such weekday
    after the previous day. Unknown labels give None and don't advance.
    """
    dates: list[Optional[date]] = []
    previous = today - timedelta(days=1)
    for label in labels:
        if label in ("idag", "i dag"):
            current: Optional[date] = today
        elif label in ("imorgon", "i morgon"):
            current = today + timedelta(days=1)
        elif label in _WEEKDAYS:
            current = previous + timedelta(days=1)
            while current.weekday() != _WEEKDAYS[label]:
                current += timedelta(days=1)
        else:
            current = None
        dates.append(current)
        if current:
            previous = current
    return dates


def parse_lunches(html: str, today: date) -> list[tuple[str, list[LunchDay]]]:
    """Per child card, in page order: (child name, days that have a menu)."""
    parser = _WelcomeParser()
    parser.feed(html)
    parser.close()
    if not parser.cards:
        raise VklassParseError("no student cards on the welcome page")
    result = []
    for name, days in parser.cards:
        dates = _resolve_day_dates([label for label, _ in days], today)
        lunches = [
            LunchDay(day, dishes)
            for day, (_, dishes) in zip(dates, days)
            if day and dishes
        ]
        result.append((name, lunches))
    return result
