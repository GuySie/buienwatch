"""Base entity for Buienwatch."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import BuienwatchDataUpdateCoordinator

# Typed config entry alias — entry.runtime_data is BuienwatchDataUpdateCoordinator.
type BuienwatchConfigEntry = ConfigEntry[BuienwatchDataUpdateCoordinator]


class BuienwatchEntity(CoordinatorEntity[BuienwatchDataUpdateCoordinator]):
    """Base class for all Buienwatch entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BuienwatchDataUpdateCoordinator) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model="Rain Nowcast",
        )
