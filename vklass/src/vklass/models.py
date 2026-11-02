"""Data models returned by the Vklass client."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Child:
    # Chosen by the caller (Home Assistant uses the config entry id); it must not
    # contain the secret calendar URL, since it ends up in entity unique ids.
    id: str
    name: str


@dataclass(frozen=True)
class LunchDay:
    date: date
    dishes: list[str]


class EventKind(enum.Enum):
    LESSON = "lesson"
    ASSIGNMENT = "assignment"
    HOLIDAY = "holiday"
    OTHER = "other"


@dataclass(frozen=True)
class Event:
    # The calendar feed's own event id, prefixed with the child id.
    uid: str
    child_id: str
    kind: EventKind
    title: str
    # Short code such as "SV" or "IDH"; empty for non-lessons.
    code: str
    start: datetime
    # None for assignments (due at `start`, taken from the description when given).
    end: Optional[datetime]
    all_day: bool
    location: str
    cancelled: bool
    substitute: bool
