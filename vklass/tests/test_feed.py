from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from vklass import (
    EventKind,
    VklassInvalidUrl,
    VklassParseError,
    feed_id,
    normalize_feed_url,
)
from vklass.feed import parse_feed

TZ = ZoneInfo("Europe/Stockholm")
GUID = "97b8d65c-c5bf-4498-a95a-5717e0d4d031"
FEED = (Path(__file__).parent / "fixtures" / "feed.ics").read_text(encoding="utf-8")


def events():
    return {e.uid.split("-", 1)[1]: e for e in parse_feed(FEED, "kid", TZ)}


def test_sorted_and_counted():
    parsed = parse_feed(FEED, "kid", TZ)
    assert len(parsed) == 8
    assert parsed == sorted(parsed, key=lambda e: e.start)
    assert all(e.child_id == "kid" and e.uid.startswith("kid-") for e in parsed)


def test_lesson_fields():
    e = events()["aaaa0001"]
    assert e.kind is EventKind.LESSON
    assert e.title == "Svenska (9A/SV)"
    assert e.code == "SV"
    assert e.location == "12 | ABC"  # room | teacher, as the old calendar view
    assert e.start == datetime(2026, 11, 2, 9, 15, tzinfo=TZ)
    assert e.end == datetime(2026, 11, 2, 9, 40, tzinfo=TZ)
    assert not e.all_day and not e.cancelled


def test_escaped_text_is_unescaped():
    assert events()["aaaa0002"].location == "Idrott, hall 2 | DEF"


def test_windows_timezone_follows_daylight_saving():
    # 2026-10-25 is when Sweden went back to winter time.
    text = FEED.replace("20261102T091500", "20261024T091500").replace(
        "20261102T094000", "20261024T094000"
    )
    e = {x.uid: x for x in parse_feed(text, "kid", TZ)}["kid-aaaa0001"]
    assert e.start.utcoffset().total_seconds() == 2 * 3600
    assert events()["aaaa0001"].start.utcoffset().total_seconds() == 3600


def test_utc_times_are_converted_and_status_read():
    e = events()["cccc0001"]
    assert e.start == datetime(2026, 11, 4, 8, 0, tzinfo=TZ)
    assert e.cancelled


def test_folded_lines_are_joined():
    assert events()["cccc0002"].title == "Bild (9A/BD)"
    assert events()["cccc0002"].code == "BD"


def test_tests_and_homework_are_all_day_assignments_with_due_time():
    test, homework = events()["bbbb0001"], events()["bbbb0002"]
    assert test.kind is homework.kind is EventKind.ASSIGNMENT
    assert test.all_day and test.end is None
    assert test.title == "Prov Meteorologi"
    assert test.start == datetime(2026, 11, 5, 13, 5, tzinfo=TZ)
    assert homework.start == datetime(2026, 11, 6, 8, 15, tzinfo=TZ)


def test_other_all_day_entries_are_not_assignments():
    e = events()["bbbb0003"]
    assert e.kind is EventKind.OTHER
    assert e.start == datetime(2026, 11, 9, 8, 0, tzinfo=TZ)


def test_empty_feed_has_no_events():
    assert parse_feed("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", "kid", TZ) == []


def test_not_a_calendar():
    with pytest.raises(VklassParseError):
        parse_feed("<html>Verifying...</html>", "kid", TZ)


def test_bad_time_is_a_parse_error():
    bad = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:soon\nSUMMARY:x\nEND:VEVENT\nEND:VCALENDAR"
    with pytest.raises(VklassParseError):
        parse_feed(bad, "kid", TZ)


@pytest.mark.parametrize(
    "pasted",
    [
        f"webcal://cal.vklass.se/{GUID}.ics?includeLectures=true",
        f"https://cal.vklass.se/{GUID}.ics?includeLectures=false",
        f"  https://cal.vklass.se/{GUID.upper()}.ics  ",
    ],
)
def test_normalize_feed_url(pasted):
    assert (
        normalize_feed_url(pasted)
        == f"https://cal.vklass.se/{GUID}.ics?includeLectures=true"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not a url",
        f"https://evil.example.com/{GUID}.ics",
        f"https://cal.vklass.se.evil.example.com/{GUID}.ics",
        "https://cal.vklass.se/",
        "https://cal.vklass.se/not-a-guid.ics",
        f"https://cal.vklass.se/{GUID}",
    ],
)
def test_normalize_feed_url_rejects(bad):
    with pytest.raises(VklassInvalidUrl):
        normalize_feed_url(bad)


def test_feed_id_hides_the_secret_and_ignores_formatting():
    a = feed_id(f"webcal://cal.vklass.se/{GUID}.ics?includeLectures=true")
    b = feed_id(f"https://cal.vklass.se/{GUID.upper()}.ics")
    assert a == b and GUID not in a and len(a) == 16
    assert a != feed_id("https://cal.vklass.se/00000000-0000-0000-0000-000000000000.ics")
