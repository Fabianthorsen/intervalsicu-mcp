import enum
from datetime import date, timedelta

import httpx
from fastmcp import Context, FastMCP

from client import get_client
from shaping import CORE_FIELDS, project_and_prune, project_and_prune_list, prune
from curves import format_curve
from windows import (
    WindowError,
    extract_time_stream,
    format_window_metrics,
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
async def get_activity_intervals(ctx: Context, activity_id: str) -> dict:
    """Get the analysed intervals for a specific activity, including power, HR,
    pace, TSS, and other metrics per interval.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    client = await get_client(ctx)

    resp = await client.get(
        f"/activity/{activity_id}/intervals"
    )
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
