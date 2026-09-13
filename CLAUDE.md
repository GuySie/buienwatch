# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/buienwatch/`) that follows a `person`/`device_tracker`
entity's current location and combines short-term Dutch/Belgian rain nowcasts from Buienradar and Buienalarm
into sensors — including an 8-character Unicode bar graph suited for an Apple Watch Text Image complication.
See README.md for the user-facing description, installation, and sensor list.

## Commands

There is no bundled test suite, linter, or build step — this is a plain HA custom component (no `pyproject.toml`,
no packaging). Validation happens two ways:

- **Static/CI validation** — two GitHub Actions workflows run on every push (`.github/workflows/`):
  `validate-with-hassfest.yaml` (Home Assistant's own manifest/integration structure linter) and
  `validate-hacs.yml` (HACS repository requirements). Check their status with:
  ```
  gh run list --repo guysie/buienwatch --limit 5
  ```
- **Syntax check** — `python3 -m py_compile custom_components/buienwatch/*.py`
- **Logic testing without a Home Assistant install** — `helpers.py` and `api.py` deliberately have zero
  `homeassistant.*` imports (see Architecture below), so their functions (`combine_samples`, `build_bar_graph`,
  `compute_gauges`, `_buienradar_code_to_mm_per_hour`, `_resolve_buienradar_time`) can be exercised directly
  with a throwaway script and stdlib-only stubbing of `aiohttp` — no HA install or network access required.
  There's no committed test file for this yet; write one-off scratch scripts when validating changes to this logic.
- **End-to-end verification** requires a real (or dev-container) Home Assistant instance: copy
  `custom_components/buienwatch/` into its `custom_components/`, restart, and add the integration via the UI.
  `homeassistant` and `aiohttp` are not installed in this repo's environment.

## Architecture

**Coordinator-per-tracked-entity.** Each config entry tracks exactly one `person`/`device_tracker` and owns one
`BuienwatchDataUpdateCoordinator` (`coordinator.py`), becoming its own HA device. Multiple people/trackers means
multiple config entries — enforced via `async_set_unique_id(tracked_entity_id)` in `config_flow.py`. On every poll,
the coordinator re-reads the tracked entity's *current* `latitude`/`longitude` from `hass.states` before fetching —
so a moving phone gets forecasts for wherever it currently is, not a fixed location captured at setup time.

**Pure logic is deliberately isolated from Home Assistant.** `api.py` (HTTP fetch + raw parsing) and `helpers.py`
(combining sources, building the bar graph, computing gauge values) import nothing from `homeassistant.*` — only
stdlib and `aiohttp`. `coordinator.py` is the thin orchestration layer that calls into both and wraps the result
in `BuienwatchData` for entities to read. Keep new forecast-math changes in `helpers.py`/`api.py` if possible;
that's what makes them testable without a full HA install (see Commands above).

**Two independently-cadenced sources, reconciled onto one grid.** Buienradar returns bare `"XXX|HH:MM"` lines
(code 000-255, converted via `10 ** ((code-109)/32)` to mm/h) with no date — `_resolve_buienradar_time()` in
`api.py` resolves these against Europe/Amsterdam local time specifically (`zoneinfo.ZoneInfo`, not the host's
system timezone, which is often UTC in Docker deployments and would otherwise misalign samples by 1-2 hours).
Buienalarm returns JSON with Unix timestamps already in mm/h. `combine_samples()` in `helpers.py` snaps both
source's samples onto a shared 5-minute UTC-normalized grid and takes the **max** value per slot where both have
data — this is a deliberate design choice (worst-case/cautious forecast), not an average or fallback chain.
Grid slots with no data from either source are treated as dry (`0.0`), so "no rain" and "missing data" are
currently indistinguishable at the sensor level.

**Entity/sensor layout** (`entity.py`, `sensor.py`, `select.py`): `BuienwatchEntity` is the shared `CoordinatorEntity`
base, keyed by `entry.entry_id` for `DeviceInfo`. Each tracked entity gets 7 sensors — 5 enabled by default (bar
graph, current/peak intensity, minutes-until-start/stop) and 2 diagnostic raw-sample sensors per source, disabled
by default (`EntityCategory.DIAGNOSTIC`, `entity_registry_enabled_default = False`), for anyone who wants to build
custom templates against the raw per-source series (mirrors the old Node-RED `sensor.*.data` habit this
integration replaces) — plus one `EntityCategory.CONFIG` select entity (`BuienwatchDataSourceSelect`) to choose
the `DataSourceMode` right from the device page: Buienradar-only, Buienalarm-only, Combined, or one of two
primary-with-fallback modes (try one source, only query the other if the first errors/is unavailable).

**Options are applied live, never via reload.** Both `CONF_POLL_INTERVAL` and `CONF_DATA_SOURCE` live in
`entry.options`, but neither change triggers `async_reload` (deliberately — a reload would flicker every entity
unavailable, which defeats the point of a device-page select for something meant to feel instant):
- `coordinator.data_source_mode` is a *property* that reads `entry.options[CONF_DATA_SOURCE]` fresh on every poll —
  no caching, so a mode change just takes effect on the next `_async_update_data()` call.
- The poll interval is still cached once at coordinator `__init__` (as a `DataUpdateCoordinator` constructor arg),
  but `__init__.py`'s options-update listener patches `coordinator.update_interval` directly in place, which
  `DataUpdateCoordinator` re-reads when it reschedules its next refresh — no reload needed there either.
- `select.py`'s `async_select_option()` persists the new mode via `hass.config_entries.async_update_entry()` *and*
  calls `coordinator.async_request_refresh()` immediately, so switching source doesn't wait for the next scheduled
  poll. This mirrors the pattern in the sibling `ha-tuneshine` repo's `select.py` (source media player selection) —
  check that file if extending this further.

**Fetch strategy is mode-dependent** (`coordinator._fetch_for_mode()`), and only Combined mode fetches both sources
unconditionally. `_safe_fetch()` wraps a single source's fetch and turns any `BuienwatchApiError`/unexpected
exception into `None` (logged) rather than raising, so per-mode dispatch never needs its own try/except:
- `BUIENRADAR` / `BUIENALARM` — fetch only that one source. No fallback: if it fails, the update fails.
- `COMBINED` — fetch both concurrently via `asyncio.gather()` regardless of each other's outcome; one failing still
  lets the other serve data.
- `BUIENRADAR_PRIMARY` / `BUIENALARM_PRIMARY` — `_fetch_with_fallback()` fetches the primary first and *only*
  fetches the secondary if the primary returned `None`, sequentially (not concurrently), specifically to avoid
  hitting the non-primary source on every poll when the primary is healthy. `BUIENALARM_PRIMARY` calls
  `_fetch_with_fallback(buienalarm, buienradar, ...)` and swaps the returned `(primary, fallback)` pair back into
  `(buienradar, buienalarm)` order before returning — get this swap wrong and the samples end up attributed to the
  wrong source's sensor/attributes.
`_async_update_data()` raises `UpdateFailed` only when *both* `buienradar_samples` and `buienalarm_samples` end up
`None` — which happens either because a single/fallback mode's only available source(s) all failed, or (Combined
only) both sources failed independently.

