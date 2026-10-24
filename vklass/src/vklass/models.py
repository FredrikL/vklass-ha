"""Data models returned by the Vklass client."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Child:
    id: int
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


# eventType values observed in /Events/FullCalendar responses.
EVENT_KINDS = {
    1: EventKind.LESSON,
    2: EventKind.ASSIGNMENT,
    8: EventKind.HOLIDAY,
}


@dataclass(frozen=True)
class Event:
    # Vklass gives lessons no stable id, so this is derived from child+start+title.
    uid: str
    child_id: int
    kind: EventKind
    title: str
    # Short code such as "SV" or "IDH"; empty for non-lessons.
    code: str
    start: datetime
    # None for assignments (due at `start`).
    end: Optional[datetime]
    all_day: bool
    location: str
    cancelled: bool
    substitute: bool
