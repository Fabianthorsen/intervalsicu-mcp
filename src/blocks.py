"""Block-level aggregation over a range of activities (ADR-0003).

The tools in this module's callers answer questions about a *block* — a week,
a month, a training camp — rather than a session. Pulling every activity in
full to answer them would flood the caller's context with fields nobody reads,
so the fetch is scoped with the API's `fields` parameter and everything here
reduces many activities to a handful of numbers.

Two shapes need normalising before anything can be summed.

Zone times arrive in two different formats depending on the metric: power
comes back as ``[{"id": "Z2", "secs": 1800}, ...]`` while heart rate and pace
come back as bare positional arrays ``[600, 1800, ...]`` whose index is the
zone. ``zone_secs`` flattens both to ``{"Z1": secs, ...}`` so a mixed block
can be pooled without the caller caring which sport produced which row.

And "polarisation" means two different things. ``Activity.polarization_index``
is intervals.icu's own scalar, computed per activity by a formula we do not
reimplement; it is passed through untouched. The pooled Z1-2 / Z3 / Z4+ split
this module computes is a *different quantity* — a time distribution, not an
index — so it is named ``intensity_split`` and never mixed with the native
field. Averaging per-activity indices would in any case weight a 30-minute
spin equally with a 5-hour ride.
"""

from collections import defaultdict
from datetime import date, datetime

# Pulled with the API's `fields` parameter. Everything here is either summed,
# bucketed or passed through; adding a field means adding a consumer for it.
SUMMARY_FIELDS = (
    "id",
    "name",
    "type",
    "start_date_local",
    "moving_time",
    "elapsed_time",
    "icu_training_load",
    "icu_intensity",
    "polarization_index",
    "compliance",
    "paired_event_id",
    "icu_zone_times",
    "icu_hr_zone_times",
    "pace_zone_times",
)

ZONE_TIME_FIELDS = {
    "power": "icu_zone_times",
    "hr": "icu_hr_zone_times",
    "pace": "pace_zone_times",
}

ZONE_BOUND_FIELDS = {
    "power": "icu_power_zones",
    "hr": "icu_hr_zones",
    "pace": "pace_zones",
}

METRICS = tuple(ZONE_TIME_FIELDS)

# The three-bucket model behind the 80/20-style rules: easy, moderate, hard.
# Boundaries are on zone number, so a 5-zone HR model and a 7-zone power model
# both land somewhere sensible.
EASY_MAX_ZONE = 2
MODERATE_MAX_ZONE = 3


