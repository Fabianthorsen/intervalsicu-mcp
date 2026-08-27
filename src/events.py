import enum
from datetime import date, timedelta
from typing import TypedDict

import httpx
from fastmcp import Context, FastMCP

from blocks import (
    ATL_DAYS,
    CTL_DAYS,
    apply_overlay,
    date_range,
    planned_loads,
    project_fitness_series,
)
from client import get_client
from shaping import project_and_prune, project_and_prune_list

events = FastMCP("events")


class EventFields(enum.Enum):
    """Semantic field groups for event/calendar data."""

    HEADLINE = "headline"
    TARGETS = "targets"
    COACHING = "coaching"
    METADATA = "metadata"
    ALL = "all"


EVENT_TAXONOMY = {
    "HEADLINE": [
        "name",
        "category",
        "type",
        "moving_time",
        "distance",
        "icu_training_load",
    ],
    "TARGETS": [
        "target",
        "load_target",
        "time_target",
        "distance_target",
        "icu_intensity",
        "icu_ftp",
        "carbs_per_hour",
        "max_training_time",
    ],
    "COACHING": [
        "description",
        "tags",
        "hide_from_athlete",
        "athlete_cannot_edit",
        "show_as_note",
    ],
    "METADATA": [
        "color",
        "indoor",
        "sub_type",
        "external_id",
        "updated",
        "created_by_id",
        "plan_applied",
    ],
}


@events.tool(tags={"Calendar"}, annotations={"readOnlyHint": True})
async def list_events(
    ctx: Context,
    athlete_id: str = "0",
    days_ahead: int = 7,
    days_back: int = 0,
    category: str | None = None,
) -> list:
    """List planned events (workouts, notes, races) on calendar — core + HEADLINE fields.

    Use get_event with an event id to drill into targets, coaching notes or metadata.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        days_ahead: How many days into the future to return (default 7).
        days_back: How many days into the past to include (default 0).
        category: Comma-separated event categories to filter for, e.g. 'WORKOUT,NOTE'.
    """
    oldest = (date.today() - timedelta(days=days_back)).isoformat()
    newest = (date.today() + timedelta(days=days_ahead)).isoformat()
    client = await get_client(ctx)

    data = await client.get(
        f"/athlete/{athlete_id}/events",
        params=httpx.QueryParams(oldest=oldest, newest=newest, category=category),
    )
    records = data.json()

    return project_and_prune_list(records, ["HEADLINE"], EVENT_TAXONOMY)


