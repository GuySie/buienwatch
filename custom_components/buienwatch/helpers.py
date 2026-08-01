"""Pure rain-forecast logic: combining sources, bar graph, gauge values.

Deliberately free of Home Assistant imports so it can be exercised directly
against fixture data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .api import RainSample
from .const import (
    BAR_GRAPH_SEGMENT_MINUTES,
    BAR_GRAPH_SEGMENTS,
    BAR_MAX_CHAR,
    BAR_THRESHOLDS,
    RAIN_THRESHOLD_MM_PER_HOUR,
    SAMPLE_GRID_MINUTES,
)

_SAMPLES_PER_SEGMENT = BAR_GRAPH_SEGMENT_MINUTES // SAMPLE_GRID_MINUTES
_WINDOW = timedelta(minutes=BAR_GRAPH_SEGMENTS * BAR_GRAPH_SEGMENT_MINUTES)
_GRID = timedelta(minutes=SAMPLE_GRID_MINUTES)
_SLOT_COUNT = BAR_GRAPH_SEGMENTS * _SAMPLES_PER_SEGMENT


@dataclass(frozen=True)
class GaugeResult:
    """Numeric values derived from a combined forecast, for gauge sensors."""

    current: float | None
    peak: float | None
    minutes_until_start: int | None
    minutes_until_stop: int | None


def _floor_to_grid(moment: datetime, grid: timedelta) -> datetime:
    """Round a datetime down to the start of its grid slot."""
    grid_minutes = int(grid.total_seconds() // 60)
    moment = moment.replace(second=0, microsecond=0)
    overshoot = moment.minute % grid_minutes
    return moment - timedelta(minutes=overshoot)


def _snap_to_grid(
    samples: list[RainSample], *, grid_start: datetime, grid: timedelta, slot_count: int
) -> dict[int, float]:
    """Map samples onto grid slot indices, keeping the max value per slot."""
    slots: dict[int, float] = {}
    for sample in samples:
        offset = (sample.time - grid_start) / grid
        idx = round(offset)
        if 0 <= idx < slot_count:
            slots[idx] = max(slots.get(idx, sample.mm_per_hour), sample.mm_per_hour)
    return slots


def combine_samples(
    buienradar: list[RainSample] | None,
    buienalarm: list[RainSample] | None,
    *,
    now: datetime,
    window: timedelta = _WINDOW,
    grid: timedelta = _GRID,
) -> list[RainSample]:
    """Combine both sources onto a shared time grid, taking the max per slot.

    Slots with no data from either source are treated as dry (0.0 mm/h).
    Always returns ``window / grid`` samples, in order, starting at the grid
    slot containing ``now``.
    """
    slot_count = int(window / grid)
    grid_start = _floor_to_grid(now, grid)

    buienradar_slots = _snap_to_grid(
        buienradar or [], grid_start=grid_start, grid=grid, slot_count=slot_count
    )
    buienalarm_slots = _snap_to_grid(
        buienalarm or [], grid_start=grid_start, grid=grid, slot_count=slot_count
    )

    combined: list[RainSample] = []
    for idx in range(slot_count):
        candidates = [
            slots[idx]
            for slots in (buienradar_slots, buienalarm_slots)
            if idx in slots
        ]
        value = max(candidates) if candidates else 0.0
        combined.append(RainSample(time=grid_start + idx * grid, mm_per_hour=value))
    return combined


def _char_for_intensity(mm_per_hour: float) -> str:
    """Map an intensity to its bar-graph character."""
    for threshold, char in BAR_THRESHOLDS:
        if mm_per_hour < threshold:
            return char
    return BAR_MAX_CHAR


def build_bar_graph(samples: list[RainSample]) -> str:
    """Render combined samples as an 8-character Unicode bar graph.

    Batches consecutive samples into 15-minute segments, taking the max
    intensity per segment — a direct port of the existing Jinja2 templates.
    """
    chars: list[str] = []
    for segment_start in range(0, _SLOT_COUNT, _SAMPLES_PER_SEGMENT):
        segment = samples[segment_start : segment_start + _SAMPLES_PER_SEGMENT]
        if not segment:
            break
        peak = max(sample.mm_per_hour for sample in segment)
        chars.append(_char_for_intensity(peak))
    return "".join(chars)


def compute_gauges(
    samples: list[RainSample],
    *,
    threshold: float = RAIN_THRESHOLD_MM_PER_HOUR,
    grid_minutes: int = SAMPLE_GRID_MINUTES,
) -> GaugeResult:
    """Derive current/peak intensity and start/stop countdowns from samples."""
    if not samples:
        return GaugeResult(None, None, None, None)

    current = samples[0].mm_per_hour
    peak = max(sample.mm_per_hour for sample in samples)

    start_idx = next(
        (i for i, sample in enumerate(samples) if sample.mm_per_hour >= threshold),
        None,
    )
    if start_idx is None:
        return GaugeResult(current, peak, None, None)

    minutes_until_start = start_idx * grid_minutes
    stop_idx = next(
        (
            j
            for j in range(start_idx + 1, len(samples))
            if samples[j].mm_per_hour < threshold
        ),
        None,
    )
    minutes_until_stop = stop_idx * grid_minutes if stop_idx is not None else None

    return GaugeResult(current, peak, minutes_until_start, minutes_until_stop)
