import enum
from datetime import date, timedelta

import httpx
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from blocks import (
    METRICS,
    SUMMARY_FIELDS,
    ZONE_BOUND_FIELDS,
    compare_block as compare_block_rows,
    summarise,
)
from client import get_client
from shaping import CORE_FIELDS, project_and_prune, project_and_prune_list, prune
from curves import format_curve
from intervals import (
    IntervalError,
    IntervalFields,
    IntervalType,
    apply_edits,
    extract_intervals,
    find_interval,
    find_section,
    plan_cuts,
    shape_intervals,
)
from windows import (
    WindowError,
    extract_time_stream,
    format_window_metrics,
    resolve_section,
    resolve_window,
)

activities = FastMCP("activities")


class CoachTick(enum.IntEnum):
    WTF = enum.auto()
    POOR = enum.auto()
    SEEN = enum.auto()
    GOOD = enum.auto()
    AMAZING = enum.auto()


class ActivityFields(enum.Enum):
    """Semantic field groups for activity data."""

    HEADLINE = "headline"
    POWER = "power"
    HR = "hr"
    PACE = "pace"
    CADENCE = "cadence"
    ZONES = "zones"
    ELEVATION = "elevation"
    WEATHER = "weather"
    FUELING = "fueling"
    COMPLIANCE = "compliance"
    COACHING = "coaching"
    DEVICE = "device"
    ALL = "all"


ACTIVITY_TAXONOMY = {
    "HEADLINE": [
        "sub_type",
        "moving_time",
        "elapsed_time",
        "distance",
        "icu_distance",
        "icu_training_load",
        "icu_intensity",
        "calories",
        "trainer",
        "commute",
    ],
    "POWER": [
        "icu_average_watts",
        "icu_weighted_avg_watts",
        "p_max",
        "icu_ftp",
        "icu_pm_ftp",
        "icu_pm_cp",
        "icu_pm_w_prime",
        "icu_w_prime",
        "icu_variability_index",
        "polarization_index",
        "icu_efficiency_factor",
        "power_load",
        "icu_joules",
        "icu_joules_above_ftp",
        "avg_lr_balance",
        "coasting_time",
        "icu_max_wbal_depletion",
        "device_watts",
        "icu_ignore_power",
        "icu_rolling_ftp",
        "icu_rolling_cp",
        "icu_rolling_p_max",
        "icu_rolling_w_prime",
        "icu_power_spike_threshold",
        "p30s_exponent",
        "icu_sweet_spot_min",
        "icu_sweet_spot_max",
        "ss_cp",
        "ss_p_max",
        "ss_w_prime",
        "strain_score",
    ],
    "HR": [
        "average_heartrate",
        "max_heartrate",
        "athlete_max_hr",
        "lthr",
        "icu_resting_hr",
        "hr_load",
        "hr_load_type",
        "decoupling",
        "icu_hrr",
        "icu_power_hr",
        "icu_power_hr_z2",
        "icu_power_hr_z2_mins",
        "has_heartrate",
        "icu_ignore_hr",
        "trimp",
    ],
    "PACE": [
        "pace",
        "gap",
        "gap_model",
        "average_speed",
        "max_speed",
        "threshold_pace",
        "pace_load",
        "pace_load_type",
        "ignore_pace",
        "ignore_velocity",
    ],
    "CADENCE": [
        "average_cadence",
        "average_stride",
        "icu_cadence_z2",
        "crank_length",
    ],
    "ZONES": [
        "icu_zone_times",
        "icu_hr_zone_times",
        "pace_zone_times",
        "gap_zone_times",
        "icu_power_zones",
        "icu_hr_zones",
        "pace_zones",
        "custom_zones",
        "use_gap_zone_times",
        "tiz_order",
    ],
    "ELEVATION": [
        "total_elevation_gain",
        "total_elevation_loss",
        "average_altitude",
        "min_altitude",
        "max_altitude",
        "use_elevation_correction",
    ],
    "WEATHER": [
        "average_temp",
        "min_temp",
        "max_temp",
        "average_weather_temp",
        "min_weather_temp",
        "max_weather_temp",
        "average_feels_like",
        "min_feels_like",
        "max_feels_like",
        "average_wind_speed",
        "average_wind_gust",
        "prevailing_wind_deg",
        "average_clouds",
        "max_rain",
        "max_snow",
        "headwind_percent",
        "tailwind_percent",
        "has_weather",
    ],
    "FUELING": [
        "calories",
        "carbs_ingested",
        "carbs_used",
        "kg_lifted",
    ],
    "COMPLIANCE": [
        "compliance",
        "interval_summary",
        "icu_intervals_edited",
        "lock_intervals",
        "icu_lap_count",
        "icu_warmup_time",
        "icu_cooldown_time",
        "icu_recording_time",
        "recording_stops",
    ],
    "COACHING": [
        "coach_tick",
        "feel",
        "perceived_exertion",
        "session_rpe",
        "icu_rpe",
        "description",
        "tags",
        "icu_achievements",
        "analyzed",
    ],
    "DEVICE": [
        "device_name",
        "power_meter",
        "power_meter_battery",
        "power_meter_serial",
        "file_type",
        "source",
        "strava_id",
        "gear",
        "oauth_client_name",
        "route_id",
        "external_id",
    ],
}


