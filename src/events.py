from datetime import date, timedelta

import httpx
from fastmcp import Context, FastMCP

events = FastMCP("events")


@events.tool(tags={"Calendar"}, annotations={"readOnlyHint": True})
async def list_events(
    ctx: Context,
    athlete_id: str = "0",
    days_ahead: int = 7,
    days_back: int = 0,
    category: str | None = None,
) -> list:
    """List planned events (workouts, notes, races) on the athlete's calendar.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
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


@events.tool(tags={"Calendar"}, annotations={"readOnlyHint": True})
async def get_event(ctx: Context, event_id: int, athlete_id: str = "0") -> dict:
    """Get a single planned event (workout, note, race) by ID.

    Args:
        event_id: The event ID.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    resp = await ctx.lifespan_context["client"].get(
        f"/athlete/{athlete_id}/events/{event_id}"
    )
    return resp.json()


@events.tool(tags={"Training"}, annotations={"readOnlyHint": True})
async def get_training_plan(ctx: Context, athlete_id: str = "0") -> dict:
    """Get the athlete's current training plan.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    resp = await ctx.lifespan_context["client"].get(
        f"/athlete/{athlete_id}/training-plan"
    )
    return resp.json()


@events.tool(tags={"Calendar"})
async def schedule_workout(
    ctx: Context,
    workout_id: int,
    date: str,
    athlete_id: str = "0",
    library_athlete_id: str = "0",
    name: str | None = None,
    indoor: bool | None = None,
    hide_from_athlete: bool | None = None,
) -> dict:
    """Schedule a workout from the workout library onto an athlete's calendar.

    Args:
        workout_id: The library workout ID to schedule. Get IDs from list_workout_folders.
        date: The date to schedule the workout on, in ISO-8601 format (e.g. '2026-03-10').
        athlete_id: Athlete whose calendar to schedule onto. Use '0' for the authenticated user (default).
        library_athlete_id: Athlete whose library to pull the workout from. Defaults to '0' (the coach/authenticated user).
        name: Override the workout name on the calendar event.
        indoor: Override whether the workout is indoors.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
    """
    client = ctx.lifespan_context["client"]

    workout_resp = await client.get(f"/athlete/{library_athlete_id}/workouts/{workout_id}")
    workout = workout_resp.json()

    copy_fields = ("description", "workout_doc", "type", "moving_time", "target",
                   "targets", "sub_type", "color", "tags", "carbs_per_hour", "distance")
    body: dict = {
        "category": "WORKOUT",
        "start_date_local": f"{date}T00:00:00",
        "name": name or workout.get("name"),
        "indoor": indoor if indoor is not None else workout.get("indoor"),
    }
    body.update({k: workout[k] for k in copy_fields if workout.get(k) is not None})
    if hide_from_athlete is not None:
        body["hide_from_athlete"] = hide_from_athlete

    resp = await client.post(
        f"/athlete/{athlete_id}/events",
        params={"upsertOnUid": False},
        json=body,
    )
    return {"message": f"Workout '{body['name']}' scheduled on {date}.", "status": resp.status_code}


@events.tool(tags={"Calendar"}, annotations={"destructiveHint": True})
async def delete_event(ctx: Context, event_id: int, athlete_id: str = "0") -> dict:
    """Delete an event (planned workout, note, race etc.) from an athlete's calendar.

    Args:
        event_id: The event ID to delete.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    resp = await ctx.lifespan_context["client"].delete(
        f"/athlete/{athlete_id}/events/{event_id}"
    )
    return {"message": f"Event {event_id} deleted.", "status": resp.status_code}


@events.tool(tags={"Calendar"})
async def update_event(
    ctx: Context,
    event_id: int,
    athlete_id: str = "0",
    name: str | None = None,
    date: str | None = None,
    description: str | None = None,
    type: str | None = None,
    indoor: bool | None = None,
    hide_from_athlete: bool | None = None,
    moving_time: int | None = None,
    color: str | None = None,
    load_target: int | None = None,
    time_target: int | None = None,
    distance_target: float | None = None,
) -> dict:
    """Update an existing event on an athlete's calendar (planned workout, note, race etc.).

    Only the fields you provide will be updated — all others are left unchanged.

    Args:
        event_id: The event ID to update.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        name: New name for the event.
        date: New date in ISO-8601 format (e.g. '2026-03-10').
        description: New description / workout steps.
        type: Sport type (e.g. 'Ride', 'Run', 'Swim').
        indoor: Whether the workout is indoors.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
        moving_time: Target duration in seconds.
        color: Hex color string (e.g. '#FF5733').
        load_target: Target training load (TSS).
        time_target: Target duration in seconds (planned event field).
        distance_target: Target distance in metres (planned event field).
    """
    optional = {
        "name": name,
        "description": description,
        "type": type,
        "indoor": indoor,
        "hide_from_athlete": hide_from_athlete,
        "moving_time": moving_time,
        "color": color,
        "load_target": load_target,
        "time_target": time_target,
        "distance_target": distance_target,
    }
    body: dict = {k: v for k, v in optional.items() if v is not None}
    if date is not None:
        body["start_date_local"] = f"{date}T00:00:00"

    resp = await ctx.lifespan_context["client"].put(
        f"/athlete/{athlete_id}/events/{event_id}", json=body
    )
    return {"message": f"Event {event_id} updated.", "status": resp.status_code}


@events.tool(tags={"Calendar"})
async def create_note(
    ctx: Context,
    date: str,
    name: str,
    description: str = "",
    end_date: str | None = None,
    athlete_id: str = "0",
) -> dict:
    """Create a note on an athlete's calendar (e.g. rest day, travel, illness, race trip).

    Args:
        date: Start date in ISO-8601 format (e.g. '2026-03-10').
        name: Title of the note.
        description: Optional body text for the note.
        end_date: Optional end date for multi-day notes (e.g. a trip). ISO-8601.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    body = {
        "category": "NOTE",
        "start_date_local": f"{date}T00:00:00",
        "name": name,
        "description": description,
    }
    if end_date:
        body["end_date_local"] = f"{end_date}T00:00:00"
    resp = await ctx.lifespan_context["client"].post(
        f"/athlete/{athlete_id}/events",
        params={"upsertOnUid": False},
        json=body,
    )
    return {"message": f"Note '{name}' created.", "status": resp.status_code}


@events.tool(tags={"Calendar"})
async def create_workout(
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
    """Create a workout event directly on an athlete's calendar.

    Args:
        athlete_id: The athlete's ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
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
    return {"message": f"Workout '{name}' created on {date} for athlete {athlete_id}.", "status": resp.status_code}