def parse_local_date(value: str | None) -> date | None:
    """Pull the date out of a `start_date_local` ('2026-03-10T07:14:00')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def bucket_of(value: str | date | None, group_by: str) -> str | None:
    """Bucket key for a date: the ISO week's Monday, or 'YYYY-MM'.

    Weeks are ISO weeks and therefore start on Monday. No week-start-day
    setting is exposed anywhere in the athlete schema, so there is nothing to
    honour — an athlete whose intervals.icu UI starts weeks on Sunday will see
    buckets that do not line up with their screen.
    """
    day = value if isinstance(value, date) else parse_local_date(value)
    if day is None:
        return None
    if group_by == "month":
        return f"{day.year:04d}-{day.month:02d}"
    if group_by == "week":
        return date.fromordinal(day.toordinal() - day.weekday()).isoformat()
    raise ValueError(f"group_by must be 'week' or 'month', got '{group_by}'.")


def zone_number(zone_id: object, position: int) -> int:
    """Zone number from either an id ('Z2', 'z2', '2') or an array position."""
    text = str(zone_id or "").strip().lstrip("Zz")
    if text.isdigit():
        return int(text)
    return position + 1


def zone_secs(activity: dict, metric: str) -> dict[str, int]:
    """Normalise an activity's zone times to {'Z1': secs, ...} for one metric.

    Power arrives as a list of {id, secs} objects; heart rate and pace arrive
    as bare positional arrays. Returns {} when the activity has no times for
    that metric, which is the signal that it should be excluded rather than
    counted as zero.
    """
    if metric not in ZONE_TIME_FIELDS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}, got '{metric}'.")

    raw = activity.get(ZONE_TIME_FIELDS[metric])
    if not raw:
        return {}

    out: dict[str, int] = {}
    for position, entry in enumerate(raw):
        if isinstance(entry, dict):
            secs = entry.get("secs")
            number = zone_number(entry.get("id"), position)
        else:
            secs = entry
            number = position + 1
        if secs:
            out[f"Z{number}"] = out.get(f"Z{number}", 0) + int(secs)
    return out


def zone_bounds(activity: dict, metric: str) -> list[float]:
    """The activity's own zone upper bounds, in force when it was recorded.

    Judging adherence against today's zones would mark a session ridden at a
    lower FTP as non-compliant for holding the ceiling it was actually given.
    """
    if metric not in ZONE_BOUND_FIELDS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}, got '{metric}'.")
    raw = activity.get(ZONE_BOUND_FIELDS[metric])
    return [float(v) for v in raw] if raw else []


def zone_ceiling(activity: dict, metric: str, zone: str) -> float | None:
    """Upper bound of one zone for one activity, or None if it has no zones."""
    bounds = zone_bounds(activity, metric)
    number = zone_number(zone, 0)
    if not bounds or number < 1 or number > len(bounds):
        return None
    return bounds[number - 1]


def pool_zone_secs(per_activity: list[dict[str, int]]) -> dict[str, int]:
    """Sum normalised zone times across activities."""
    pooled: dict[str, int] = defaultdict(int)
    for secs_by_zone in per_activity:
        for zone, secs in secs_by_zone.items():
            pooled[zone] += secs
    return dict(sorted(pooled.items(), key=lambda kv: zone_number(kv[0], 0)))


def intensity_split(pooled: dict[str, int]) -> dict:
    """Pooled Z1-2 / Z3 / Z4+ time split, as seconds and percentages.

    This is a distribution, not intervals.icu's `polarization_index`. Computed
    from pooled seconds rather than by averaging per-activity values, so a long
    ride counts for more than a short one.
    """
    easy = moderate = hard = 0
    for zone, secs in pooled.items():
        number = zone_number(zone, 0)
        if number <= EASY_MAX_ZONE:
            easy += secs
        elif number <= MODERATE_MAX_ZONE:
            moderate += secs
        else:
            hard += secs

    total = easy + moderate + hard
    if not total:
        return {"total_secs": 0}

    return {
        "total_secs": total,
        "easy_secs": easy,
        "moderate_secs": moderate,
        "hard_secs": hard,
        "easy_pct": round(100 * easy / total, 1),
        "moderate_pct": round(100 * moderate / total, 1),
        "hard_pct": round(100 * hard / total, 1),
    }


def summarise_bucket(activities: list[dict], metric: str | None) -> dict:
    """Reduce one bucket's activities to totals, a sport split and zone time."""
    load = sum(a.get("icu_training_load") or 0 for a in activities)
    moving = sum(a.get("moving_time") or 0 for a in activities)

    by_sport: dict[str, dict] = {}
    for a in activities:
        sport = a.get("type") or "Unknown"
        row = by_sport.setdefault(sport, {"sessions": 0, "load": 0, "moving_time": 0})
        row["sessions"] += 1
        row["load"] += a.get("icu_training_load") or 0
        row["moving_time"] += a.get("moving_time") or 0

    summary = {
        "sessions": len(activities),
        "load": load,
        "moving_time": moving,
        "by_sport": dict(sorted(by_sport.items(), key=lambda kv: -kv[1]["load"])),
    }

    if metric:
        with_times = [z for z in (zone_secs(a, metric) for a in activities) if z]
        pooled = pool_zone_secs(with_times)
        summary["zone_secs"] = pooled
        summary["intensity_split"] = intensity_split(pooled)
        # Sessions without this metric are excluded from the split rather than
        # counted as zero: a padel match has no power, and silently folding it
        # in as 0 seconds would drag the easy percentage around.
        summary["sessions_without_metric"] = len(activities) - len(with_times)

    return summary


def summarise(activities: list[dict], group_by: str = "week", metric: str | None = None) -> dict:
    """Bucket a block of activities and reduce each bucket.

    Activities with an unparseable or missing `start_date_local` cannot be
    bucketed; they are counted in `undated` rather than dropped silently.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    undated = 0
    for a in activities:
        key = bucket_of(a.get("start_date_local"), group_by)
        if key is None:
            undated += 1
            continue
        buckets[key].append(a)

    result = {
        "group_by": group_by,
        "metric": metric,
        "buckets": {
            key: summarise_bucket(rows, metric)
            for key, rows in sorted(buckets.items())
        },
        "total": summarise_bucket(
            [a for rows in buckets.values() for a in rows], metric
        ),
    }
    if undated:
        result["undated"] = undated
    return result
