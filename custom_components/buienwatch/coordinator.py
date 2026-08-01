"""DataUpdateCoordinator for Buienwatch."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BuienwatchApiError, RainSample, async_fetch_buienalarm, async_fetch_buienradar
from .const import (
    CONF_DATA_SOURCE,
    CONF_POLL_INTERVAL,
    CONF_TRACKED_ENTITY_ID,
    DEFAULT_DATA_SOURCE,
    DEFAULT_POLL_INTERVAL_MINUTES,
    DOMAIN,
    DataSourceMode,
)
from .helpers import combine_samples, build_bar_graph, compute_gauges

_LOGGER = logging.getLogger(__name__)

# A fetch function's signature is async_fetch_buienradar/async_fetch_buienalarm's:
# (session, lat, lon) -> list[RainSample].
_FetchFn = Callable[..., Awaitable[list[RainSample]]]


@dataclass
class BuienwatchData:
    """A fully-resolved forecast for one tracked entity."""

    bar_graph: str
    current_intensity: float | None
    peak_intensity: float | None
    minutes_until_start: int | None
    minutes_until_stop: int | None
    buienradar_samples: list[RainSample] | None
    buienalarm_samples: list[RainSample] | None
    buienradar_available: bool
    buienalarm_available: bool
    data_source_mode: DataSourceMode
    latitude: float
    longitude: float


class BuienwatchDataUpdateCoordinator(DataUpdateCoordinator[BuienwatchData]):
    """Coordinator that polls Buienradar and Buienalarm for one tracked entity."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        self.tracked_entity_id: str = entry.data[CONF_TRACKED_ENTITY_ID]
        self._entry = entry
        self._session = async_get_clientsession(hass)
        interval_minutes = entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )

    @property
    def data_source_mode(self) -> DataSourceMode:
        """Return the currently-selected data source mode.

        Read live from entry options (rather than cached at init) so the
        device-page select entity can change this without a coordinator
        reload — it takes effect on the next poll.
        """
        return DataSourceMode(
            self._entry.options.get(CONF_DATA_SOURCE, DEFAULT_DATA_SOURCE)
        )

    async def _async_update_data(self) -> BuienwatchData:
        """Fetch the current location, poll the selected source(s), and combine them."""
        state = self.hass.states.get(self.tracked_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            raise UpdateFailed(f"{self.tracked_entity_id} is unavailable")

        lat = state.attributes.get(ATTR_LATITUDE)
        lon = state.attributes.get(ATTR_LONGITUDE)
        if lat is None or lon is None:
            raise UpdateFailed(f"{self.tracked_entity_id} has no known location")

        mode = self.data_source_mode
        buienradar_samples, buienalarm_samples = await self._fetch_for_mode(mode, lat, lon)

        if buienradar_samples is None and buienalarm_samples is None:
            raise UpdateFailed(
                f"No rain data available for {self.tracked_entity_id} (mode: {mode.value})"
            )

        combined = combine_samples(
            buienradar_samples, buienalarm_samples, now=dt_util.utcnow()
        )
        bar_graph = build_bar_graph(combined)
        gauges = compute_gauges(combined)

        return BuienwatchData(
            bar_graph=bar_graph,
            current_intensity=gauges.current,
            peak_intensity=gauges.peak,
            minutes_until_start=gauges.minutes_until_start,
            minutes_until_stop=gauges.minutes_until_stop,
            buienradar_samples=buienradar_samples,
            buienalarm_samples=buienalarm_samples,
            buienradar_available=buienradar_samples is not None,
            buienalarm_available=buienalarm_samples is not None,
            data_source_mode=mode,
            latitude=float(lat),
            longitude=float(lon),
        )

    async def _fetch_for_mode(
        self, mode: DataSourceMode, lat: float, lon: float
    ) -> tuple[list[RainSample] | None, list[RainSample] | None]:
        """Fetch whichever source(s) ``mode`` calls for, applying fallback where relevant.

        Always returns (buienradar_samples, buienalarm_samples), regardless of mode.
        """
        buienradar = (async_fetch_buienradar, "Buienradar")
        buienalarm = (async_fetch_buienalarm, "Buienalarm")

        if mode is DataSourceMode.BUIENRADAR:
            return await self._safe_fetch(*buienradar, lat, lon), None
        if mode is DataSourceMode.BUIENALARM:
            return None, await self._safe_fetch(*buienalarm, lat, lon)
        if mode is DataSourceMode.COMBINED:
            # Both are wanted regardless of the other's outcome — fetch concurrently.
            buienradar_samples, buienalarm_samples = await asyncio.gather(
                self._safe_fetch(*buienradar, lat, lon),
                self._safe_fetch(*buienalarm, lat, lon),
            )
            return buienradar_samples, buienalarm_samples
        if mode is DataSourceMode.BUIENRADAR_PRIMARY:
            return await self._fetch_with_fallback(buienradar, buienalarm, lat, lon)
        if mode is DataSourceMode.BUIENALARM_PRIMARY:
            # The fallback only fires when the primary failed, so the two results
            # are never both populated — swap back into (buienradar, buienalarm) order.
            buienalarm_samples, buienradar_samples = await self._fetch_with_fallback(
                buienalarm, buienradar, lat, lon
            )
            return buienradar_samples, buienalarm_samples
        raise AssertionError(f"Unhandled data source mode: {mode}")  # pragma: no cover

    async def _fetch_with_fallback(
        self,
        primary: tuple[_FetchFn, str],
        fallback: tuple[_FetchFn, str],
        lat: float,
        lon: float,
    ) -> tuple[list[RainSample] | None, list[RainSample] | None]:
        """Try the primary source; only fetch the fallback if the primary failed.

        Sequential, not concurrent — the fallback source is only queried when
        actually needed, to avoid hitting it on every poll.
        """
        primary_fetch, primary_name = primary
        fallback_fetch, fallback_name = fallback

        primary_samples = await self._safe_fetch(primary_fetch, primary_name, lat, lon)
        if primary_samples is not None:
            return primary_samples, None

        _LOGGER.debug(
            "%s unavailable for %s, falling back to %s",
            primary_name, self.tracked_entity_id, fallback_name,
        )
        fallback_samples = await self._safe_fetch(fallback_fetch, fallback_name, lat, lon)
        return None, fallback_samples

    async def _safe_fetch(
        self, fetch: _FetchFn, source_name: str, lat: float, lon: float
    ) -> list[RainSample] | None:
        """Call an API fetch function, returning None (and logging) on any failure."""
        try:
            return await fetch(self._session, lat, lon)
        except BuienwatchApiError as err:
            _LOGGER.warning("%s unavailable for %s: %s", source_name, self.tracked_entity_id, err)
            return None
        except Exception:
            _LOGGER.exception("Unexpected error fetching %s for %s", source_name, self.tracked_entity_id)
            return None
