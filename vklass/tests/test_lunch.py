from datetime import date
from pathlib import Path

import pytest

from vklass import VklassParseError
from vklass.parsing import _resolve_day_dates, parse_lunches

HTML = (Path(__file__).parent / "fixtures" / "welcome.html").read_text(encoding="utf-8")


def test_parse_lunches_names_and_days():
    cards = parse_lunches(HTML, date(2026, 10, 22))
    assert [name for name, _ in cards] == ["Alva", "Bo"]
    alva = dict((l.date, l.dishes) for l in cards[0][1])
    assert list(alva) == [date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 27)]
    assert alva[date(2026, 10, 22)] == ["Köttbullar med potatis", "Vegetariskt: Linsgryta"]
    assert alva[date(2026, 10, 27)] == ["Pannkakor & sylt"]  # entity decoded


def test_days_without_menu_are_dropped():
    cards = parse_lunches(HTML, date(2026, 10, 22))
    assert date(2026, 10, 26) not in {l.date for l in cards[0][1]}  # empty monday
    assert [l.date for l in cards[1][1]] == [date(2026, 10, 22)]


def test_no_cards_is_a_parse_error():
    with pytest.raises(VklassParseError):
        parse_lunches("<html>login page</html>", date(2026, 10, 22))


def test_weekday_labels_resolve_in_order():
    friday = date(2026, 10, 23)
    labels = ["idag", "måndag", "tisdag", "onsdag", "torsdag"]
    assert _resolve_day_dates(labels, friday) == [
        date(2026, 10, 23), date(2026, 10, 26), date(2026, 10, 27),
        date(2026, 10, 28), date(2026, 10, 29),
    ]


def test_same_weekday_as_today_means_next_week():
    thursday = date(2026, 10, 22)
    assert _resolve_day_dates(["idag", "torsdag"], thursday) == [
        thursday, date(2026, 10, 29),
    ]


def test_imorgon_and_unknown_labels():
    today = date(2026, 10, 22)
    assert _resolve_day_dates(["idag", "imorgon", "okänd", "måndag"], today) == [
        today, date(2026, 10, 23), None, date(2026, 10, 26),
    ]
