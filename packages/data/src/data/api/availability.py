"""Public point-in-time information-availability API.

USAGE:
    from data.api import add_available_at, filter_available_as_of

    available = add_available_at(frame, event_time_column="timestamp")
    historical = filter_available_as_of(available, as_of=cutoff)
"""

from data.platform.availability import (
    AVAILABLE_AT_COLUMN,
    add_available_at,
    filter_available_as_of,
    validate_information_set,
)

# --------------------------------------------------------------------------- #
# Public exports
# --------------------------------------------------------------------------- #

__all__ = [
    "AVAILABLE_AT_COLUMN",
    "add_available_at",
    "filter_available_as_of",
    "validate_information_set",
]
