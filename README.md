# Buienwatch

A Home Assistant custom integration that follows a `person` or `device_tracker`
entity around and turns short-term Dutch/Belgian rain nowcasts (Buienradar +
Buienalarm) into sensors — including a compact text bar graph that's a good
fit for an Apple Watch Text Image complication.

Add the integration once per person/tracker you want a rain forecast for. On
every poll it reads that entity's current `latitude`/`longitude`, fetches the
selected source(s) for that location, and — when using both — combines them
by taking the worst-case / highest intensity per time slot.

> Both APIs used here are unofficial/reverse-engineered (no API key, no
> official documentation) — they may change or break without notice.
> Buienradar only works within the Netherlands and Belgium and returns an
> error for any other location. Buienalarm will return data anywhere in the
> world, but its accuracy drops the further you get from the Netherlands/
> Belgium — it's backed by an actual radar composite there and in a wider
> Western Europe area (Germany, Switzerland, Czechia, Luxembourg), falling
> back to a coarser global estimate everywhere else. This integration is
> built and tested for the Netherlands and Belgium; treat other locations as
> unsupported.

## Sensors

Each configured tracker becomes its own device with:

- **Forecast** — an 8-character Unicode bar graph (`▁▂▃▄▅▆▇█▓`) covering the
  next 2 hours in 15-minute segments. Drop this sensor's state straight into
  a Text Image complication.
- **Current Intensity** / **Peak Intensity** — mm/h gauges for right now and
  the worst point in the forecast window.
- **Starts In** / **Stops In** — minutes until rain starts/stops, `unknown`
  when not applicable.
- Two diagnostic sensors (disabled by default) exposing the raw Buienradar
  and Buienalarm sample series, for building your own templates/automations.
- **Data Source** — a select entity, right on the device page, to choose:
  - **Buienradar only** / **Buienalarm only** — poll a single source, no fallback.
  - **Buienradar, fall back to Buienalarm** / **Buienalarm, fall back to Buienradar** —
    poll one source; only query the other if the first one errors or is unavailable.
  - **Combined** — poll both every time and take the worst-case value per time slot.

  Switching takes effect immediately (no reload), and only the source(s) the
  current mode actually needs get polled.

## Installation

### HACS

Add this repository as a custom repository in HACS (category: Integration),
then install "Buienwatch" and restart Home Assistant.

### Manual

Copy `custom_components/buienwatch` into your Home Assistant config's
`custom_components/` directory and restart.

## Configuration

Settings → Devices & Services → Add Integration → **Buienwatch**, then pick
the `person` or `device_tracker` entity to follow. Repeat to track additional
people. The poll interval (default 5 minutes) can be changed afterwards via
the integration's options.

## Apple Watch complication

Point a Home Assistant Companion app Text Image complication at the
**Forecast** sensor's state for a rain bar graph that follows you around —
the successor to [the original Node-RED/template-based
setup](https://style.oversubstance.net/2021/07/buienalarm-buienradar-apple-watch-complication-using-home-assistant/).
