from .client import VklassClient
from .exceptions import (
    VklassAuthError,
    VklassConnectionError,
    VklassError,
    VklassParseError,
)
from .models import Child, Event, EventKind, LunchDay
from .schedule import (
    Assignment,
    AssignmentType,
    SchoolDay,
    next_school_day,
    upcoming_assignments,
)

__all__ = [
    "Assignment",
    "AssignmentType",
    "SchoolDay",
    "next_school_day",
    "upcoming_assignments",
    "Child",
    "Event",
    "EventKind",
    "LunchDay",
    "VklassAuthError",
    "VklassClient",
    "VklassConnectionError",
    "VklassError",
    "VklassParseError",
]
