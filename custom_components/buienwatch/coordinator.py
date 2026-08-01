"""DataUpdateCoordinator for Buienwatch."""
from __future__ import annotations

import asyncio
import logging
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
        want_buienradar = mode in (DataSourceMode.BUIENRADAR, DataSourceMode.COMBINED)
        want_buienalarm = mode in (DataSourceMode.BUIENALARM, DataSourceMode.COMBINED)

        tasks = []
        if want_buienradar:
            tasks.append(async_fetch_buienradar(self._session, lat, lon))
        if want_buienalarm:
            tasks.append(async_fetch_buienalarm(self._session, lat, lon))

        fetched = iter(await asyncio.gather(*tasks, return_exceptions=True))
        buienradar_samples = self._unwrap(next(fetched), "Buienradar") if want_buienradar else None
        buienalarm_samples = self._unwrap(next(fetched), "Buienalarm") if want_buienalarm else None

        if buienradar_samples is None and buienalarm_samples is None:
            attempted = " and ".join(
                name
                for want, name in ((want_buienradar, "Buienradar"), (want_buienalarm, "Buienalarm"))
                if want
            )
            raise UpdateFailed(f"{attempted} unavailable for {self.tracked_entity_id}")

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

    def _unwrap(
        self, result: list[RainSample] | BaseException, source_name: str
    ) -> list[RainSample] | None:
        """Return the sample list, or None if that source's fetch failed."""
        if isinstance(result, BuienwatchApiError):
            _LOGGER.warning("%s unavailable for %s: %s", source_name, self.tracked_entity_id, result)
            return None
        if isinstance(result, BaseException):
            _LOGGER.exception(
                "Unexpected error fetching %s for %s", source_name, self.tracked_entity_id, exc_info=result
            )
            return None
        return result
