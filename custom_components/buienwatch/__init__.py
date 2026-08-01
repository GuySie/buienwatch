"""The Buienwatch integration."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MINUTES
from .coordinator import BuienwatchDataUpdateCoordinator
from .entity import BuienwatchConfigEntry

PLATFORMS: list[Platform] = [Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BuienwatchConfigEntry) -> bool:
    """Set up Buienwatch from a config entry."""
    coordinator = BuienwatchDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Both options are read live by the coordinator (data source mode) or
    # patched in-place here (poll interval) — no reload needed, so the
    # device-page select entity can change data source without any flicker.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: BuienwatchConfigEntry) -> None:
    """Apply a changed poll interval to the running coordinator in-place."""
    coordinator = entry.runtime_data
    coordinator.update_interval = timedelta(
        minutes=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MINUTES)
    )


async def async_unload_entry(hass: HomeAssistant, entry: BuienwatchConfigEntry) -> bool:
    """Unload a Buienwatch config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
