"""Select entity for the Buienwatch data source mode."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DATA_SOURCE, DEFAULT_DATA_SOURCE, DataSourceMode
from .coordinator import BuienwatchDataUpdateCoordinator
from .entity import BuienwatchConfigEntry, BuienwatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BuienwatchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the data source select entity."""
    async_add_entities([BuienwatchDataSourceSelect(entry.runtime_data, entry)])


class BuienwatchDataSourceSelect(BuienwatchEntity, SelectEntity):
    """Select entity to choose Buienradar, Buienalarm, or both, combined."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:weather-pouring"
    _attr_translation_key = "data_source"
    _attr_options = [mode.value for mode in DataSourceMode]

    def __init__(
        self,
        coordinator: BuienwatchDataUpdateCoordinator,
        entry: BuienwatchConfigEntry,
    ) -> None:
        """Initialise the select entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_data_source"
        # Initialise from persisted options so the correct value shows on startup,
        # without waiting for the coordinator's first refresh.
        self._attr_current_option = entry.options.get(CONF_DATA_SOURCE, DEFAULT_DATA_SOURCE)

    async def async_select_option(self, option: str) -> None:
        """Persist the new data source mode and refresh immediately."""
        self._attr_current_option = option
        self.async_write_ha_state()

        new_options = {**self._entry.options, CONF_DATA_SOURCE: DataSourceMode(option)}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)

        # The coordinator reads the mode live on every poll — request one now
        # so the change is reflected immediately instead of on the next
        # scheduled interval.
        await self.coordinator.async_request_refresh()
