"""Telemetry processing pipeline.

This module turns raw sensor lines such as ``"roof;3;71.6;F"`` into a single
site score.  The work is split into eight small stages that are executed in
order by :class:`Pipeline`:

1. ``parse``      - split raw text lines into record dictionaries
2. ``validate``   - drop records that are malformed
3. ``normalize``  - express every reading in degrees Celsius
4. ``dedupe``     - keep the last reading per (sensor, tick) and sort
5. ``smooth``     - trailing moving average, computed per sensor
6. ``clip``       - clamp readings into the allowed band
7. ``aggregate``  - per-sensor summary statistics
8. ``score``      - weighted site score

Every stage is a small class with a ``run(records)`` method that returns a new
list; stages never modify the objects they receive.
"""

from __future__ import annotations

import math
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIELD_SEPARATOR = ";"
COMMENT_MARKER = "#"
RECORD_FIELDS = ("sensor", "tick", "value", "unit")
DEFAULT_WINDOW = 3
DEFAULT_LOWER_BOUND = -40.0
DEFAULT_UPPER_BOUND = 85.0
DEFAULT_WEIGHTS = {"hall": 1.0, "roof": 2.0, "lab": 1.5, "cellar": 0.5}
DEFAULT_WEIGHT = 1.0
VALUE_DECIMALS = 3
SCORE_DECIMALS = 4
ABSOLUTE_ZERO_C = -273.15

# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------


def make_record(sensor, tick, value, unit):
    """Build a record dictionary from its four fields."""
    return {"sensor": sensor, "tick": tick, "value": value, "unit": unit}


def with_value(record, value):
    """Return a copy of ``record`` whose ``value`` has been replaced."""
    updated = dict(record)
    updated["value"] = value
    return updated


def record_key(record):
    """Identity of a reading: the ``(sensor, tick)`` pair."""
    return (record["sensor"], record["tick"])


def sensor_of(record):
    """Return the sensor name stored in ``record``."""
    return record["sensor"]


def tick_of(record):
    """Return the integer tick stored in ``record``."""
    return record["tick"]


def value_of(record):
    """Return the numeric reading stored in ``record``."""
    return record["value"]


def unit_of(record):
    """Return the unit letter stored in ``record``."""
    return record["unit"]


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def strip_comment(line):
    """Remove an inline ``#`` comment and surrounding whitespace."""
    marker = line.find(COMMENT_MARKER)
    if marker >= 0:
        line = line[:marker]
    return line.strip()


def is_blank(line):
    """True for lines that carry no data once comments are stripped."""
    return strip_comment(line) == ""


def split_fields(line):
    """Split a raw line on the field separator, trimming each piece."""
    return [piece.strip() for piece in line.split(FIELD_SEPARATOR)]


def parse_int(text):
    """Parse ``text`` as an integer, returning ``None`` when it is not one."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_float(text):
    """Parse ``text`` as a float, returning ``None`` for garbage input."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def normalize_sensor(text):
    """Lower-case a sensor name; empty names become ``None``."""
    name = (text or "").strip().lower()
    return name or None


def normalize_unit(text):
    """Upper-case a unit letter; anything but a single letter becomes ``None``."""
    unit = (text or "").strip().upper()
    if len(unit) != 1 or not unit.isalpha():
        return None
    return unit


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def round_value(x, decimals=VALUE_DECIMALS):
    """Round ``x`` to the module-wide number of decimals."""
    return round(float(x), decimals)


def is_finite(x):
    """True for real numbers that are neither NaN nor infinite."""
    return isinstance(x, (int, float)) and math.isfinite(x)


def mean(values):
    """Arithmetic mean; an empty sequence has mean ``0.0``."""
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values):
    """Population variance (divides by ``n``, not ``n - 1``)."""
    values = list(values)
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    return sum((v - centre) ** 2 for v in values) / len(values)


def stdev(values):
    """Population standard deviation, the square root of :func:`variance`."""
    return math.sqrt(variance(values))


def clamp(x, lower, upper):
    """Constrain ``x`` to the closed interval ``[lower, upper]``."""
    if x < lower:
        return lower
    if x > upper:
        return upper
    return x


