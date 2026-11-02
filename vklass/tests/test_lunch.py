from datetime import date
from pathlib import Path

import pytest

from vklass import LunchDay, VklassInvalidUrl, VklassParseError, normalize_lunch_url
from vklass.lunch import parse_lunches

XML = (Path(__file__).parent / "fixtures" / "lunch.xml").read_text(encoding="utf-8")


def test_days_and_dishes():
    assert parse_lunches(XML) == [
        LunchDay(
            date(2026, 11, 2),
            [
                "Korv stroganoff serveras med ris (Bird)",
                "Vegetarisk korv stroganoff serveras med ris (Vegetarian)",
            ],
        ),
        LunchDay(date(2026, 11, 3), ["Spaghetti med färssås (Vegetarian)"]),
    ]  # Wednesday has no dishes, so it is left out


def test_not_rss():
    with pytest.raises(VklassParseError):
        parse_lunches("<html>nope</html>")
    with pytest.raises(VklassParseError):
        parse_lunches("not xml at all")


EXPECTED = "https://skolmaten.se/api/4/rss/week/exampleskolan?locale=sv"


@pytest.mark.parametrize(
    "pasted",
    [
        "https://skolmaten.se/exampleskolan",
        "https://skolmaten.se/exampleskolan/",
        "https://www.skolmaten.se/exampleskolan",
        "https://skolmaten.se/api/4/rss/week/exampleskolan?locale=en",
    ],
)
def test_normalize_lunch_url(pasted):
    assert normalize_lunch_url(pasted) == EXPECTED


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "https://example.com/exampleskolan",
        "https://skolmaten.se.evil.example.com/exampleskolan",
        "https://skolmaten.se/",
        "https://skolmaten.se/a/b/c",
        "ftp://skolmaten.se/exampleskolan",
    ],
)
def test_normalize_lunch_url_rejects(bad):
    with pytest.raises(VklassInvalidUrl):
        normalize_lunch_url(bad)
