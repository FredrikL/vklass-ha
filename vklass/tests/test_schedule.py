from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from vklass import Event, EventKind
from vklass.schedule import (
    AssignmentType,
    classify_assignment,
    next_school_day,
    schedule_ahead,
    upcoming_assignments,
)

TZ = ZoneInfo("Europe/Stockholm")


def ev(kind, title, start, end=None, cancelled=False):
    return Event(
        uid=f"{title}{start}",
        child_id=1,
        kind=kind,
        title=title,
        code="",
        start=datetime.fromisoformat(start).replace(tzinfo=TZ),
        end=datetime.fromisoformat(end).replace(tzinfo=TZ) if end else None,
        all_day=False,
        location="",
        cancelled=cancelled,
        substitute=False,
    )


L, A, H = EventKind.LESSON, EventKind.ASSIGNMENT, EventKind.HOLIDAY


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Prov Meteorologi", AssignmentType.TEST),
        ("Nationellt prov i matte", AssignmentType.TEST),
        ("Läxa i Fysik", AssignmentType.HOMEWORK),
        ("Inlämning: Offentlig konst", AssignmentType.SUBMISSION),
        ("Textila material", AssignmentType.OTHER),
        ("Provkörning", AssignmentType.OTHER),
    ],
)
def test_classify(title, expected):
    assert classify_assignment(title) is expected


def test_next_school_day_skips_weekend_and_holidays():
    friday = date(2026, 10, 30)
    events = [
        ev(H, "Alla helgons dag", "2026-10-31T00:00"),
        ev(L, "Svenska", "2026-11-02T09:15", "2026-11-02T10:00"),
        ev(L, "Idrott", "2026-11-02T08:15", "2026-11-02T09:00"),
        ev(L, "Matte", "2026-11-03T08:15", "2026-11-03T09:00"),
    ]
    day = next_school_day(events, friday)
    assert day.date == date(2026, 11, 2)
    assert [e.title for e in day.lessons] == ["Idrott", "Svenska"]  # sorted
    assert day.first_start == events[2].start
    assert day.last_end == events[1].end


def test_next_school_day_ignores_today_and_past():
    today = date(2026, 11, 2)
    events = [
        ev(L, "Earlier", "2026-11-01T08:00"),
        ev(L, "Today", "2026-11-02T08:00"),
        ev(L, "Tomorrow", "2026-11-03T08:00"),
    ]
    assert next_school_day(events, today).lessons[0].title == "Tomorrow"


def test_schedule_ahead_is_today_then_next_school_day():
    events = [
        ev(L, "Later", "2026-11-02T10:00"),
        ev(L, "Earlier", "2026-11-02T08:00"),
        ev(L, "Tomorrow", "2026-11-03T08:00"),
        ev(L, "Day after", "2026-11-04T08:00"),
        ev(A, "Prov", "2026-11-02T12:00"),
    ]
    days = schedule_ahead(events, date(2026, 11, 2))
    assert [d.date for d in days] == [date(2026, 11, 2), date(2026, 11, 3)]
    assert [e.title for e in days[0].lessons] == ["Earlier", "Later"]


def test_schedule_ahead_without_lessons_today():
    events = [ev(L, "Monday", "2026-11-02T08:00")]
    days = schedule_ahead(events, date(2026, 11, 1))
    assert [d.date for d in days] == [date(2026, 11, 2)]
    assert schedule_ahead([], date(2026, 11, 1)) == []


def test_next_school_day_keeps_cancelled_lessons():
    events = [ev(L, "Svenska", "2026-11-03T08:00", cancelled=True)]
    assert next_school_day(events, date(2026, 11, 2)).lessons[0].cancelled


def test_no_school_day():
    assert next_school_day([], date(2026, 11, 2)) is None
    assert next_school_day([ev(A, "Prov", "2026-11-05T13:05")], date(2026, 11, 2)) is None


def test_upcoming_assignments_window_and_order():
    today = date(2026, 10, 23)
    events = [
        ev(A, "Läxa i Fysik", "2026-11-04T11:40"),
        ev(A, "Prov Meteorologi", "2026-11-05T13:05"),
        ev(A, "Too far", "2026-11-20T10:00"),
        ev(A, "Old", "2026-10-22T10:00"),
        ev(L, "Svenska", "2026-10-26T08:00"),
    ]
    found = upcoming_assignments(events, today, days=14)
    assert [(a.event.title, a.type, a.days_until) for a in found] == [
        ("Läxa i Fysik", AssignmentType.HOMEWORK, 12),
        ("Prov Meteorologi", AssignmentType.TEST, 13),
    ]


def test_school_day_as_dict():
    events = [
        ev(L, "Idrott", "2026-11-02T08:15", "2026-11-02T09:00"),
        ev(L, "Svenska", "2026-11-02T09:15", "2026-11-02T10:00", cancelled=True),
    ]
    d = next_school_day(events, date(2026, 11, 1)).as_dict()
    assert d["date"] == "2026-11-02"
    assert d["lesson_count"] == 2
    assert d["last_end"] == "2026-11-02T10:00:00+01:00"
    assert d["lessons"][0] == {
        "start": "08:15", "end": "09:00",
        "start_at": "2026-11-02T08:15:00+01:00", "end_at": "2026-11-02T09:00:00+01:00",
        "title": "Idrott", "code": "", "location": "", "cancelled": False,
    }
    assert d["summary"] == "08:15-09:00 Idrott\n09:15-10:00 Svenska [INSTÄLLD]"


def test_assignment_as_dict():
    found = upcoming_assignments(
        [ev(A, "Prov Meteorologi", "2026-11-05T13:05")], date(2026, 10, 23)
    )
    assert found[0].as_dict() == {
        "title": "Prov Meteorologi",
        "type": "test",
        "due": "2026-11-05T13:05:00+01:00",
        "date": "2026-11-05",
        "days_until": 13,
    }
