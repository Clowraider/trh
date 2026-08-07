"""Timezone-aware UTC datetime helpers.

Centralizes UTC time generation so the auth module never depends on the
deprecated ``datetime.utcnow()``.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)
