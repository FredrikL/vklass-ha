"""Exceptions raised by the Vklass client."""


class VklassError(Exception):
    """Base class for all Vklass errors."""


class VklassConnectionError(VklassError):
    """The server could not be reached or answered unexpectedly."""


class VklassAuthError(VklassError):
    """The server does not recognise the calendar link (revoked or mistyped)."""


class VklassParseError(VklassError):
    """A response did not have the shape we expect (Vklass probably changed)."""


class VklassInvalidUrl(VklassError, ValueError):
    """A pasted link is not a Vklass calendar or Skolmaten menu link."""