@events.tool(tags={"Calendar"}, annotations={"readOnlyHint": True})
async def get_event(
    ctx: Context, event_id: int, athlete_id: str = "0", include: list[str] | None = None
) -> dict:
    """Get a single planned event by ID with optional field group selection.

    Args:
        event_id: The event ID.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        include: List of field groups to include. Omit for core + HEADLINE.
                 Options: HEADLINE (default), TARGETS, COACHING, METADATA, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        (g.value if isinstance(g, EventFields) else g).upper()
        for g in include
    ]

    client = await get_client(ctx)

    resp = await client.get(
        f"/athlete/{athlete_id}/events/{event_id}"
    )
    obj = resp.json()

    return project_and_prune(obj, include_groups, EVENT_TAXONOMY)


@events.tool(tags={"Training"}, annotations={"readOnlyHint": True})
async def get_training_plan(
    ctx: Context, athlete_id: str = "0", include: list[str] | None = None
) -> dict:
    """Get the athlete's current training plan with optional field selection.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        include: List of field groups to include. Omit for core + HEADLINE.
                 Options: HEADLINE (default), TARGETS, COACHING, METADATA, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        (g.value if isinstance(g, EventFields) else g).upper()
        for g in include
    ]

    client = await get_client(ctx)

    resp = await client.get(
        f"/athlete/{athlete_id}/training-plan"
    )
    obj = resp.json()

    return project_and_prune(obj, include_groups, EVENT_TAXONOMY)


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

    The library workout's description is copied onto the calendar event. See
    create_workout for the description format if you are authoring one.

    Args:
        workout_id: The library workout ID to schedule. Get IDs from list_workout_folders.
        date: The date to schedule the workout on, in ISO-8601 format (e.g. '2026-03-10').
        athlete_id: Athlete whose calendar to schedule onto. Use '0' for the authenticated user (default).
        library_athlete_id: Athlete whose library to pull the workout from. Defaults to '0' (the coach/authenticated user).
        name: Override the workout name on the calendar event.
        indoor: Override whether the workout is indoors.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
    """
    client = await get_client(ctx)

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
    client = await get_client(ctx)

    resp = await client.delete(
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
    tags: list[str] | None = None,
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
        color: Hex color string (e.g. '#FF5733'). Reuse the colour already on
               similar events rather than inventing one — list_events with
               include=['METADATA'] returns the colour in use.
        tags: Replaces the event's tags entirely. Pass the full list you want.
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
        "tags": tags,
        "load_target": load_target,
        "time_target": time_target,
        "distance_target": distance_target,
    }
    body: dict = {k: v for k, v in optional.items() if v is not None}
    if date is not None:
        body["start_date_local"] = f"{date}T00:00:00"

    client = await get_client(ctx)

    resp = await client.put(
        f"/athlete/{athlete_id}/events/{event_id}", json=body
    )
    return {"message": f"Event {event_id} updated.", "status": resp.status_code}


NOTE_CATEGORIES = ("NOTE", "HOLIDAY", "SICK", "INJURED", "SEASON_START")


@events.tool(tags={"Calendar"})
async def create_note(
    ctx: Context,
    date: str,
    name: str,
    description: str = "",
    end_date: str | None = None,
    category: str = "NOTE",
    color: str | None = None,
    tags: list[str] | None = None,
    athlete_id: str = "0",
) -> dict:
    """Create a note or a whole-day marker on an athlete's calendar.

    Covers the day-describing categories: a plain note, a holiday, and spells
    of illness or injury. All of them span one or more days and carry no
    training target — for a race use create_race, for a session use
    create_workout.

    Args:
        date: Start date in ISO-8601 format (e.g. '2026-03-10').
        name: Title of the note.
        description: Optional body text for the note.
        end_date: Optional end date for multi-day notes (e.g. a trip). ISO-8601.
        category: NOTE (default), HOLIDAY, SICK, INJURED or SEASON_START.
                  HOLIDAY/SICK/INJURED mark the day on the athlete's calendar
                  and explain a gap in training; SEASON_START anchors the season.
        color: Hex color string (e.g. '#FF5733'). Reuse the colour already on
               similar events rather than inventing one — list_events with
               include=['METADATA'] returns the colour in use.
        tags: Tags to attach to the event.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    category = category.upper()
    if category not in NOTE_CATEGORIES:
        raise ValueError(
            f"category must be one of {', '.join(NOTE_CATEGORIES)}, got '{category}'."
        )

    body: dict = {
        "category": category,
        "start_date_local": f"{date}T00:00:00",
        "name": name,
        "description": description,
    }
    if end_date:
        body["end_date_local"] = f"{end_date}T00:00:00"
    optional = {"color": color, "tags": tags}
    body.update({k: v for k, v in optional.items() if v is not None})
    client = await get_client(ctx)

    resp = await client.post(
        f"/athlete/{athlete_id}/events",
        params={"upsertOnUid": False},
        json=body,
    )
    return {
        "message": f"{category.replace('_', ' ').title()} '{name}' created on {date}.",
        "status": resp.status_code,
    }


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
    color: str | None = None,
    tags: list[str] | None = None,
    hide_from_athlete: bool | None = None,
) -> dict:
    """Create a workout event directly on an athlete's calendar.

    ## Writing the description

    Always populate `description`. For Ride and Run it has two parts: a prose
    intro of 2-4 sentences covering purpose, feel and coaching focus, followed
    immediately by a structured spec in Intervals.icu text format.

    Spec format:
      - Section headers carry no dash: `Warmup`, `Main set 4x`, `Cooldown`.
        Put any repeat count on the header, not the steps.
      - Each step starts with `- `, then a duration, then an intensity target.
      - Durations look like `30s`, `10m`, `1m30`.
      - Ride intensity: zones (`Z2`, `Z3`) for steady work, `%FTP` ranges
        (`90-95%`) where precision or outdoor flexibility matters. Add cadence
        where it matters: `85-95rpm`.
      - Run intensity: HR zones (`Z2 HR`) for steady work, `%LTHR` ranges
        (`95-100% LTHR`) where precision matters.

    Example (Ride):
        Threshold work to build sustained power. Keep cadence high through the
        intervals and focus on smooth pedalling. Outdoors, use the ranges to
        accommodate terrain.

        Warmup
        - 15m Z2 85-95rpm

        Main set 4x
        - 8m 95-100% 88-92rpm
        - 4m Z1 recovery

        Cooldown
        - 10m Z1

    For HR-trackable sports with no power or pace — Padel, Football, Tennis,
    Climbing and similar — use the same two parts, but keep the spec minimal:
    one or two steps of duration at an `%LTHR` range, calibrated from what
    previous sessions of that type actually cost. The spec is what lets
    intervals.icu compute the planned load; prose alone plans zero load, so
    the session never reaches the fitness chart. Do not reach for
    `load_target` to work around a missing spec.

    Example (Padel):
        Match play. Expect long rallies and plenty of stop-start work, so
        treat it as the week's hard session rather than an easy extra.

        Main set
        - 90m 70-80% LTHR

    This depends on the sport's settings group having an LTHR — if the planned
    load comes back as zero, check with get_sport_settings.

    For genuinely unmeasured sports (Yoga, WeightTraining, Swim without a
    sensor) write prose only: goal, equipment, step-by-step structure with
    sets, reps, distances and rest, plus technique cues. These plan no load,
    which is the honest outcome.

    Args:
        athlete_id: The athlete's ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        date: The date to schedule the workout on, in ISO-8601 format (e.g. '2026-03-10').
        name: Workout name.
        description: Workout description or interval structure — see above for the format.
        type: Sport type (e.g. 'Ride', 'Run', 'Swim').
        indoor: Whether the workout is indoors.
        moving_time: Target duration in seconds.
        target: Primary target metric — AUTO, POWER, HR, or PACE.
        load_target: Target training load (TSS).
        distance_target: Target distance in metres.
        color: Hex color string (e.g. '#FF5733'). Reuse the colour already on
               similar events rather than inventing one — list_events with
               include=['METADATA'] returns the colour in use.
        tags: Tags to attach to the event.
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
        "color": color,
        "tags": tags,
        "hide_from_athlete": hide_from_athlete,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    client = await get_client(ctx)

    resp = await client.post(
        f"/athlete/{athlete_id}/events",
        params={"upsertOnUid": False},
        json=body,
    )
    return {"message": f"Workout '{name}' created on {date} for athlete {athlete_id}.", "status": resp.status_code}


RACE_PRIORITIES = ("A", "B", "C")


@events.tool(tags={"Calendar"})
async def create_race(
    ctx: Context,
    date: str,
    name: str,
    priority: str = "A",
    athlete_id: str = "0",
    type: str | None = None,
    description: str = "",
    moving_time: int | None = None,
    distance_target: float | None = None,
    load_target: int | None = None,
    target: str | None = None,
    indoor: bool | None = None,
    color: str | None = None,
    tags: list[str] | None = None,
    hide_from_athlete: bool | None = None,
) -> dict:
    """Put a race on an athlete's calendar, with its priority and expected demand.

    Give the race a duration or distance where you can. A race with neither
    contributes nothing to planned load, so it shows on the calendar but not on
    the fitness chart — which is rarely what a season plan wants.

    Args:
        date: Race date in ISO-8601 format (e.g. '2026-03-10').
        name: Race name.
        priority: 'A', 'B' or 'C'. A is a season goal raced fully rested; B is
                  raced hard but trained through; C is a hard training day.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        type: Sport type (e.g. 'Ride', 'Run', 'Swim').
        description: Course, plan, pacing notes and anything the athlete should
                     read on the day.
        moving_time: Expected duration in seconds.
        distance_target: Race distance in metres.
        load_target: Expected training load (TSS), if you want to override what
                     intervals.icu derives from duration and intensity.
        target: Primary target metric — AUTO, POWER, HR, or PACE.
        indoor: Whether the race is indoors.
        color: Hex color string (e.g. '#FF5733'). Reuse the colour already on
               similar events rather than inventing one — list_events with
               include=['METADATA'] returns the colour in use.
        tags: Tags to attach to the event.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
    """
    priority = priority.upper()
    if priority not in RACE_PRIORITIES:
        raise ValueError(
            f"priority must be one of {', '.join(RACE_PRIORITIES)}, got '{priority}'."
        )

    body: dict = {
        "category": f"RACE_{priority}",
        "start_date_local": f"{date}T00:00:00",
        "name": name,
        "description": description,
    }
    optional = {
        "type": type,
        "moving_time": moving_time,
        "distance_target": distance_target,
        "load_target": load_target,
        "target": target,
        "indoor": indoor,
        "color": color,
        "tags": tags,
        "hide_from_athlete": hide_from_athlete,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    client = await get_client(ctx)

    resp = await client.post(
        f"/athlete/{athlete_id}/events",
        params={"upsertOnUid": False},
        json=body,
    )
    return {
        "message": f"{priority}-race '{name}' created on {date}.",
        "status": resp.status_code,
    }


class EventSpec(TypedDict, total=False):
    """One calendar entry in a batch write.

    Same vocabulary as create_workout / create_race / create_note — `date` and
    `name` are required, everything else is optional and depends on `category`.
    """

    date: str
    name: str
    category: str
    description: str
    type: str
    indoor: bool
    moving_time: int
    target: str
    load_target: int
    distance_target: float
    end_date: str
    color: str
    tags: list[str]
    hide_from_athlete: bool


BATCH_CATEGORIES = (
    "WORKOUT",
    "RACE_A",
    "RACE_B",
    "RACE_C",
    *NOTE_CATEGORIES,
)

_SPEC_PASSTHROUGH = (
    "description",
    "type",
    "indoor",
    "moving_time",
    "target",
    "load_target",
    "distance_target",
    "color",
    "tags",
    "hide_from_athlete",
)


def _event_body(spec: EventSpec) -> dict:
    """Turn one EventSpec into the API's event body. Raises on a bad spec."""
    missing = [k for k in ("date", "name") if not spec.get(k)]
    if missing:
        raise ValueError(f"Event spec is missing required field(s): {', '.join(missing)}.")

    category = str(spec.get("category", "WORKOUT")).upper()
    if category not in BATCH_CATEGORIES:
        raise ValueError(
            f"category must be one of {', '.join(BATCH_CATEGORIES)}, got '{category}'."
        )

    body: dict = {
        "category": category,
        "start_date_local": f"{spec['date']}T00:00:00",
        "name": spec["name"],
    }
    if spec.get("end_date"):
        body["end_date_local"] = f"{spec['end_date']}T00:00:00"
    body.update({k: spec[k] for k in _SPEC_PASSTHROUGH if spec.get(k) is not None})
    return body