# Field list sent to the API for list calls: the HEADLINE group plus the core
# fields that ship unconditionally. Every name is verified against the Activity
# schema by tests/test_taxonomy_fields.py, so this cannot request a field that
# does not exist.
_HEADLINE_FIELDS_PARAM = ",".join(
    sorted(CORE_FIELDS | set(ACTIVITY_TAXONOMY["HEADLINE"]))
)


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def list_activities_between_dates(
    ctx: Context,
    athlete_id: str = "0",
    from_date: date | None = None,
    to_date: date | None = None,
) -> list:
    """List recent activities in descending date order (core + HEADLINE fields).

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        from_date: Earliest date to include (ISO-8601). Defaults to 14 days ago.
        to_date: Latest date to include (ISO-8601). Defaults to today.
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=14)
    if to_date is None:
        to_date = date.today()

    client = await get_client(ctx)

    data = await client.get(
        f"/athlete/{athlete_id}/activities",
        params=httpx.QueryParams(
            oldest=from_date.isoformat(),
            newest=to_date.isoformat(),
            # Project server-side as well as locally. An Activity carries ~200
            # fields and shaping discards nearly all of them, so asking for the
            # dozen we keep avoids pulling the rest over the wire. Output is
            # unchanged — project_and_prune_list still has the final say.
            fields=_HEADLINE_FIELDS_PARAM,
        ),
    )
    records = data.json()

    return project_and_prune_list(records, ["HEADLINE"], ACTIVITY_TAXONOMY)


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity(
    ctx: Context, activity_id: str, include: list[str] | None = None
) -> dict:
    """Get activity details with optional field group selection.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        include: List of field groups to include (e.g. ['POWER', 'HR']). Omit for core + HEADLINE.
                 Options: HEADLINE (default), POWER, HR, PACE, CADENCE, ZONES, ELEVATION,
                 WEATHER, FUELING, COMPLIANCE, COACHING, DEVICE, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        (g.value if isinstance(g, ActivityFields) else g).upper()
        for g in include
    ]

    client = await get_client(ctx)

    resp = await client.get(f"/activity/{activity_id}")
    obj = resp.json()

    return project_and_prune(obj, include_groups, ACTIVITY_TAXONOMY)


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_intervals(
    ctx: Context,
    activity_id: str,
    include: list[IntervalFields | str] | None = None,
) -> dict:
    """Get the analysed intervals for an activity — power, HR, pace, TSS and
    load per interval, plus intervals.icu's own grouping of them into reps.

    Returns each interval's `id` and `label`, which is what the interval
    editing tools address. `start_time` and `end_time` are elapsed seconds from
    the start of the activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        include: Field groups — HEADLINE (default), TIMING, POWER, HR, PACE,
                 CADENCE, ELEVATION, or ALL for the raw payload, which is large.
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        (g.value if isinstance(g, IntervalFields) else g).upper() for g in include
    ]

    client = await get_client(ctx)

    resp = await client.get(f"/activity/{activity_id}/intervals")
    return shape_intervals(resp.json(), include_groups)


@activities.tool(tags={"Activities"})
async def update_activity_interval(
    ctx: Context,
    activity_id: str,
    interval_id: int,
    label: str | None = None,
    interval_type: IntervalType | str | None = None,
) -> dict:
    """Name an interval, or change whether it counts as work or recovery.

    Use this to turn auto-detected intervals into something readable — "5min
    threshold rep 3", "the surge on the climb", "tempo block". Labels show up
    in the athlete's own intervals.icu view, so they are a way to leave
    structure behind, not just to annotate one conversation.

    Get interval ids from get_activity_intervals.

    Note: editing an activity's intervals makes intervals.icu treat them as
    manually curated. It stops re-detecting intervals for that activity, and
    the change is visible to the athlete. Say so before editing an athlete's
    session on their behalf.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        interval_id: The interval's id, from get_activity_intervals.
        label: New name for the interval. Pass '' to clear an existing label.
        interval_type: 'WORK' or 'RECOVERY'. Affects how intervals.icu analyses
                       and groups the interval.
    """
    if isinstance(interval_type, IntervalType):
        interval_type = interval_type.value

    client = await get_client(ctx)

    # Read-modify-write: the PUT replaces the interval, so it has to carry
    # every field the server already holds, not just the edited ones.
    current = await client.get(f"/activity/{activity_id}/intervals")
    intervals = extract_intervals(current.json())

    try:
        interval = find_interval(intervals, interval_id)
        edited = apply_edits(interval, label=label, interval_type=interval_type)
    except IntervalError as exc:
        raise ToolError(str(exc)) from exc

    await client.put(
        f"/activity/{activity_id}/intervals/{interval_id}", json=edited
    )

    resp = await client.get(f"/activity/{activity_id}/intervals")
    return shape_intervals(resp.json(), ["HEADLINE"])


@activities.tool(tags={"Activities"})
async def create_activity_interval(
    ctx: Context,
    activity_id: str,
    start_seconds: int,
    end_seconds: int,
    label: str,
    interval_type: IntervalType | str = "WORK",
) -> dict:
    """Carve a stretch of an activity out as its own named interval.

    This is how an unstructured ride gets sections. A steady Z2 ride arrives as
    one long interval; carving out 20-40min as "tempo block" leaves three
    intervals — before, the block, after — each with its own power, HR and
    decoupling. Repeat for as many sections as the ride deserves.

    Intervals tile the recording end to end, so a section is cut out of its
    neighbours rather than layered over them: the surrounding riding stays,
    split around the new interval. Nothing about the ride's data changes, only
    where the boundaries fall.

    For metrics over a window without editing anything, use
    get_activity_window_metrics instead.

    Note: this edits the athlete's activity, and the labels are visible to
    them. intervals.icu stops auto-detecting intervals for an activity once its
    intervals have been edited. Say so before restructuring someone's session.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        start_seconds: Section start, in elapsed seconds from the activity
                       start, including any pauses.
        end_seconds: Section end, in elapsed seconds, exclusive — a section of
                     1200-2400 lasts exactly 1200s, and a following section
                     starting at 2400 continues from it with no gap. Must be
                     after start_seconds.
        label: Name for the section, e.g. 'tempo block' or 'threshold rep 2'.
        interval_type: 'WORK' (default) or 'RECOVERY'. Affects how
                       intervals.icu analyses and groups the interval.
    """
    if isinstance(interval_type, IntervalType):
        interval_type = interval_type.value

    client = await get_client(ctx)

    # split-interval addresses the recording by sample index, not seconds. The
    # time stream is fetched only to convert; per ADR-0003 none of it is
    # returned. Both ends resolve against the same stream before any cut,
    # because an index means the same thing before and after a split.
    stream_resp = await client.get(
        f"/activity/{activity_id}/streams.json", params={"types": "time"}
    )
    time_stream = extract_time_stream(stream_resp.json())

    try:
        start_index, end_index = resolve_section(
            time_stream, start_seconds, end_seconds
        )
    except WindowError as exc:
        raise ToolError(str(exc)) from exc

    current = await client.get(f"/activity/{activity_id}/intervals")

    try:
        cuts = plan_cuts(extract_intervals(current.json()), start_index, end_index)
    except IntervalError as exc:
        raise ToolError(str(exc)) from exc

    for cut in cuts:
        await client.put(
            f"/activity/{activity_id}/split-interval", params={"splitAt": cut}
        )

    cut_resp = await client.get(f"/activity/{activity_id}/intervals")

    try:
        section = find_section(
            extract_intervals(cut_resp.json()), start_index, end_index
        )
        edited = apply_edits(section, label=label, interval_type=interval_type)
    except IntervalError as exc:
        raise ToolError(str(exc)) from exc

    await client.put(
        f"/activity/{activity_id}/intervals/{section['id']}", json=edited
    )

    resp = await client.get(f"/activity/{activity_id}/intervals")
    return shape_intervals(resp.json(), ["HEADLINE"])


@activities.tool(tags={"Activities"}, annotations={"destructiveHint": True})
async def delete_activity_intervals(
    ctx: Context,
    activity_id: str,
    interval_ids: list[int],
) -> dict:
    """Delete intervals from an activity.

    Removes the named intervals so the surrounding riding is no longer split
    out — the usual reason being an interval that was cut in the wrong place,
    or a detected interval that was never really an effort. The ride's own data
    is untouched; only the interval boundaries drawn over it go away.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        interval_ids: Ids of the intervals to delete, from
                      get_activity_intervals.
    """
    client = await get_client(ctx)

    current = await client.get(f"/activity/{activity_id}/intervals")
    intervals = extract_intervals(current.json())

    try:
        doomed = [find_interval(intervals, i) for i in interval_ids]
    except IntervalError as exc:
        raise ToolError(str(exc)) from exc

    await client.put(
        f"/activity/{activity_id}/delete-intervals", json=doomed
    )

    resp = await client.get(f"/activity/{activity_id}/intervals")
    return shape_intervals(resp.json(), ["HEADLINE"])


@activities.tool(tags={"Activities"})
async def update_activity(
    ctx: Context,
    activity_id: str,
    name: str | None = None,
    description: str | None = None,
    type: str | None = None,
    rpe: int | None = None,
    feel: int | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
) -> dict:
    """Correct an activity's name, description, sport type, RPE, feel or tags.

    Only the fields you provide are changed. `type` is the consequential one:
    it decides which sport settings group the activity falls under, and
    therefore which thresholds and zones its load is computed against. A padel
    match that arrived from a watch as a generic 'Workout' gets no sensible
    load until its type is right.

    Tags are added and removed rather than replaced. Writing the whole list
    would silently drop tags that arrived from Strava, the athlete or an
    earlier pass — a loss that returns 200 and looks like success. Use
    list_activity_tags first and reuse an existing tag: 'padel' and 'Padel'
    are two different tags to search_activities, which matches them exactly.

    Changes here are visible to the athlete.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        name: New activity name.
        description: New activity description.
        type: Sport type (e.g. 'Ride', 'Run', 'Padel'). Must match a type
              intervals.icu recognises — get_sport_settings lists the types
              each settings group covers.
        rpe: Rate of perceived exertion, 1-10.
        feel: How the session felt, 1 (strong) to 5 (terrible).
        add_tags: Tags to add, keeping the ones already there. Find an activity
                  by tag later with search_activities using '#tag'.
        remove_tags: Tags to remove. Matched case-sensitively, as stored.
    """
    optional = {
        "name": name,
        "description": description,
        "type": type,
        "icu_rpe": rpe,
        "feel": feel,
    }
    body = {k: v for k, v in optional.items() if v is not None}

    client = await get_client(ctx)

    if add_tags or remove_tags:
        # Read-merge-write: the API replaces the whole array, so the current
        # tags have to be fetched to preserve them.
        current = await client.get(f"/activity/{activity_id}", params={"fields": "id,tags"})
        existing = list(current.json().get("tags") or [])
        removing = set(remove_tags or [])
        merged = [t for t in existing if t not in removing]
        for tag in add_tags or []:
            if tag not in merged:
                merged.append(tag)
        body["tags"] = merged

    if not body:
        raise ValueError(
            "Nothing to update — provide at least one of name, description, type, "
            "rpe, feel, add_tags or remove_tags."
        )

    resp = await client.put(f"/activity/{activity_id}", json=body)
    return {
        "message": f"Activity {activity_id} updated: {', '.join(sorted(body))}.",
        "status": resp.status_code,
        **({"tags": body["tags"]} if "tags" in body else {}),
    }


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def list_activity_tags(ctx: Context, athlete_id: str = "0") -> list:
    """List every tag already used on this athlete's activities.

    Check here before tagging. search_activities matches tags exactly, so a
    near-duplicate ('padel' next to 'Padel') quietly splits a set of sessions
    in two and every later query sees half of them.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    client = await get_client(ctx)

    resp = await client.get(f"/athlete/{athlete_id}/activity-tags")
    return resp.json()


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_messages(ctx: Context, activity_id: str) -> list:
    """Get all messages/comments posted on an activity (athlete and coach feedback).

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    client = await get_client(ctx)

    try:
        resp = await client.get(
            f"/activity/{activity_id}/messages"
        )
        return resp.json() or []
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return []
        raise


@activities.tool(tags={"Coaching"})
async def set_coach_evaluation(
    ctx: Context, activity_id: str, evaluation: CoachTick
) -> dict:
    """Set the coach's evaluation tick on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        evaluation: 1 = WTF, 2 = POOR, 3 = SEEN, 4 = GOOD, 5 = AMAZING.
    """
    client = await get_client(ctx)

    resp = await client.put(
        f"/activity/{activity_id}", json={"coach_tick": evaluation}
    )
    return {
        "message": f"Coach evaluation for activity {activity_id} set to {evaluation.name}.",
        "status": resp.status_code,
    }


@activities.tool(tags={"Coaching"})
async def post_activity_message(ctx: Context, activity_id: str, content: str) -> dict:
    """Post a coaching message or feedback comment on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        content: The message text to post.
    """
    client = await get_client(ctx)

    resp = await client.post(
        f"/activity/{activity_id}/messages", json={"content": content}
    )
    return {"message": f"Message posted to activity {activity_id}.", "status": resp.status_code}


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_power_curve(
    ctx: Context,
    athlete_id: str = "0",
    sport_type: str = "Ride",
    days: int = 90,
    durations: list[str] | None = None,
) -> dict:
    """Get an athlete's best-effort power curve over a date window.

    Server-computed mean-max curve (best sustained effort for each duration).
    Sampled to canonical durations (5s…60m). Never raw streams.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        sport_type: Activity type to filter by (default 'Ride'). Options: Ride, Run, Swim, etc.
        days: Date window in days (default 90). Common: 7, 30, 90, 365.
        durations: List of duration labels to include (e.g. ['5m', '20m', '60m']).
                  Omit for all canonical durations.
    """
    client = await get_client(ctx)

    # The power-curves endpoint requires the activity type and a curve window.
    try:
        resp = await client.get(
            f"/athlete/{athlete_id}/power-curves.json",
            params={"type": sport_type, "curves": f"{days}d"},
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {
                "athlete_id": athlete_id,
                "sport_type": sport_type,
                "window": f"{days}d",
                "note": f"No power curve available for activity type '{sport_type}'",
                "curve": None,
            }
        raise

    server_curve = resp.json()
    # Weight rides along in the curve payload; use it for W/kg rather than a guess.
    entries = server_curve.get("list") or []
    weight = entries[0].get("weight") if entries else None

    formatted = format_curve(
        server_curve, metric="POWER", requested_durations=durations, weight=weight
    )

    return {
        "athlete_id": athlete_id,
        "sport_type": sport_type,
        "window": f"{days}d",
        "curve": formatted,
        "weight": weight,
    }


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_curve(
    ctx: Context,
    activity_id: str,
    metric: str = "POWER",
    durations: list[str] | None = None,
) -> dict:
    """Get best efforts (curve) within a single activity.

    Server-computed curve for the activity. Sampled to canonical durations.
    Never raw streams. Not all activities have computed curves.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        metric: Curve metric: 'POWER', 'HR', or 'PACE' (default 'POWER').
        durations: List of duration labels to include. Omit for all canonical durations.
    """
    metric_lower = metric.lower()
    if metric_lower not in ("power", "hr", "pace"):
        return {"error": f"Unknown metric: {metric}"}

    client = await get_client(ctx)

    # Not every activity has a computed curve, and pace curves don't exist for
    # non-distance sports — both surface as a 404 we report rather than raise.
    try:
        resp = await client.get(f"/activity/{activity_id}/{metric_lower}-curve.json")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {
                "activity_id": activity_id,
                "metric": metric,
                "note": f"No {metric_lower} curve available for this activity",
                "curve": None,
            }
        raise

    server_curve = resp.json()
    # Weight is included in the activity curve payload; use it for W/kg.
    weight = server_curve.get("weight")

    formatted = format_curve(
        server_curve, metric=metric.upper(), requested_durations=durations, weight=weight
    )

    return {
        "activity_id": activity_id,
        "metric": metric,
        "curve": formatted,
        "weight": weight,
    }


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_window_metrics(
    ctx: Context,
    activity_id: str,
    start_seconds: int,
    end_seconds: int,
) -> dict:
    """Get power, HR and load metrics for any time window within an activity.

    Answers questions the recorded intervals do not, such as "how did the last
    hour of that ride compare to the first" or "what did she average between
    40 and 60 minutes". The window is arbitrary — it need not line up with laps
    or intervals.

    Returns normalized and average power, variability index, intensity factor,
    TSS, decoupling, average HR and cadence for the window. All of it is
    computed by intervals.icu, not derived from raw samples.

    Times are elapsed seconds from the start of the activity, including any
    pauses. Use get_activity for the activity's total duration.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        start_seconds: Window start, in elapsed seconds from the activity start.
        end_seconds: Window end, in elapsed seconds. Must be after start_seconds.
    """
    client = await get_client(ctx)

    # The time stream maps sample index to elapsed second. It is needed because
    # interval-stats addresses windows by index, and index only equals second
    # for an unpaused 1Hz recording. Fetched here and discarded — per ADR-0003
    # no part of it is returned to the caller.
    stream_resp = await client.get(
        f"/activity/{activity_id}/streams.json", params={"types": "time"}
    )
    time_stream = extract_time_stream(stream_resp.json())

    try:
        start_index, end_index = resolve_window(time_stream, start_seconds, end_seconds)
    except WindowError as exc:
        return {
            "activity_id": activity_id,
            "requested_window": {"start_seconds": start_seconds, "end_seconds": end_seconds},
            "error": str(exc),
            "metrics": None,
        }

    stats_resp = await client.get(
        f"/activity/{activity_id}/interval-stats",
        params={"start_index": start_index, "end_index": end_index},
    )
    metrics = format_window_metrics(stats_resp.json())

    return {
        "activity_id": activity_id,
        "window": {
            "start_seconds": time_stream[start_index],
            "end_seconds": time_stream[end_index],
        },
        "metrics": metrics,
    }


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def search_activities(
    ctx: Context,
    query: str,
    athlete_id: str = "0",
    limit: int = 20,
) -> list:
    """Find activities by name or tag, across the athlete's whole history.

    Use this when the date is unknown — "find her Alpe du Zwift attempts" or
    "when did he last do a ramp test". For a known date range,
    list_activities_between_dates is cheaper.

    Args:
        query: Name to search for, case-insensitive and matched as a substring.
               Prefix with '#' to match a tag exactly, e.g. '#race'.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        limit: Maximum number of activities to return (default 20).
    """
    client = await get_client(ctx)

    resp = await client.get(
        f"/athlete/{athlete_id}/activities/search",
        params=httpx.QueryParams(q=query, limit=limit),
    )
    results = resp.json()

    # The search endpoint returns a purpose-built summary (name, date, type,
    # distance, moving_time, tags, race, description) rather than a full
    # Activity, so there is nothing to project — only empties to drop.
    return [prune(item) for item in results]


@activities.tool(tags={"Analysis"}, annotations={"readOnlyHint": True})
async def get_load_summary(
    ctx: Context,
    from_date: date,
    to_date: date,
    athlete_id: str = "0",
    group_by: str = "week",
    metric: str | None = None,
) -> dict:
    """Totals for a block of training — load, duration and sport split per week or month.

    Answers "how much, of what, and how hard" across a range. For one session
    use get_activity; to compare a block against what was prescribed use
    compare_block.

    The sport split is the point when training is mixed: during a camp,
    cycling load can collapse while total load doubles, and a single aggregate
    number hides that completely.

    Pass `metric` to add zone-time distribution and the Z1-2 / Z3 / Z4+
    intensity split, pooled from seconds so a long ride counts for more than a
    short one. Sessions without that metric — padel has no power — are excluded
    from the split and reported as `sessions_without_metric` rather than
    counted as zero. This split is a time distribution, not intervals.icu's
    per-activity `polarization_index`, which is a different quantity.

    Weeks are ISO weeks and start on Monday.

    Args:
        from_date: Earliest date to include (ISO-8601).
        to_date: Latest date to include (ISO-8601).
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        group_by: 'week' (default) or 'month'.
        metric: Optional — 'power', 'hr' or 'pace'. Adds the zone distribution
                and intensity split for sessions that recorded it.
    """
    if group_by not in ("week", "month"):
        raise ValueError(f"group_by must be 'week' or 'month', got '{group_by}'.")
    if metric is not None and metric not in METRICS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}, got '{metric}'.")

    client = await get_client(ctx)

    data = await client.get(
        f"/athlete/{athlete_id}/activities",
        params=httpx.QueryParams(
            oldest=from_date.isoformat(),
            newest=to_date.isoformat(),
            # One scoped call for the whole block. An Activity carries ~200
            # fields; the reducers read fifteen.
            fields=",".join(SUMMARY_FIELDS),
        ),
    )
    records = data.json()

    summary = summarise(records, group_by=group_by, metric=metric)
    summary["from_date"] = from_date.isoformat()
    summary["to_date"] = to_date.isoformat()
    return summary


@activities.tool(tags={"Analysis"}, annotations={"readOnlyHint": True})
async def compare_block(
    ctx: Context,
    from_date: date,
    to_date: date,
    athlete_id: str = "0",
    metric: str | None = None,
    zone: str | None = None,
) -> dict:
    """Compare a block of training against what was prescribed.

    Joins each completed activity to its planned event and reports prescribed
    load and duration against actual, per session and pooled. Activities with
    no plan are reported as unplanned; planned workouts with no activity are
    reported as missed, because a block's discipline is as much about what did
    not happen as what did. intervals.icu's own `compliance` figure is passed
    through untouched rather than recomputed.

    Pass `metric` and `zone` together to add zone adherence — for a Z2 ceiling
    question, metric='power', zone='Z2'. Two percentages come back per session
    and pooled: `under_ceiling_pct` (time at or below the zone's upper bound —
    the discipline number) and `in_band_pct` (time inside the zone, which also
    counts descents and stops as misses). Read together they separate "rode
    too hard" from "rode too easy".

    Each session is judged against its own zones, so a ride from before an FTP
    change is measured against the ceiling it was actually given. When the
    ceiling moved during the block, the pooled result says so.

    Adherence is whole-session, not narrowed to the prescribed steps: the API
    exposes a planned workout's structure only as an untyped document. For a
    session prescribed entirely in one zone the two are identical; for a mixed
    session the number describes the whole ride.

    Sessions without the requested metric — padel has no power — are excluded
    and counted in `sessions_without_metric`, never scored as zero.

    Args:
        from_date: Earliest date to include (ISO-8601).
        to_date: Latest date to include (ISO-8601).
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        metric: 'power', 'hr' or 'pace'. Required for adherence, with `zone`.
        zone: Zone to score adherence against, e.g. 'Z2'. Resolved to watts or
              bpm per activity from that activity's own zones.
    """
    if metric is not None and metric not in METRICS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}, got '{metric}'.")
    if bool(metric) != bool(zone):
        raise ValueError("metric and zone must be given together, or not at all.")

    client = await get_client(ctx)

    activity_fields = list(SUMMARY_FIELDS)
    if metric:
        activity_fields.append(ZONE_BOUND_FIELDS[metric])

    activities_resp = await client.get(
        f"/athlete/{athlete_id}/activities",
        params=httpx.QueryParams(
            oldest=from_date.isoformat(),
            newest=to_date.isoformat(),
            fields=",".join(activity_fields),
        ),
    )
    events_resp = await client.get(
        f"/athlete/{athlete_id}/events",
        params=httpx.QueryParams(
            oldest=from_date.isoformat(),
            newest=to_date.isoformat(),
            category="WORKOUT",
        ),
    )

    result = compare_block_rows(
        activities_resp.json(), events_resp.json(), metric=metric, zone=zone
    )
    result["from_date"] = from_date.isoformat()
    result["to_date"] = to_date.isoformat()
    return result
