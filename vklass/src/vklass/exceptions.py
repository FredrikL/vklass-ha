"""Exceptions raised by the Vklass client."""


class VklassError(Exception):
    """Base class for all Vklass errors."""


class VklassConnectionError(VklassError):
    """The server could not be reached or answered unexpectedly."""


class VklassAuthError(VklassError):
    """Login was rejected, or a session could not be (re)established."""


class VklassParseError(VklassError):
    """A response did not have the shape we expect (Vklass probably changed)."""
