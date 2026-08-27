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


# --- forward fitness projection -------------------------------------------

# Impulse-response time constants. CTL and ATL are exponentially weighted
# averages of daily load over these windows; intervals.icu exposes the same
# constants per athlete, so a caller can override them rather than assume.
CTL_DAYS = 42
ATL_DAYS = 7


def decay(current: float, load: float, days: int) -> float:
    """One day of an exponentially weighted average: value + (load - value)/days."""
    if days <= 0:
        raise ValueError(f"days must be positive, got {days}.")
    return current + (load - current) / days


def date_range(start: date, end: date) -> list[date]:
    """Every date from start to end inclusive."""
    if end < start:
        raise ValueError(f"to_date {end} is before from_date {start}.")
    return [date.fromordinal(o) for o in range(start.toordinal(), end.toordinal() + 1)]


def event_load(event: dict) -> tuple[int, str]:
    """A planned event's load, and how firm that number is.

    'derived' means intervals.icu computed it from the workout's structured
    steps against the athlete's thresholds. 'target' means someone typed it in
    — the softer number, and the one an unstructured session ends up with.
    """
    derived = event.get("icu_training_load")
    if derived:
        return int(derived), "derived"
    target = event.get("load_target")
    if target:
        return int(target), "target"
    return 0, "none"


def planned_loads(events: list[dict]) -> dict[str, list[dict]]:
    """Group planned events by local date, keeping load and its firmness."""
    by_date: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        day = parse_local_date(event.get("start_date_local"))
        if day is None:
            continue
        load, source = event_load(event)
        by_date[day.isoformat()].append(
            {
                "event_id": event.get("id"),
                "name": event.get("name"),
                "load": load,
                "load_source": source,
                "moving_time": event.get("moving_time"),
            }
        )
    return dict(by_date)