def weighted_mean(pairs):
    """Mean of ``(value, weight)`` pairs; zero total weight yields ``0.0``."""
    total_weight = 0.0
    total = 0.0
    for value, weight in pairs:
        total += value * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return total / total_weight


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------


def fahrenheit_to_celsius(value):
    """Convert degrees Fahrenheit to degrees Celsius."""
    return (value - 32.0) * 5.0 / 9.0


def kelvin_to_celsius(value):
    """Convert kelvin to degrees Celsius."""
    return value + ABSOLUTE_ZERO_C


def celsius_to_celsius(value):
    """Identity conversion, kept so that every known unit has a converter."""
    return value


CONVERTERS = {
    "C": celsius_to_celsius,
    "F": fahrenheit_to_celsius,
    "K": kelvin_to_celsius,
}


def is_known_unit(unit):
    """True when a converter to Celsius exists for ``unit``."""
    return unit in CONVERTERS


def to_celsius(value, unit):
    """Convert ``value`` expressed in ``unit`` to degrees Celsius."""
    try:
        converter = CONVERTERS[unit]
    except KeyError:
        raise StageError("unknown unit %r" % (unit,))
    return converter(value)


def is_physical(value_c):
    """True when a Celsius reading is at or above absolute zero."""
    return value_c >= ABSOLUTE_ZERO_C


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------


def group_by_sensor(records):
    """Bucket records by sensor, preserving their relative order."""
    groups = {}
    for record in records:
        groups.setdefault(sensor_of(record), []).append(record)
    return groups


def flatten_groups(groups):
    """Concatenate the per-sensor lists in sorted sensor order."""
    flat = []
    for sensor in sorted(groups):
        flat.extend(groups[sensor])
    return flat


def sort_records(records):
    """Return records ordered by ``(sensor, tick)``."""
    return sorted(records, key=record_key)


def dedupe_keep_last(records):
    """Drop earlier readings that share a key with a later one."""
    latest = {}
    for record in records:
        latest[record_key(record)] = record
    return list(latest.values())


def values_of(records):
    """Extract the readings of ``records`` as a plain list."""
    return [value_of(record) for record in records]


def ticks_of(records):
    """Extract the ticks of ``records`` as a plain list."""
    return [tick_of(record) for record in records]


def is_sorted_by_tick(series):
    """True when ``series`` is in non-decreasing tick order."""
    ticks = ticks_of(series)
    return all(a <= b for a, b in zip(ticks, ticks[1:]))


# ---------------------------------------------------------------------------
# Trace and reporting
# ---------------------------------------------------------------------------


class Trace:
    """Counts of items entering and leaving each stage."""

    def __init__(self):
        self.entries = []

    def add(self, stage_name, before, after):
        """Record how a stage changed the number of items."""
        self.entries.append((stage_name, before, after))

    def as_lines(self):
        """Human readable rendering, one line per stage."""
        lines = []
        for name, before, after in self.entries:
            lines.append("%-10s %4d -> %4d" % (name, before, after))
        return lines


def weight_for_sensor(sensor, weights=None):
    """Weight used by the score stage; unknown sensors weigh ``DEFAULT_WEIGHT``."""
    table = DEFAULT_WEIGHTS if weights is None else weights
    return float(table.get(sensor, DEFAULT_WEIGHT))


def format_summary(summary):
    """One-line description of a per-sensor summary."""
    return "%s: n=%d mean=%.3f min=%.3f max=%.3f sd=%.3f" % (
        summary["sensor"], summary["count"], summary["mean"],
        summary["min"], summary["max"], summary["stdev"],
    )


