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
# final threshold map to BAR_MAX_CHAR. The 0.1-10.0 mm/h boundaries are a
# constant-ratio (~x1.93 per bucket) split of that range across the 7
# non-dry buckets — i.e. each bucket is "roughly double the previous bucket's
# rain rate" — rather than the arbitrary round numbers this replaced
# (0.5/1.0/1.5/2.0/3.5/5.0, no consistent ratio between them). This is
# derived purely from the fixed 0.1-10.0 endpoints, not from any observed
# sample, so it can't be invalidated by more/different data the way a
# frequency-fitted set of boundaries could be. Each boundary was individually
# checked against Buienradar's `10 ** ((code-109)/32)` code ladder to confirm
# it lands inside a gap between two consecutive codes (never splitting a
# single code's cluster in two). One known tradeoff: this leaves the 0.1-0.20
# bucket (▂) thin — cross-checked against both sources' real capture data,
# genuinely few readings land in that narrow band specifically (not a
# quantization artifact — Buienalarm's continuous values show the same
# thinness), so it's a deliberate accepted tradeoff, not a bug.
BAR_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.1, "▁"),
    (0.20, "▂"),
    (0.37, "▃"),
    (0.72, "▄"),
    (1.4, "▅"),
    (2.7, "▆"),
    (5.2, "▇"),
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
