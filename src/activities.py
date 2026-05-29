import enum
from datetime import date, timedelta

import httpx
from fastmcp import Context, FastMCP

from shaping import project_and_prune, project_and_prune_list
from curves import format_curve

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
        "power_load_type",
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

    try:
        client = ctx.lifespan_context["client"]
    except KeyError as e:
        import sys
        print(f"ERROR: lifespan_context missing 'client'. Keys available: {list(ctx.lifespan_context.keys())}", file=sys.stderr)
        raise

    data = await client.get(
        f"/athlete/{athlete_id}/activities",
        params=httpx.QueryParams(
            oldest=from_date.isoformat(), newest=to_date.isoformat()
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
        g.value if isinstance(g, ActivityFields) else g
        for g in include
    ]

    try:
        client = ctx.lifespan_context["client"]
    except KeyError as e:
        import sys
        print(f"ERROR: lifespan_context missing 'client'. Keys available: {list(ctx.lifespan_context.keys())}", file=sys.stderr)
        raise

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
    resp = await ctx.lifespan_context["client"].get(
        f"/activity/{activity_id}/intervals"
    )
    return resp.json()


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_messages(ctx: Context, activity_id: str) -> list:
    """Get all messages/comments posted on an activity (athlete and coach feedback).

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    try:
        resp = await ctx.lifespan_context["client"].get(
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
    resp = await ctx.lifespan_context["client"].put(
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
    resp = await ctx.lifespan_context["client"].post(
        f"/activity/{activity_id}/messages", json={"content": content}
    )
    return {"message": f"Message posted to activity {activity_id}.", "status": resp.status_code}


class CurveMetric(enum.Enum):
    """Curve metric types."""

    POWER = "power"
    HR = "hr"
    PACE = "pace"


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_power_curve(
    ctx: Context,
    athlete_id: str = "0",
    metric: str = "POWER",
    days: int = 90,
    durations: list[str] | None = None,
) -> dict:
    """Get an athlete's best-effort power/HR/pace curve over a date window.

    Server-computed mean-max curve (best sustained effort for each duration).
    Sampled to canonical durations (5s…60m). Never raw streams.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        metric: Curve metric: 'POWER', 'HR', or 'PACE' (default 'POWER').
        days: Date window in days (default 90).
        durations: List of duration labels to include (e.g. ['5m', '20m', '60m']).
                  Omit for all 9 canonical durations.
    """
    client = ctx.lifespan_context["client"]
    athlete = await client.get(f"/athlete/{athlete_id}")
    weight = athlete.json().get("weight", 70.0)

    # Map metric to API parameters
    metric_lower = metric.lower()
    if metric_lower == "power":
        api_path = f"/athlete/{athlete_id}/power-curves.json"
        api_type = "power"
    elif metric_lower == "hr":
        api_path = f"/athlete/{athlete_id}/hr-curves.json"
        api_type = "hr"
    elif metric_lower == "pace":
        api_path = f"/athlete/{athlete_id}/pace-curves.json"
        api_type = "pace"
    else:
        return {"error": f"Unknown metric: {metric}"}

    # Query the curve endpoint
    resp = await client.get(api_path)
    server_curve = resp.json()

    # Format and sample
    formatted = format_curve(
        server_curve, metric=metric.upper(), requested_durations=durations, weight=weight
    )

    return {
        "athlete_id": athlete_id,
        "window": f"{days}d",
        "metric": metric,
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
    Never raw streams.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        metric: Curve metric: 'POWER', 'HR', or 'PACE' (default 'POWER').
        durations: List of duration labels to include. Omit for all 9 canonical durations.
    """
    client = ctx.lifespan_context["client"]

    # Get activity for weight
    activity = await client.get(f"/activity/{activity_id}")
    activity_data = activity.json()
    weight = activity_data.get("icu_weight", 70.0)

    # Map metric to API path
    metric_lower = metric.lower()
    if metric_lower == "power":
        api_path = f"/activity/{activity_id}/power-curve.json"
    elif metric_lower == "hr":
        api_path = f"/activity/{activity_id}/hr-curve.json"
    elif metric_lower == "pace":
        api_path = f"/activity/{activity_id}/pace-curve.json"
    else:
        return {"error": f"Unknown metric: {metric}"}

    # Query the curve endpoint
    resp = await client.get(api_path)
    server_curve = resp.json()

    # Format and sample
    formatted = format_curve(
        server_curve, metric=metric.upper(), requested_durations=durations, weight=weight
    )

    return {
        "activity_id": activity_id,
        "metric": metric,
        "curve": formatted,
        "weight": weight,
    }