@events.tool(tags={"Calendar"})
async def create_events(
    ctx: Context, events: list[EventSpec], athlete_id: str = "0"
) -> dict:
    """Create several calendar entries at once — a whole planned week in one call.

    Mixes categories freely: workouts, races, notes and holidays in the same
    batch. Prefer this over repeated create_workout calls when laying out a
    block; use the singular tools for a one-off.

    Write each entry's `description` exactly as create_workout documents — its
    docstring carries the structured-interval format and the rules on which
    sports need a spec to get a planned load.

    Args:
        events: The entries to create. Each needs `date` (ISO-8601) and `name`;
                `category` defaults to WORKOUT and accepts RACE_A/RACE_B/RACE_C,
                NOTE, HOLIDAY, SICK, INJURED and SEASON_START. The remaining
                fields match the singular tools.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    if not events:
        raise ValueError("events is empty — nothing to create.")

    bodies = [_event_body(spec) for spec in events]
    client = await get_client(ctx)

    resp = await client.post(
        f"/athlete/{athlete_id}/events/bulk",
        params={"upsertOnUid": False, "updatePlanApplied": False},
        json=bodies,
    )
    created = resp.json()
    count = len(created) if isinstance(created, list) else 0

    result = {
        "requested": len(bodies),
        "created": count,
        "status": resp.status_code,
    }
    if count != len(bodies):
        # The bulk endpoint returns a bare array with no per-item error shape,
        # so a partial write is only visible by counting. Say so rather than
        # reporting a cheerful success.
        result["message"] = (
            f"Partial write: {count} of {len(bodies)} events were created. "
            "Check the calendar before assuming the plan is complete."
        )
    else:
        result["message"] = f"{count} events created for athlete {athlete_id}."
    return result


@events.tool(tags={"Analysis"}, annotations={"readOnlyHint": True})
async def project_fitness(
    ctx: Context,
    from_date: str,
    to_date: str,
    athlete_id: str = "0",
    overlay: list[dict] | None = None,
) -> dict:
    """Project CTL, ATL and TSB forward over planned training.

    Read-only. Nothing here writes to the calendar, including the overlay.

    Every day is labelled with where its numbers came from. 'platform' means
    intervals.icu supplied CTL and ATL for that date, so the figure cannot
    disagree with the fitness chart the athlete is looking at. 'extrapolated'
    means this tool computed it from planned load. 'hypothetical' means an
    overlay applies — and applies to every day from the first change onward,
    since a change carries forward through the series.

    Days whose planned load was typed in rather than derived from structured
    steps are flagged `load_is_estimated`. Those are softer numbers: an
    unstructured padel session should not read as firmly as an ERG workout.

    ## Hypotheticals

    `overlay` answers "what if" without touching the calendar. Each entry
    names a `date`, plus `event_id` when a day holds more than one session:

      - `{"date": "2026-03-14", "skip": true}` — drop that day's session
      - `{"date": "2026-03-14", "load": 85}` — set the load exactly
      - `{"date": "2026-03-14", "moving_time": 5400}` — scale load by duration
      - `{"date": "2026-03-19", "load": 60, "name": "Extra endurance"}` — add a
        session where none is planned

    Duration scaling assumes the minutes removed were of average intensity.
    Sessions are usually trimmed from the easy tail instead, so it overstates
    the saving; those days come back marked approximate. Prefer `load` when
    you know it.

    The response echoes what each overlay entry did — modified, skipped, added
    or matched nothing. Check it: a mistyped date becomes an added session
    rather than an error, and would otherwise hide inside a CTL number.

    Args:
        from_date: First day to project (ISO-8601).
        to_date: Last day to project (ISO-8601).
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        overlay: Optional hypothetical changes — see above. Never written.
    """
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    days = date_range(start, end)

    client = await get_client(ctx)

    events_resp = await client.get(
        f"/athlete/{athlete_id}/events",
        params=httpx.QueryParams(
            oldest=from_date, newest=to_date, category="WORKOUT,RACE_A,RACE_B,RACE_C"
        ),
    )
    # One day before the range so there is a seed to carry forward from when
    # the platform has nothing for the first projected day.
    seed_from = (start - timedelta(days=1)).isoformat()
    wellness_resp = await client.get(
        f"/athlete/{athlete_id}/wellness",
        params=httpx.QueryParams(
            oldest=seed_from, newest=to_date, fields="id,ctl,atl"
        ),
    )

    rows = wellness_resp.json()
    platform = {
        r["id"]: r
        for r in rows
        if isinstance(r, dict) and r.get("id")
    }

    seed = platform.get(seed_from) or {}
    if seed.get("ctl") is None:
        # Fall back to the most recent row at or before the range start.
        earlier = [
            r for key, r in sorted(platform.items())
            if key <= seed_from and r.get("ctl") is not None
        ]
        seed = earlier[-1] if earlier else {}

    plan = planned_loads(events_resp.json())
    plan, echo = apply_overlay(plan, overlay)
    overlaid = {e["date"] for e in echo if e.get("action") in ("modified", "skipped", "added")}

    series = project_fitness_series(
        days,
        plan,
        seed_ctl=seed.get("ctl") or 0,
        seed_atl=seed.get("atl") or 0,
        platform=platform,
        overlaid_dates=overlaid,
        ctl_days=CTL_DAYS,
        atl_days=ATL_DAYS,
    )

    result: dict = {
        "from_date": from_date,
        "to_date": to_date,
        "seed": {"ctl": seed.get("ctl"), "atl": seed.get("atl"), "date": seed_from},
        "days": series,
    }
    if echo:
        result["overlay"] = echo
    if not any(d["source"] == "platform" for d in series):
        # Nothing came back from the platform for this range, so every number
        # here is ours. Say so rather than let it pass as the fitness chart.
        result["warning"] = (
            "intervals.icu returned no CTL/ATL for these dates, so every value is "
            "computed by this tool and may differ from the fitness chart."
        )
    return result
