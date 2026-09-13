"""Constants for the Buienwatch integration."""
from __future__ import annotations

from enum import StrEnum

DOMAIN = "buienwatch"
MANUFACTURER = "Buienradar / Buienalarm"

CONF_TRACKED_ENTITY_ID = "tracked_entity_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_DATA_SOURCE = "data_source"

DEFAULT_POLL_INTERVAL_MINUTES = 5
MIN_POLL_INTERVAL_MINUTES = 1
MAX_POLL_INTERVAL_MINUTES = 30

# Below this intensity a time slot is considered dry, for the purposes of the
# bar graph's lowest bucket and the "starts in"/"stops in" gauge sensors.
RAIN_THRESHOLD_MM_PER_HOUR = 0.1

# Bar graph: 2 hours as 8 segments of 15 minutes, each segment the max of
# three 5-minute samples — matches the pre-existing Jinja2 templates this
# integration replaces.
BAR_GRAPH_SEGMENTS = 8
BAR_GRAPH_SEGMENT_MINUTES = 15
SAMPLE_GRID_MINUTES = 5

BUIENRADAR_URL = "https://gps.buienradar.nl/getrr.php?lat={lat:.2f}&lon={lon:.2f}&c={cachebuster}"
BUIENALARM_URL = (
    "https://imn-rust-lb.infoplaza.io/v4/nowcast/ba/timeseries/"
    "{lat:.3f}/{lon:.3f}/?c={cachebuster}"
)

REQUEST_TIMEOUT_SECONDS = 10

# Ascending (threshold_mm_per_hour, character) pairs — a slot maps to the
# first character whose threshold it is strictly below. Values at/above the
# final threshold map to BAR_MAX_CHAR. The 0.1-2.0 mm/h boundaries were
# re-derived from a ~12h real-world capture of both sources at one location.
# Buienradar's `10 ** ((code-109)/32)` conversion only produces a fixed
# ladder of ~40 discrete mm/h values in practice, not a continuum, and two
# of those codes (0.1000 and 0.2054 mm/h) dominate the low end — round-number
# boundaries (0.5/1.0/1.5/2.0) lumped both into one bucket, so these instead
# sit in the actual gaps between code values, chosen to balance the
# resulting bucket populations rather than split any single code's cluster.
BAR_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.1, "▁"),
    (0.25, "▂"),
    (0.35, "▃"),
    (0.75, "▄"),
    (2.0, "▅"),
    (3.5, "▆"),
    (5.0, "▇"),
    (10.0, "█"),
)
BAR_MAX_CHAR = "▓"


class DataSourceMode(StrEnum):
    """Which upstream source(s) to use, selectable from the device page."""

    BUIENRADAR = "buienradar"
    BUIENRADAR_PRIMARY = "buienradar_primary"
    BUIENALARM = "buienalarm"
    BUIENALARM_PRIMARY = "buienalarm_primary"
    COMBINED = "combined"


DEFAULT_DATA_SOURCE = DataSourceMode.COMBINED
