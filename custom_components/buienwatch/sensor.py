"""Buienwatch sensor entities."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime, UnitOfVolumetricFlux
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import RainSample
from .coordinator import BuienwatchDataUpdateCoordinator
from .entity import BuienwatchConfigEntry, BuienwatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BuienwatchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Buienwatch sensor entities from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BuienwatchBarGraphSensor(coordinator),
            BuienwatchCurrentIntensitySensor(coordinator),
            BuienwatchPeakIntensitySensor(coordinator),
            BuienwatchMinutesUntilStartSensor(coordinator),
            BuienwatchMinutesUntilStopSensor(coordinator),
            BuienwatchRawSensor(
                coordinator,
                slug="buienradar_raw",
                translation_key="buienradar_raw",
                samples_attr="buienradar_samples",
                available_attr="buienradar_available",
            ),
            BuienwatchRawSensor(
                coordinator,
                slug="buienalarm_raw",
                translation_key="buienalarm_raw",
                samples_attr="buienalarm_samples",
                available_attr="buienalarm_available",
            ),
        ]
    )


def _serialize_samples(samples: list[RainSample] | None) -> list[dict[str, Any]] | None:
    """Convert a sample list into JSON-serializable attribute data."""
    if samples is None:
        return None
    return [
        {"time": sample.time.isoformat(), "mm_per_hour": sample.mm_per_hour}
        for sample in samples
    ]


class BuienwatchBarGraphSensor(BuienwatchEntity, SensorEntity):
    """Text bar graph of the next 2 hours, for a Text Image complication."""

    _attr_translation_key = "bar_graph"
    _attr_icon = "mdi:chart-bar"

    def __init__(self, coordinator: BuienwatchDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_bar_graph"

    @property
    def native_value(self) -> str:
        """Return the bar graph string."""
        return self.coordinator.data.bar_graph

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return source availability so automations can tell what fed this."""
        data = self.coordinator.data
        return {
            "buienradar_available": data.buienradar_available,
            "buienalarm_available": data.buienalarm_available,
        }


class BuienwatchCurrentIntensitySensor(BuienwatchEntity, SensorEntity):
    """Current combined rain intensity."""

    _attr_translation_key = "current_intensity"
    _attr_device_class = SensorDeviceClass.PRECIPITATION_INTENSITY
    _attr_native_unit_of_measurement = UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BuienwatchDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_current_intensity"

    @property
    def native_value(self) -> float | None:
        """Return the current intensity in mm/h."""
        return self.coordinator.data.current_intensity


class BuienwatchPeakIntensitySensor(BuienwatchEntity, SensorEntity):
    """Peak combined rain intensity across the forecast window."""

    _attr_translation_key = "peak_intensity"
    _attr_device_class = SensorDeviceClass.PRECIPITATION_INTENSITY
    _attr_native_unit_of_measurement = UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BuienwatchDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_peak_intensity"

    @property
    def native_value(self) -> float | None:
        """Return the peak intensity in mm/h."""
        return self.coordinator.data.peak_intensity


class BuienwatchMinutesUntilStartSensor(BuienwatchEntity, SensorEntity):
    """Minutes until rain starts (0 if already raining)."""

    _attr_translation_key = "minutes_until_start"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: BuienwatchDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_minutes_until_start"

    @property
    def native_value(self) -> int | None:
        """Return minutes until rain starts, or None if none is forecast."""
        return self.coordinator.data.minutes_until_start


class BuienwatchMinutesUntilStopSensor(BuienwatchEntity, SensorEntity):
    """Minutes until rain stops."""

    _attr_translation_key = "minutes_until_stop"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: BuienwatchDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_minutes_until_stop"

    @property
    def native_value(self) -> int | None:
        """Return minutes until rain stops, or None if not applicable."""
        return self.coordinator.data.minutes_until_stop


class BuienwatchRawSensor(BuienwatchEntity, SensorEntity):
    """Raw per-source sample series, for building custom templates."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: BuienwatchDataUpdateCoordinator,
        *,
        slug: str,
        translation_key: str,
        samples_attr: str,
        available_attr: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._samples_attr = samples_attr
        self._available_attr = available_attr
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.tracked_entity_id}_{slug}"

    @property
    def native_value(self) -> str:
        """Return whether this source's most recent fetch succeeded."""
        return "ok" if getattr(self.coordinator.data, self._available_attr) else "unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw sample series."""
        samples: list[RainSample] | None = getattr(self.coordinator.data, self._samples_attr)
        return {"samples": _serialize_samples(samples)}