## Geographic coverage (spotchecked 2026-08-01, live upstream behavior)

Despite the "Dutch/Belgian" framing above, the two upstream APIs behave very differently outside NL/BE:

- **Buienradar hard-rejects non-NL/BE coordinates.** `gps.buienradar.nl/getrr.php` returns the plain-text body
  `Not found: location must be inside the Netherlands or Belgium.` for any lat/lon outside NL/BE — confirmed for
  DE, FR, UK, US, DK, ES, PL, IT, NO, SE, IE, CZ, CH. This already degrades cleanly: no `|` lines parse, so
  `async_fetch_buienradar()` raises `BuienwatchParseError`, which `_safe_fetch()` turns into `None`.
- **Buienalarm always returns HTTP 200 everywhere on Earth**, but `imn-rust-lb.infoplaza.io/.../timeseries/` responses
  carry a `summary.source` field revealing three real backing-data tiers, not a generic fake fallback:
  - `radar-nl` — NL, BE, and also western Germany near the border (e.g. Cologne, 50.94/6.96)
  - `radar-westeurope` — wider Western Europe: Berlin, Czechia, Switzerland, Luxembourg, Kiel, Strasbourg
  - `radar-world` — everywhere else observed: Paris, London, Madrid, Rome, Warsaw, Vienna, Lyon, Budapest,
    Istanbul, and non-EU spots (New York, Tokyo, Sydney, Nairobi)

  All spotcheck queries returned `precipitationrate: 0.0` (dry at test time), so `radar-world`'s accuracy during
  actual rain is unverified — it's presumably a coarser satellite-based global estimate versus true radar for the
  other two tiers. If Buienwatch is ever extended to support trackers outside NL/BE, Buienalarm-only mode already
  returns numeric data worldwide, but `radar-world` results should be flagged as lower-confidence; Buienradar
  should keep being skipped there (no code change needed — it already fails gracefully via `_safe_fetch`).

