"""Thin async HTTP clients for the Buienradar and Buienalarm nowcast APIs.

Both endpoints are unofficial and unauthenticated. This module only handles
transport and raw parsing into a shared ``RainSample`` model — combining the
two sources and deriving the bar graph/gauges lives in helpers.py.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiohttp

from .const import BUIENALARM_URL, BUIENRADAR_URL, REQUEST_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)


@dataclass(frozen=True)
class RainSample:
    """A single (time, intensity) forecast reading, already in mm/h."""

    time: datetime
    mm_per_hour: float


class BuienwatchApiError(Exception):
    """Base error for a failed upstream request."""


class BuienwatchConnectionError(BuienwatchApiError):
    """Raised when the upstream endpoint could not be reached in time."""


class BuienwatchParseError(BuienwatchApiError):
    """Raised when the upstream response could not be parsed."""


def _cachebuster() -> str:
    """Return a cache-busting query value, mirroring the upstream convention."""
    return str(random.randint(0, 999_999_999_999_999))


def _buienradar_code_to_mm_per_hour(code: int) -> float:
    """Convert a Buienradar 0-255 log-scale code to mm/h."""
    return 10 ** ((code - 109) / 32)


def _resolve_buienradar_time(hour: int, minute: int, *, now: datetime) -> datetime:
    """Resolve a bare HH:MM reading to a full datetime near ``now``.

    Buienradar's plain-text feed carries no date, only a time-of-day. Readings
    run forward from "now", so if a parsed time appears to be well in the past
    relative to `now` it must actually be just after midnight the next day.
    """
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate < now - timedelta(hours=1):
        candidate += timedelta(days=1)
    return candidate


async def async_fetch_buienradar(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> list[RainSample]:
    """Fetch and parse the Buienradar nowcast for a location."""
    url = BUIENRADAR_URL.format(lat=lat, lon=lon, cachebuster=_cachebuster())
    try:
        async with session.get(url, timeout=_TIMEOUT) as response:
            if response.status != 200:
                raise BuienwatchParseError(
                    f"Buienradar returned HTTP {response.status}"
                )
            text = await response.text()
    except TimeoutError as err:
        raise BuienwatchConnectionError("Timed out contacting Buienradar") from err
    except aiohttp.ClientError as err:
        raise BuienwatchConnectionError(f"Error contacting Buienradar: {err}") from err

    now = datetime.now(timezone.utc).astimezone()
    samples: list[RainSample] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        code_str, _, time_str = line.partition("|")
        try:
            code = int(code_str[:3])
            hour, minute = (int(part) for part in time_str.strip().split(":"))
        except ValueError:
            continue
        samples.append(
            RainSample(
                time=_resolve_buienradar_time(hour, minute, now=now),
                mm_per_hour=_buienradar_code_to_mm_per_hour(code),
            )
        )

    if not samples:
        raise BuienwatchParseError("Buienradar response contained no readings")
    return samples


async def async_fetch_buienalarm(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> list[RainSample]:
    """Fetch and parse the Buienalarm nowcast for a location."""
    url = BUIENALARM_URL.format(lat=lat, lon=lon, cachebuster=_cachebuster())
    try:
        async with session.get(url, timeout=_TIMEOUT) as response:
            if response.status != 200:
                raise BuienwatchParseError(
                    f"Buienalarm returned HTTP {response.status}"
                )
            payload = await response.json(content_type=None)
    except TimeoutError as err:
        raise BuienwatchConnectionError("Timed out contacting Buienalarm") from err
    except aiohttp.ClientError as err:
        raise BuienwatchConnectionError(f"Error contacting Buienalarm: {err}") from err

    try:
        timeseries = payload["data"]
        samples = [
            RainSample(
                time=datetime.fromtimestamp(item["timestamp"], tz=timezone.utc),
                mm_per_hour=float(item.get("precipitationrate", 0.0)),
            )
            for item in timeseries
        ]
    except (KeyError, TypeError, ValueError) as err:
        raise BuienwatchParseError(f"Could not parse Buienalarm response: {err}") from err

    if not samples:
        raise BuienwatchParseError("Buienalarm response contained no readings")
    return samples