def apply_overlay(
    by_date: dict[str, list[dict]], overlay: list[dict] | None
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Apply hypothetical changes in memory. Returns (new plan, per-entry echo).

    Nothing here writes to a calendar. Each entry names a `date`, and
    optionally an `event_id` to disambiguate a day holding more than one
    session. An entry may:

      - `skip: true`      drop the session (or the whole day)
      - `load: N`         set the load exactly
      - `moving_time: N`  scale the load by the duration ratio

    Scaling assumes the minutes removed were of average intensity, which is
    optimistic — sessions are usually trimmed from the easy tail — so the day
    is marked approximate. It requires both an existing load and duration to
    scale from and raises rather than guessing when either is missing.

    An entry whose date matches no planned session is an *addition*, not an
    error, so "what if I add 60 TSS on Thursday" needs no calendar write. The
    echo reports modified/skipped/added per entry precisely because a typo'd
    date would otherwise become a phantom session hidden inside a CTL number.
    """
    plan = {day: [dict(s) for s in sessions] for day, sessions in by_date.items()}
    echo: list[dict] = []
    if not overlay:
        return plan, echo

    for entry in overlay:
        day = entry.get("date")
        if not day:
            raise ValueError("Every overlay entry needs a 'date'.")
        event_id = entry.get("event_id")
        sessions = plan.get(day, [])
        if event_id is not None:
            sessions = [s for s in sessions if s.get("event_id") == event_id]

        if entry.get("skip"):
            if not sessions:
                echo.append({"date": day, "action": "no_match", "detail": "nothing to skip"})
                continue
            keep = [s for s in plan.get(day, []) if s not in sessions]
            plan[day] = keep
            echo.append({"date": day, "action": "skipped", "sessions": len(sessions)})
            continue

        if not sessions:
            load = entry.get("load")
            if load is None:
                raise ValueError(
                    f"Overlay entry for {day} matches no planned session, so it would "
                    "add one — but it has no 'load' to add."
                )
            plan.setdefault(day, []).append(
                {
                    "event_id": None,
                    "name": entry.get("name") or "Hypothetical session",
                    "load": int(load),
                    "load_source": "overlay",
                    "moving_time": entry.get("moving_time"),
                }
            )
            echo.append({"date": day, "action": "added", "load": int(load)})
            continue

        if len(sessions) > 1 and event_id is None:
            raise ValueError(
                f"{day} has {len(sessions)} planned sessions — pass 'event_id' to say "
                "which one to change, or use 'skip' to drop them all."
            )

        session = sessions[0]
        if "load" in entry and entry["load"] is not None:
            session["load"] = int(entry["load"])
            session["load_source"] = "overlay"
            echo.append({"date": day, "action": "modified", "load": session["load"]})
        elif entry.get("moving_time"):
            if not session.get("load") or not session.get("moving_time"):
                raise ValueError(
                    f"Cannot scale the session on {day} by duration: it has no existing "
                    "load and duration to scale from. Pass 'load' directly instead."
                )
            ratio = entry["moving_time"] / session["moving_time"]
            session["load"] = round(session["load"] * ratio)
            session["moving_time"] = entry["moving_time"]
            session["load_source"] = "overlay_scaled"
            echo.append(
                {
                    "date": day,
                    "action": "modified",
                    "load": session["load"],
                    "approximate": True,
                    "detail": "load scaled by duration; assumes the removed minutes "
                    "were of average intensity",
                }
            )
        else:
            raise ValueError(
                f"Overlay entry for {day} changes nothing — give 'load', "
                "'moving_time' or 'skip'."
            )

    return plan, echo


def project_fitness_series(
    days: list[date],
    plan: dict[str, list[dict]],
    seed_ctl: float,
    seed_atl: float,
    platform: dict[str, dict] | None = None,
    overlaid_dates: set[str] | None = None,
    ctl_days: int = CTL_DAYS,
    atl_days: int = ATL_DAYS,
) -> list[dict]:
    """Daily CTL/ATL/TSB across `days`, labelled by where each number came from.

    Prefers intervals.icu's own values wherever `platform` supplies them, so
    the series cannot drift away from the fitness chart the athlete is looking
    at. Days it has to compute are labelled 'extrapolated', and every day at or
    after the first overlay change is 'hypothetical' — a hypothetical does not
    only alter its own day, it carries forward through the whole series.
    """
    platform = platform or {}
    overlaid = overlaid_dates or set()
    first_overlay = min(overlaid) if overlaid else None

    ctl, atl = float(seed_ctl), float(seed_atl)
    series: list[dict] = []

    for day in days:
        key = day.isoformat()
        sessions = plan.get(key, [])
        load = sum(s.get("load") or 0 for s in sessions)

        hypothetical = first_overlay is not None and key >= first_overlay
        actual = platform.get(key) or {}
        use_platform = (
            not hypothetical
            and actual.get("ctl") is not None
            and actual.get("atl") is not None
        )

        if use_platform:
            ctl, atl = float(actual["ctl"]), float(actual["atl"])
            source = "platform"
        else:
            ctl = decay(ctl, load, ctl_days)
            atl = decay(atl, load, atl_days)
            source = "hypothetical" if hypothetical else "extrapolated"

        load_sources = sorted({s.get("load_source", "none") for s in sessions})
        row = {
            "date": key,
            "load": load,
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(ctl - atl, 1),
            "source": source,
        }
        if sessions:
            row["sessions"] = len(sessions)
            row["load_sources"] = load_sources
            # A load someone typed in is a softer number than one derived from
            # structured steps — the padel day should not read as firmly as the
            # ERG session next to it.
            if "target" in load_sources or "overlay_scaled" in load_sources:
                row["load_is_estimated"] = True
        series.append(row)

    return series


# --- planned versus actual ------------------------------------------------


def _iso_day(value: str | None) -> str | None:
    """Local date as an ISO string, or None when it cannot be parsed."""
    day = parse_local_date(value)
    return day.isoformat() if day else None


def zone_adherence(activity: dict, metric: str, zone: str) -> dict | None:
    """How much of a session's recorded time held a zone ceiling, and its band.

    Two numbers, because one conflates two failure modes. `under_ceiling_pct`
    counts time at or below the zone's upper bound — the discipline question,
    blind to riding too easy. `in_band_pct` counts time inside the zone itself,
    which on an outdoor ride also counts every descent and traffic light as a
    miss. Read together, 98%/61% is a disciplined ride with a lot of coasting;
    72%/70% is someone attacking the climbs.

    The ceiling comes from the activity's own zones, so a session ridden at a
    lower FTP is judged against the ceiling it was actually given rather than
    today's. The ceiling used is reported, because a moving threshold makes
    otherwise-identical percentages incomparable.

    Returns None when the session has no times for this metric — the signal to
    exclude and count it, not to score it zero.

    Scope: this is whole-session adherence, not adherence inside the prescribed
    blocks. Narrowing it to prescribed steps needs the planned workout's step
    structure, which the API exposes only as an untyped `workout_doc`. For a
    session prescribed entirely in one zone the two are the same; for a mixed
    session this number describes the whole ride and should be read that way.
    """
    secs_by_zone = zone_secs(activity, metric)
    if not secs_by_zone:
        return None

    number = zone_number(zone, 0)
    total = sum(secs_by_zone.values())
    if not total:
        return None

    under = sum(s for z, s in secs_by_zone.items() if zone_number(z, 0) <= number)
    in_band = secs_by_zone.get(f"Z{number}", 0)

    return {
        "zone": f"Z{number}",
        "ceiling": zone_ceiling(activity, metric, zone),
        "recorded_secs": total,
        "under_ceiling_secs": under,
        "in_band_secs": in_band,
        "under_ceiling_pct": round(100 * under / total, 1),
        "in_band_pct": round(100 * in_band / total, 1),
    }


def compare_session(activity: dict, event: dict | None) -> dict:
    """One session's prescribed load and duration against what was done."""
    row = {
        "activity_id": activity.get("id"),
        "date": _iso_day(activity.get("start_date_local")),
        "name": activity.get("name"),
        "type": activity.get("type"),
        "actual_load": activity.get("icu_training_load") or 0,
        "actual_moving_time": activity.get("moving_time") or 0,
    }
    if activity.get("compliance") is not None:
        # intervals.icu's own planned-versus-actual measure. Passed through
        # rather than reimplemented so it cannot disagree with the platform.
        row["compliance"] = activity["compliance"]

    if not event:
        row["planned"] = False
        return row

    load, load_source = event_load(event)
    row["planned"] = True
    row["event_id"] = event.get("id")
    row["planned_load"] = load
    row["planned_load_source"] = load_source
    row["planned_moving_time"] = event.get("moving_time")

    if load:
        row["load_delta"] = row["actual_load"] - load
        row["load_pct"] = round(100 * row["actual_load"] / load, 1)
    planned_time = event.get("moving_time")
    if planned_time:
        row["time_delta"] = row["actual_moving_time"] - planned_time
        row["time_pct"] = round(100 * row["actual_moving_time"] / planned_time, 1)
    return row


def compare_block(
    activities: list[dict],
    events: list[dict],
    metric: str | None = None,
    zone: str | None = None,
) -> dict:
    """Per-session and aggregate planned-versus-actual across a block.

    Sessions are joined to their planned event by `paired_event_id`. An
    activity with no pairing is reported as unplanned rather than dropped, and
    a planned event with no activity is reported as missed — a block's
    discipline is as much about what did not happen as what did.
    """
    events_by_id = {e["id"]: e for e in events if e.get("id") is not None}
    paired_event_ids: set = set()
    sessions: list[dict] = []

    for activity in activities:
        event_id = activity.get("paired_event_id")
        event = events_by_id.get(event_id) if event_id is not None else None
        if event:
            paired_event_ids.add(event_id)
        row = compare_session(activity, event)

        if metric and zone:
            adherence = zone_adherence(activity, metric, zone)
            if adherence:
                row["adherence"] = adherence
        sessions.append(row)

    missed = [
        {
            "event_id": e.get("id"),
            "date": _iso_day(e.get("start_date_local")),
            "name": e.get("name"),
            "planned_load": event_load(e)[0],
        }
        for e in events
        if e.get("id") not in paired_event_ids and e.get("category") == "WORKOUT"
    ]

    planned_rows = [s for s in sessions if s.get("planned")]
    aggregate = {
        "sessions": len(sessions),
        "planned_sessions": len(planned_rows),
        "unplanned_sessions": len(sessions) - len(planned_rows),
        "missed_sessions": len(missed),
        "actual_load": sum(s["actual_load"] for s in sessions),
        "planned_load": sum(s.get("planned_load") or 0 for s in planned_rows),
        "actual_moving_time": sum(s["actual_moving_time"] for s in sessions),
        "planned_moving_time": sum(s.get("planned_moving_time") or 0 for s in planned_rows),
    }
    if aggregate["planned_load"]:
        aggregate["load_pct"] = round(
            100 * aggregate["actual_load"] / aggregate["planned_load"], 1
        )

    result = {"aggregate": aggregate, "sessions": sessions, "missed": missed}

    if metric and zone:
        scored = [s["adherence"] for s in sessions if "adherence" in s]
        recorded = sum(a["recorded_secs"] for a in scored)
        ceilings = sorted({a["ceiling"] for a in scored if a["ceiling"] is not None})
        pooled = {
            "zone": f"Z{zone_number(zone, 0)}",
            "metric": metric,
            "scored_sessions": len(scored),
            # Excluded, not zeroed: a padel match has no power to score.
            "sessions_without_metric": len(sessions) - len(scored),
            "ceilings_used": ceilings,
        }
        if recorded:
            pooled["recorded_secs"] = recorded
            pooled["under_ceiling_pct"] = round(
                100 * sum(a["under_ceiling_secs"] for a in scored) / recorded, 1
            )
            pooled["in_band_pct"] = round(
                100 * sum(a["in_band_secs"] for a in scored) / recorded, 1
            )
        if len(ceilings) > 1:
            pooled["note"] = (
                "The ceiling moved during this block, so per-session percentages "
                "are measured against different thresholds. See each session's "
                "'adherence.ceiling'."
            )
        result["adherence"] = pooled

    return result