## Bar graph thresholds (BAR_THRESHOLDS, re-derived 2026-09-13)

`BAR_THRESHOLDS` in `const.py` used to be evenly-spaced round numbers (0.1/0.5/1.0/1.5/2.0/3.5/5.0/10.0 mm/h),
not derived from real data or the encoding. A ~12h real-world capture of both sources at one location (see
`reference/` — gitignored, a local-only stdlib poller + analysis script, not part of the published repo) led
through two approaches before landing on the current one:

**Attempt 1 (rejected): fit boundaries to observed code frequency.** Buienradar's `10 ** ((code-109)/32)`
conversion only produces a fixed ladder of ~40 distinct mm/h values in practice, not a continuum, and two codes
— 0.1000 and 0.2054 mm/h — dominated the low end of the capture, together accounting for over a third of every
non-dry reading. The original 0.1–0.5 bucket lumped both together with two more codes, absorbing ~60% of all
"raining" slots while 1.0–1.5/1.5–2.0 got only a handful each. Boundaries were placed in the actual gaps
*between* codes (never splitting a cluster) and chosen to balance bucket populations against that capture —
but when the same 12h capture ran to completion (72 vs. the 59 polls analyzed mid-run), the boundaries no
longer balanced well: a second rain pulse late in the window shifted where the mass actually was. This is
overfitting in a narrow sense — not "wrong gaps" (those are fixed by the formula, not the sample), but "gaps
chosen by weighting them against one session's code *frequency*," which is a real-world weather statistic that
a single location/session can't reliably estimate.

**Attempt 2 (adopted): constant-ratio split, ignoring observed frequency entirely.** Since consecutive codes
differ by a fixed ratio (`10 ** (1/32)` ≈ ×1.0746), the full 0.1–10.0 mm/h range was split into 7 buckets at a
constant ratio of ×1.9307 each — i.e. every bucket is "roughly double the previous bucket's rain rate" — using
only the fixed formula endpoints, not any sample's frequency. **Live thresholds: 0.1 / 0.20 / 0.37 / 0.72 / 1.4
/ 2.7 / 5.2 / 10.0.** Each boundary was individually checked to confirm it still lands inside a gap between two
consecutive Buienradar codes (so no cluster gets split), but *which* gap to use was chosen by the ratio alone,
not by which gap had more/less data in this capture — so it can't be invalidated by more data the way Attempt 1
was.

Known accepted tradeoff (not a bug): this leaves the 0.1–0.20 bucket (▂) thin. Cross-checked against both
sources independently — including Buienalarm, whose `precipitationrate` is a continuous float with no code
ladder to blame — genuinely few readings land in that narrow band specifically, so it's a real property of the
underlying rain-rate distribution (very light rain doesn't linger there long), not a quantization artifact.
Deliberately left as-is rather than nudging that one boundary to be more "usable."

Still true regardless of which attempt: the top of the scale (▇/█/▓, ≥2.7 mm/h) remains thin in this capture —
one moderate rain event, never anything deep inside the ▓ overflow bucket (just one boundary-exact 10.0 mm/h
reading). Re-running the `reference/` capture during an actual heavy/convective rain event would be the way to
gain confidence there, though the constant-ratio derivation itself doesn't depend on that the way Attempt 1 did.

## Known gaps (see git log / commit messages for context)

- HACS validation (`validate-hacs.yml`) currently fails on the "brands" check — `buienwatch` isn't registered in
  the community [home-assistant/brands](https://github.com/home-assistant/brands) repo. That requires a separate
  PR there with icon assets; it doesn't block installing via HACS as a custom repository.
- Buienalarm's actual forecast horizon/interval hasn't been confirmed against a live response — the design
  degrades gracefully if it's shorter than the 2-hour window, but that makes "dry" and "short horizon"
  indistinguishable in the combined output.
