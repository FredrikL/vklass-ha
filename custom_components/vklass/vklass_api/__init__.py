from .client import VklassClient
from .exceptions import (
    VklassAuthError,
    VklassConnectionError,
    VklassError,
    VklassInvalidUrl,
    VklassParseError,
)
from .feed import feed_id, normalize_feed_url
from .lunch import normalize_lunch_url
from .models import Child, Event, EventKind, LunchDay
from .schedule import (
    Assignment,
    AssignmentType,
    SchoolDay,
    next_school_day,
    schedule_ahead,
    upcoming_assignments,
)

__all__ = [
    "Assignment",
    "AssignmentType",
    "SchoolDay",
    "next_school_day",
    "schedule_ahead",
    "upcoming_assignments",
    "Child",
    "Event",
    "EventKind",
    "LunchDay",
    "VklassAuthError",
    "VklassClient",
    "VklassConnectionError",
    "VklassError",
    "VklassInvalidUrl",
    "VklassParseError",
    "feed_id",
    "normalize_feed_url",
    "normalize_lunch_url",
]
