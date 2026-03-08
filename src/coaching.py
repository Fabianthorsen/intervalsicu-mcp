import enum
from datetime import date, timedelta

import httpx
from fastmcp import Context, FastMCP

coaching = FastMCP("coaching")


class CoachTick(enum.IntEnum):
    WTF = enum.auto()
    POOR = enum.auto()
    SEEN = enum.auto()
    GOOD = enum.auto()
    AMAZING = enum.auto()


@coaching.tool(tags={"Coaching"}, annotations={"readOnlyHint": True})
async def list_coached_athletes(ctx: Context) -> list:
    """List all athletes the current user is coaching, with a recent summary of
    their training load, fitness, and activity data."""
    resp = await ctx.lifespan_context["client"].get("/athlete/0/athlete-summary")
    return resp.json()


@coaching.tool(tags={"Coaching"}, annotations={"readOnlyHint": True})
async def list_athlete_events(
    ctx: Context,
    athlete_id: str,
    days_ahead: int = 7,
    days_back: int = 0,
    category: str | None = None,
) -> list:
    """List planned events (workouts, notes, races) on a coached athlete's calendar.

    Args:
        athlete_id: The athlete's ID (e.g. 'i12345'). Get IDs from list_coached_athletes.
        days_ahead: How many days into the future to return (default 7).
        days_back: How many days into the past to include (default 0).
        category: Comma-separated event categories to filter for, e.g. 'WORKOUT,NOTE'.
    """
    oldest = (date.today() - timedelta(days=days_back)).isoformat()
    newest = (date.today() + timedelta(days=days_ahead)).isoformat()
    data = await ctx.lifespan_context["client"].get(
        f"/athlete/{athlete_id}/events",
        params=httpx.QueryParams(oldest=oldest, newest=newest, category=category),
    )
    return data.json()


@coaching.tool(tags={"Coaching"})
async def update_athlete_event(
    ctx: Context,
    athlete_id: str,
    event_id: int,
    name: str | None = None,
    description: str | None = None,
    start_date: str | None = None,
    load_target: int | None = None,
    time_target: int | None = None,
    distance_target: float | None = None,
    hide_from_athlete: bool | None = None,
) -> dict:
    """Update a planned event (workout, note etc.) on a coached athlete's calendar.

    Args:
        athlete_id: The athlete's ID (e.g. 'i12345'). Get IDs from list_coached_athletes.
        event_id: The event ID to update.
        name: New event title.
        description: New description or coaching notes.
        start_date: New date in ISO-8601 format (e.g. '2026-03-10').
        load_target: Target training load (TSS).
        time_target: Target duration in seconds.
        distance_target: Target distance in metres.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
    """
    body = {
        "name": name,
        "description": description,
        "start_date_local": f"{start_date}T00:00:00" if start_date else None,
        "load_target": load_target,
        "time_target": time_target,
        "distance_target": distance_target,
        "hide_from_athlete": hide_from_athlete,
    }
    resp = await ctx.lifespan_context["client"].put(
        f"/athlete/{athlete_id}/events/{event_id}",
        json={k: v for k, v in body.items() if v is not None},
    )
    resp.raise_for_status()
    return {"message": f"Event {event_id} updated successfully.", "status": resp.status_code}


@coaching.tool(tags={"Coaching"})
async def create_athlete_workout(
    ctx: Context,
    athlete_id: str,
    date: str,
    name: str,
    description: str = "",
    type: str | None = None,
    indoor: bool | None = None,
    moving_time: int | None = None,
    target: str | None = None,
    load_target: int | None = None,
    distance_target: float | None = None,
    hide_from_athlete: bool | None = None,
) -> dict:
    """Create a workout event directly on a coached athlete's calendar.

    Args:
        athlete_id: The athlete's ID (e.g. 'i12345'). Get IDs from list_coached_athletes.
        date: The date to schedule the workout on, in ISO-8601 format (e.g. '2026-03-10').
        name: Workout name.
        description: Workout description or interval structure in Intervals.icu native format.
        type: Sport type (e.g. 'Ride', 'Run', 'Swim').
        indoor: Whether the workout is indoors.
        moving_time: Target duration in seconds.
        target: Primary target metric — AUTO, POWER, HR, or PACE.
        load_target: Target training load (TSS).
        distance_target: Target distance in metres.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
    """
    body: dict = {
        "category": "WORKOUT",
        "start_date_local": f"{date}T00:00:00",
        "name": name,
        "description": description,
    }
    optional = {
        "type": type,
        "indoor": indoor,
        "moving_time": moving_time,
        "target": target,
        "load_target": load_target,
        "distance_target": distance_target,
        "hide_from_athlete": hide_from_athlete,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    resp = await ctx.lifespan_context["client"].post(
        f"/athlete/{athlete_id}/events",
        params={"upsertOnUid": False},
        json=body,
    )
    resp.raise_for_status()
    return {"message": f"Workout '{name}' created on {date} for athlete {athlete_id}.", "status": resp.status_code}


@coaching.tool(tags={"Coaching"})
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
    resp.raise_for_status()
    return {
        "message": f"Coach evaluation for activity {activity_id} set to {evaluation.name}.",
        "status": resp.status_code,
    }


@coaching.tool(tags={"Coaching"})
async def post_activity_message(ctx: Context, activity_id: str, content: str) -> dict:
    """Post a coaching message or feedback comment on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        content: The message text to post.
    """
    resp = await ctx.lifespan_context["client"].post(
        f"/activity/{activity_id}/messages", json={"content": content}
    )
    resp.raise_for_status()
    return {"message": f"Message posted to activity {activity_id}.", "status": resp.status_code}