def render_report(result):
    """Render the pipeline result as a multi-line string."""
    lines = ["trace:"]
    lines.extend("  " + line for line in result["trace"].as_lines())
    lines.append("sensors:")
    for summary in result["summaries"]:
        lines.append("  " + format_summary(summary))
    lines.append("score: %.4f" % result["score"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage base class
# ---------------------------------------------------------------------------


class StageError(ValueError):
    """Raised when a stage receives data it cannot process."""


class Stage:
    """Base class for pipeline stages.

    Subclasses set ``name`` and implement :meth:`run`, which takes a list and
    returns a *new* list.  The input list and its items must be left untouched
    so that the pipeline trace stays trustworthy.
    """

    name = "stage"

    def run(self, records):
        """Transform ``records`` and return the result as a new list."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Stages 1-4: parse, validate, normalize, dedupe
# ---------------------------------------------------------------------------


class ParseStage(Stage):
    """Stage 1: turn raw text lines into record dictionaries.

    Blank lines and comments are skipped.  Lines with too few fields become
    records with ``None`` in the missing slots so that the validate stage can
    reject them uniformly.
    """

    name = "parse"

    def parse_line(self, line):
        """Parse one non-blank line into a record."""
        fields = split_fields(strip_comment(line))
        while len(fields) < len(RECORD_FIELDS):
            fields.append("")
        sensor, tick, value, unit = fields[:4]
        return make_record(
            normalize_sensor(sensor),
            parse_int(tick),
            parse_float(value),
            normalize_unit(unit),
        )

    def run(self, lines):
        records = []
        for line in lines:
            if is_blank(line):
                continue
            records.append(self.parse_line(line))
        return records


class ValidateStage(Stage):
    """Stage 2: drop malformed readings.

    A record survives when it has a sensor name, a non-negative tick, a finite
    value and a unit for which a converter exists.
    """

    name = "validate"

    def is_valid(self, record):
        """True when every field of ``record`` is usable."""
        if sensor_of(record) is None:
            return False
        tick = tick_of(record)
        if tick is None or tick < 0:
            return False
        if not is_finite(value_of(record)):
            return False
        return is_known_unit(unit_of(record))

    def run(self, records):
        return [record for record in records if self.is_valid(record)]


class NormalizeStage(Stage):
    """Stage 3: express every reading in degrees Celsius.

    Readings below absolute zero are physically impossible and are dropped
    here rather than in the validate stage, because the check only makes
    sense once the unit is known to be Celsius.
    """

    name = "normalize"

    def convert(self, record):
        """Return a copy of ``record`` converted to Celsius."""
        celsius = to_celsius(value_of(record), unit_of(record))
        updated = with_value(record, round_value(celsius))
        updated["unit"] = "C"
        return updated

    def run(self, records):
        converted = []
        for record in records:
            candidate = self.convert(record)
            if is_physical(value_of(candidate)):
                converted.append(candidate)
        return converted


class DedupeStage(Stage):
    """Stage 4: keep one reading per ``(sensor, tick)`` and sort.

    When the same sensor reports the same tick more than once, the reading
    that appears *last* in the input wins.  The output is ordered by sensor
    and then by tick so that later stages can rely on time order.
    """

    name = "dedupe"

    def run(self, records):
        return sort_records(dedupe_keep_last(records))


# ---------------------------------------------------------------------------
# Stages 5-8: smooth, clip, aggregate, score
# ---------------------------------------------------------------------------


class SmoothStage(Stage):
    """Stage 5: trailing moving average, computed per sensor.

    With a window of ``w`` the reading at position ``i`` of a sensor's series
    is replaced by the mean of the readings at positions ``i - w + 1`` through
    ``i`` inclusive, i.e. at most ``w`` readings.  Near the start of the
    series, where fewer than ``w`` readings are available, the mean of the
    available prefix is used, so the first reading is always left unchanged.
    """

    name = "smooth"

    def __init__(self, window=DEFAULT_WINDOW):
        self.window = max(1, int(window))

    def window_start(self, index):
        """Position of the first reading in the window that ends at ``index``."""
        return max(0, index - self.window)

    def smooth_series(self, series):
        """Smooth one sensor's readings, which must already be in tick order."""
        if not is_sorted_by_tick(series):
            raise StageError("series for %r is not in tick order" % sensor_of(series[0]))
        values = values_of(series)
        smoothed = []
        for index, record in enumerate(series):
            window = values[self.window_start(index):index + 1]
            smoothed.append(with_value(record, round_value(mean(window))))
        return smoothed

    def run(self, records):
        groups = group_by_sensor(records)
        smoothed = {}
        for sensor, series in groups.items():
            smoothed[sensor] = self.smooth_series(series)
        return flatten_groups(smoothed)


class ClipStage(Stage):
    """Stage 6: clamp readings into the allowed band.

    Readings outside ``[lower, upper]`` are pulled back to the nearest bound
    rather than dropped, so that a sensor with a single wild reading keeps
    its full history.
    """

    name = "clip"

    def __init__(self, lower=DEFAULT_LOWER_BOUND, upper=DEFAULT_UPPER_BOUND):
        if lower > upper:
            raise StageError("lower bound %r above upper bound %r" % (lower, upper))
        self.lower = float(lower)
        self.upper = float(upper)

    def run(self, records):
        clipped = []
        for record in records:
            clipped.append(with_value(record, clamp(value_of(record), self.lower, self.upper)))
        return clipped


class AggregateStage(Stage):
    """Stage 7: summarise each sensor.

    The output is a list of summary dictionaries (one per sensor, in sorted
    sensor order) rather than a list of records.
    """

    name = "aggregate"

    def summarise(self, sensor, series):
        """Build the summary dictionary for one sensor."""
        values = values_of(series)
        return {
            "sensor": sensor,
            "count": len(values),
            "mean": round_value(mean(values)),
            "min": min(values),
            "max": max(values),
            "stdev": round_value(stdev(values)),
            "first_tick": min(ticks_of(series)),
            "last_tick": max(ticks_of(series)),
        }

    def run(self, records):
        groups = group_by_sensor(records)
        return [self.summarise(sensor, groups[sensor]) for sensor in sorted(groups)]


class ScoreStage(Stage):
    """Stage 8: fold the per-sensor summaries into a single site score.

    The score is the weighted mean of the per-sensor means, weighted by
    :func:`weight_for_sensor`, rounded to ``SCORE_DECIMALS`` places.  It is
    returned as a bare float rather than a list.
    """

    name = "score"

    def __init__(self, weights=None):
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)

    def run(self, summaries):
        pairs = [
            (summary["mean"], weight_for_sensor(summary["sensor"], self.weights))
            for summary in summaries
        ]
        return round(weighted_mean(pairs), SCORE_DECIMALS)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class Pipeline:
    """Run a list of stages in order and keep a trace of item counts."""

    def __init__(self, stages):
        self.stages = list(stages)

    def run(self, lines):
        """Execute every stage and return a result dictionary."""
        trace = Trace()
        payload = list(lines)
        snapshots = {}
        for stage in self.stages:
            before = len(payload) if isinstance(payload, list) else 1
            payload = stage.run(payload)
            after = len(payload) if isinstance(payload, list) else 1
            trace.add(stage.name, before, after)
            snapshots[stage.name] = payload
        return {
            "score": snapshots.get("score", payload),
            "summaries": snapshots.get("aggregate", []),
            "records": snapshots.get("clip", []),
            "trace": trace,
        }


def build_pipeline(window=DEFAULT_WINDOW, lower=DEFAULT_LOWER_BOUND,
                   upper=DEFAULT_UPPER_BOUND, weights=None):
    """Assemble the standard eight-stage pipeline in execution order."""
    return Pipeline([
        ParseStage(),
        ValidateStage(),
        NormalizeStage(),
        DedupeStage(),
        SmoothStage(window),
        ClipStage(lower, upper),
        AggregateStage(),
        ScoreStage(weights),
    ])


def run_pipeline(lines, **options):
    """Convenience wrapper: build the default pipeline and return the score."""
    return build_pipeline(**options).run(lines)["score"]


# ---------------------------------------------------------------------------
# Command line interface
# ---------------------------------------------------------------------------


def read_lines(path):
    """Read raw lines from ``path``, or from stdin when ``path`` is ``"-"``."""
    if path == "-":
        return sys.stdin.read().splitlines()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().splitlines()


def main(argv=None):
    """Command line entry point: ``python3 processor.py readings.txt``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    path = argv[0] if argv else "-"
    result = build_pipeline().run(read_lines(path))
    print(render_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
