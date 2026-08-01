"""The Buienwatch integration."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import BuienwatchDataUpdateCoordinator
from .entity import BuienwatchConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BuienwatchConfigEntry) -> bool:
    """Set up Buienwatch from a config entry."""
    coordinator = BuienwatchDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The coordinator only reads the poll interval once, at init — a full
    # reload picks up any change made via the options flow.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: BuienwatchConfigEntry) -> None:
    """Reload the config entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BuienwatchConfigEntry) -> bool:
    """Unload a Buienwatch config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
