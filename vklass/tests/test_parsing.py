import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from vklass import Child, EventKind, VklassParseError
from vklass.parsing import parse_children, parse_events, parse_verification_token

FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("Europe/Stockholm")


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_verification_token():
    assert parse_verification_token(fixture("login.html")) == "tok-123"


def test_verification_token_missing():
    with pytest.raises(VklassParseError):
        parse_verification_token("<html></html>")


def test_children():
    assert parse_children(fixture("schedule.html")) == [
        Child(1001, "Alva"),
        Child(1002, "Bo"),
    ]


def test_children_none_found():
    assert parse_children("<html></html>") == []


@pytest.fixture
def events():
    return parse_events(json.loads(fixture("calendar.json")), 1001, TZ)


def test_events_sorted_by_start(events):
    assert [e.start for e in events] == sorted(e.start for e in events)
    assert events[0].title == "Idrott och hälsa (9A/IDH)"


def test_lesson_fields(events):
    lesson = next(e for e in events if e.code == "SV")
    assert lesson.kind is EventKind.LESSON
    assert lesson.start == datetime(2026, 10, 19, 9, 15, tzinfo=TZ)
    assert lesson.end == datetime(2026, 10, 19, 9, 40, tzinfo=TZ)
    assert lesson.location == "1 | ABC"
    assert lesson.child_id == 1001
    assert not lesson.cancelled


def test_cancelled_and_substitute_flags(events):
    assert next(e for e in events if e.code == "IDH").cancelled
    assert next(e for e in events if e.kind is EventKind.HOLIDAY).substitute


def test_assignment_has_no_end(events):
    exam = next(e for e in events if e.kind is EventKind.ASSIGNMENT)
    assert exam.end is None
    assert exam.all_day


def test_unknown_event_type_and_null_strings(events):
    other = next(e for e in events if e.title == "Något nytt")
    assert other.kind is EventKind.OTHER
    assert other.location == ""
    assert other.code == ""


def test_uids_unique_and_stable(events):
    again = parse_events(json.loads(fixture("calendar.json")), 1001, TZ)
    assert [e.uid for e in events] == [e.uid for e in again]
    assert len({e.uid for e in events}) == len(events)
    other_child = parse_events(json.loads(fixture("calendar.json")), 1002, TZ)
    assert not {e.uid for e in events} & {e.uid for e in other_child}


def test_not_a_list():
    with pytest.raises(VklassParseError):
        parse_events({"error": "x"}, 1, TZ)


def test_bad_time_format():
    with pytest.raises(VklassParseError):
        parse_events([{"title": "x", "start": "19/10 09:15"}], 1, TZ)
