"""
Datetime helper utilities for consistent timezone handling.

The backend stores timestamps in UTC and exposes ISO 8601 strings with an
explicit timezone designator. For user-facing displays we typically convert to
Asia/Shanghai.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from zoneinfo import ZoneInfo

UTC = dt.UTC
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_ISO_Z_SUFFIX = "+00:00"


def utc_now() -> dt.datetime:
    """Return the current UTC time as an aware datetime."""
    return dt.datetime.now(UTC)


def utc_now_naive() -> dt.datetime:
    """Return the current UTC time as a naive datetime (for legacy DB fields)."""
    return dt.datetime.now(UTC).replace(tzinfo=None)


def shanghai_now() -> dt.datetime:
    """Return the current Asia/Shanghai time as an aware datetime."""
    return utc_now().astimezone(SHANGHAI_TZ)


def ensure_utc(value: dt.datetime) -> dt.datetime:
    """
    Convert a datetime to UTC.

    Naive values are assumed to be in Asia/Shanghai to preserve legacy data.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(UTC)


def ensure_shanghai(value: dt.datetime) -> dt.datetime:
    """
    Convert a datetime to Asia/Shanghai.

    Naive values are assumed to be in Asia/Shanghai (legacy behaviour).
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)


def utc_isoformat(value: dt.datetime | None = None) -> str:
    """Return an ISO 8601 string in UTC with a trailing Z suffix."""
    value = ensure_utc(value or utc_now())
    iso_string = value.isoformat()
    if iso_string.endswith(_ISO_Z_SUFFIX):
        return iso_string.replace(_ISO_Z_SUFFIX, "Z")
    return iso_string


def shanghai_isoformat(value: dt.datetime | None = None) -> str:
    """Return an ISO 8601 string in Asia/Shanghai timezone."""
    value = ensure_shanghai(value or shanghai_now())
    return value.isoformat()


def coerce_datetime(value: dt.datetime | None) -> dt.datetime | None:
    """Normalize persisted datetimes to UTC, handling nulls gracefully."""
    if value is None:
        return None
    return ensure_utc(value)


def coerce_any_to_utc_datetime(value: dt.datetime | int | float | str | None) -> dt.datetime | None:
    """
    Convert heterogeneous timestamp representations to an aware UTC datetime.

    Supports:
      * aware or naive datetime objects
      * unix timestamps (seconds) as int/float
      * ISO 8601 strings
    """
    if value is None:
        return None

    if isinstance(value, dt.datetime):
        return ensure_utc(value)

    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, tz=UTC)

    if isinstance(value, str):
        # Attempt to parse ISO 8601 strings.
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", _ISO_Z_SUFFIX))
            return ensure_utc(parsed)
        except ValueError:
            # Attempt fallback to numeric string
            try:
                as_number = float(value)
                return dt.datetime.fromtimestamp(as_number, tz=UTC)
            except ValueError:
                raise ValueError(f"Unsupported datetime string format: {value!r}") from None

    raise TypeError(f"Unsupported datetime value: {value!r}")


def normalize_iterable_to_utc(values: Iterable[dt.datetime | None]) -> list[dt.datetime | None]:
    """Normalize each datetime in iterable to UTC."""
    return [coerce_datetime(item) if isinstance(item, dt.datetime) else None for item in values]


def format_utc_datetime(value: dt.datetime | None) -> str | None:
    """
    Format a datetime to UTC ISO 8601 string, handling naive datetimes.

    Returns None for None input.
    Naive datetimes are assumed to be in UTC (legacy behavior).
    """
    if value is None:
        return None
    return utc_isoformat(value)


__all__ = [
    "UTC",
    "SHANGHAI_TZ",
    "utc_now",
    "utc_now_naive",
    "shanghai_now",
    "ensure_utc",
    "ensure_shanghai",
    "utc_isoformat",
    "shanghai_isoformat",
    "coerce_datetime",
    "coerce_any_to_utc_datetime",
    "normalize_iterable_to_utc",
    "format_utc_datetime",
]
