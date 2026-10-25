"""Derived views over a list of events: next school day, tests and homework."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .models import Event, EventKind


class AssignmentType(enum.Enum):
    TEST = "test"
    HOMEWORK = "homework"
    SUBMISSION = "submission"
    OTHER = "other"


_TEST_RE = re.compile(r"\bprov\b", re.IGNORECASE)


def classify_assignment(title: str) -> AssignmentType:
    """Vklass has one 'Uppgift' event type; the kind is only in the title.

    Seen so far: "Prov Meteorologi", "Läxa i Fysik", "Inlämning: Offentlig konst".
    """
    lowered = title.casefold()
    if _TEST_RE.search(title):
        return AssignmentType.TEST
    if lowered.startswith("läxa"):
        return AssignmentType.HOMEWORK
    if lowered.startswith("inlämning"):
        return AssignmentType.SUBMISSION
    return AssignmentType.OTHER


@dataclass(frozen=True)
class SchoolDay:
    date: date
    lessons: list[Event]

    @property
    def first_start(self) -> datetime:
        return self.lessons[0].start

    @property
    def last_end(self) -> Optional[datetime]:
        ends = [e.end for e in self.lessons if e.end]
        return max(ends) if ends else None

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly form, used for Home Assistant state attributes."""
        lessons = [
            {
                "start": e.start.strftime("%H:%M"),
                "end": e.end.strftime("%H:%M") if e.end else None,
                # Full timestamps so a template can tell what has already passed.
                "start_at": e.start.isoformat(),
                "end_at": e.end.isoformat() if e.end else None,
                "title": e.title,
                "code": e.code,
                "location": e.location,
                "cancelled": e.cancelled,
            }
            for e in self.lessons
        ]
        return {
            "date": self.date.isoformat(),
            "lesson_count": len(lessons),
            "last_end": self.last_end.isoformat() if self.last_end else None,
            "lessons": lessons,
            "summary": "\n".join(
                f"{l['start']}-{l['end'] or '?'} {l['title']}"
                + (f" ({l['location']})" if l["location"] else "")
                + (" [INSTÄLLD]" if l["cancelled"] else "")
                for l in lessons
            ),
        }


def next_school_day(events: list[Event], today: date) -> Optional[SchoolDay]:
    """The first day after `today` that has lessons, or None if there is none."""
    by_day: dict[date, list[Event]] = {}
    for event in events:
        if event.kind is EventKind.LESSON and event.start.date() > today:
            by_day.setdefault(event.start.date(), []).append(event)
    if not by_day:
        return None
    day = min(by_day)
    return SchoolDay(day, sorted(by_day[day], key=lambda e: e.start))


def schedule_ahead(events: list[Event], today: date) -> list[SchoolDay]:
    """Today (if it has lessons) followed by the next school day."""
    days = []
    todays = [e for e in events if e.kind is EventKind.LESSON and e.start.date() == today]
    if todays:
        days.append(SchoolDay(today, sorted(todays, key=lambda e: e.start)))
    following = next_school_day(events, today)
    if following:
        days.append(following)
    return days


@dataclass(frozen=True)
class Assignment:
    event: Event
    type: AssignmentType
    days_until: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.event.title,
            "type": self.type.value,
            "due": self.event.start.isoformat(),
            "date": self.event.start.date().isoformat(),
            "days_until": self.days_until,
        }


def upcoming_assignments(
    events: list[Event], today: date, days: int = 14
) -> list[Assignment]:
    """Assignments due from today through `days` days ahead, soonest first."""
    last = today + timedelta(days=days)
    found = [
        Assignment(e, classify_assignment(e.title), (e.start.date() - today).days)
        for e in events
        if e.kind is EventKind.ASSIGNMENT and today <= e.start.date() <= last
    ]
    return sorted(found, key=lambda a: a.event.start)
