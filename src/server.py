"""Intervals.icu MCP server — exposes training data as MCP tools."""

import os
from datetime import date, timedelta
from typing import AsyncIterator

import httpx

from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.auth import AuthContext
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.server.lifespan import lifespan

from activities import activities
from athletes import athletes
from coaching import coaching
from library import library
from wellness import wellness

load_dotenv()

API_KEY = os.environ["INTERVALS_API_KEY"]
GITHUB_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
GITHUB_CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
JWT_SIGNING_KEY = os.environ["JWT_SIGNING_KEY"]
ALLOWED_GITHUB_USERS = {u.lower() for u in os.environ.get("ALLOWED_GITHUB_USERS", "").split(",") if u}
BASE_URL = "https://intervals.icu/api/v1"


@lifespan
async def client_lifespan(_: FastMCP) -> AsyncIterator[dict]:
    async with httpx.AsyncClient(
        base_url=BASE_URL, auth=("API_KEY", API_KEY)
    ) as client:
        yield {"client": client}


auth = GitHubProvider(
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    base_url="https://intervalsicu-mcp.fly.dev",
    jwt_signing_key=JWT_SIGNING_KEY,
)

mcp = FastMCP(
    "intervals-icu",
    lifespan=client_lifespan,
    auth=auth,
    instructions="""
    You have access to the Intervals.icu training platform for endurance athletes.

    ## Key conventions
    - `athlete_id`: Use '0' to refer to the authenticated user. For coached athletes use their
      ID (e.g. 'i12345') — get IDs from list_coached_athletes.
    - Activity IDs look like 'i129230824'.
    - Dates are ISO-8601 strings (e.g. '2026-03-10').
    - Distances are in metres, durations in seconds.

    ## Tool groups
    - **Athletes** — profile data (FTP, weight, HR zones, timezone)
    - **Activities** — completed workouts with intervals, power, HR, pace and TSS
    - **Wellness** — daily HRV, resting HR, sleep, CTL/ATL/TSB (fitness/fatigue/form)
    - **Gear** — bikes, shoes, components and maintenance reminders
    - **Calendar** — planned events (workouts, notes, races) on the athlete's calendar
    - **Training** — active training plan
    - **Coaching** — tools for coaches: view and manage athlete calendars, post feedback,
      set evaluation ticks on activities (WTF/POOR/SEEN/GOOD/AMAZING)
    - **Workouts** — workout library: folders and structured workout definitions.
      list_workout_folders returns folders with workouts nested inside as 'children'.

    ## Common workflows
    - To review an athlete's week: use list_athlete_events + list_activities_between_dates
    - To check readiness: use get_wellness with days=1 for today, days=7 or days=30 for trends
    - To give feedback: use set_coach_evaluation and/or post_activity_message
    - To build a workout library: create folders with create_workout_folder, then add
      workouts with create_workout_in_folder
    - To schedule a library workout: use list_workout_folders to find the workout id (in
      children), then call schedule_workout

    ## Creating workouts

    Always populate the `description` field when creating or scheduling a workout.

    ### Cycling (type='Ride') and Running (type='Run')
    The description must contain two parts:

    1. **Prose intro** (2-4 sentences): purpose, feel, and key coaching focus for the session.
    2. **Structured spec** using Intervals.icu text format immediately after:
       - Section headers (no dash) label blocks: `Warmup`, `Main set Nx`, `Cooldown`
       - Each step starts with `- `, followed by duration then intensity target
       - Duration: `30s`, `10m`, `1m30`
       - **Ride intensity** — use zones (`Z2`, `Z3`, `Z4`) for steady-state work; use
         `%FTP` ranges (e.g. `90-95%`) when precision or flexibility matters (e.g. non-ERG,
         hard intervals). Add cadence where relevant: `85-95rpm`
       - **Run intensity** — use HR zones (`Z2 HR`, `Z3 HR`) for steady-state work; use
         `%LTHR` ranges (e.g. `95-100% LTHR`) when precision matters
       - Repeats: put the multiplier on the section header, e.g. `Main set 5x`

    Example Ride description:
    ```
    Threshold work to build sustained power. Keep cadence high throughout the intervals
    and focus on smooth pedalling. If riding outdoors, use the ranges to accommodate terrain.

    Warmup
    - 15m Z2 85-95rpm

    Main set 4x
    - 8m 95-100% 88-92rpm
    - 4m Z1 recovery

    Cooldown
    - 10m Z1
    ```

    Example Run description:
    ```
    Aerobic base run with strides to finish. Keep effort conversational throughout the
    main block. The strides are short and sharp — focus on form, not speed.

    Warmup
    - 10m Z1 HR

    Main set
    - 30m Z2 HR

    Strides 6x
    - 20s 95-100% LTHR
    - 40s Z1 HR recovery

    Cooldown
    - 5m Z1 HR
    ```

    ### All other sport types (Swim, WeightTraining, Yoga, etc.)
    Write a well-formatted prose description covering: goal of the session, equipment
    needed, step-by-step structure (sets, reps, distances, rest periods), and any
    technique cues. No structured interval spec is required.

    ## Reviewing a workout (coached athletes)
    To analyse a workout and post coaching feedback:
    1. Identify the activity — use list_activities_between_dates (last 14 days) to find the
       latest, or use a specific activity ID.
    2. Fetch in parallel: get_activity (summary stats: TSS, load, HR, power) and
       get_activity_intervals (interval breakdown, targets vs actuals, power zones).
    3. Check existing messages with get_activity_messages — if the athlete has left a
       comment, read it and factor it into your feedback (e.g. they felt tired, had an
       issue, or are happy with the effort). Avoid duplicating existing coach feedback.
    4. Assess: did the athlete hit targets? Interval consistency? Compare load to wellness
       (get_wellness with days=7 if needed). Flag high HR, dropped power, missed intervals.
    5. Set a tick with set_coach_evaluation: 1=WTF, 2=POOR, 3=SEEN, 4=GOOD, 5=AMAZING.
    6. Post feedback with post_activity_message: 2–4 sentences, direct and specific,
       mention what went well and one concrete observation or suggestion.
    """,
)

def check_github_user(ctx: AuthContext) -> bool:
    if ctx.token is None:
        return False
    return ctx.token.claims.get("login", "").lower() in ALLOWED_GITHUB_USERS


mcp.add_middleware(AuthMiddleware(auth=check_github_user))

mcp.mount(athletes)
mcp.mount(activities)
mcp.mount(coaching)
mcp.mount(wellness)
mcp.mount(library)




@mcp.tool(tags={"Gear"}, annotations={"readOnlyHint": True})
async def list_gear(ctx: Context, athlete_id: str = "0") -> list:
    """List all gear (bikes, shoes, components) with total distance, time, activity
    count, and any maintenance reminders."""
    resp = await ctx.lifespan_context["client"].get(f"/athlete/{athlete_id}/gear")
    return resp.json()


@mcp.tool(tags={"Calendar"}, annotations={"readOnlyHint": True})
async def list_events(
    ctx: Context,
    athlete_id: str = "0",
    days_ahead: int = 7,
    days_back: int = 0,
    category: str | None = None,
) -> list:
    """List planned events (workouts, notes, races) on the athlete's calendar.

    Args:
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


@mcp.tool(tags={"Calendar"}, annotations={"readOnlyHint": True})
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


@mcp.tool(tags={"Training"}, annotations={"readOnlyHint": True})
async def get_training_plan(ctx: Context, athlete_id: str = "0") -> dict:
    """Get the athlete's current training plan."""
    resp = await ctx.lifespan_context["client"].get(
        f"/athlete/{athlete_id}/training-plan"
    )
    return resp.json()


@mcp.tool(tags={"Calendar"})
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
    workout_resp.raise_for_status()
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
    resp.raise_for_status()
    return {"message": f"Workout '{body['name']}' scheduled on {date}.", "status": resp.status_code}


@mcp.tool(tags={"Calendar"}, annotations={"destructiveHint": True})
async def delete_event(ctx: Context, event_id: int, athlete_id: str = "0") -> dict:
    """Delete an event (planned workout, note, race etc.) from an athlete's calendar.

    Args:
        event_id: The event ID to delete.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    resp = await ctx.lifespan_context["client"].delete(
        f"/athlete/{athlete_id}/events/{event_id}"
    )
    resp.raise_for_status()
    return {"message": f"Event {event_id} deleted.", "status": resp.status_code}


@mcp.tool(tags={"Calendar"})
async def update_athlete_event(
    ctx: Context,
    event_id: int,
    athlete_id: str = "0",
    name: str | None = None,
    date: str | None = None,
    description: str | None = None,
    indoor: bool | None = None,
    hide_from_athlete: bool | None = None,
    moving_time: int | None = None,
    color: str | None = None,
) -> dict:
    """Update an existing event on an athlete's calendar (planned workout, note, race etc.).

    Only the fields you provide will be updated — all others are left unchanged.

    Args:
        event_id: The event ID to update.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        name: New name for the event.
        date: New date in ISO-8601 format (e.g. '2026-03-10').
        description: New description / workout steps.
        indoor: Whether the workout is indoors.
        hide_from_athlete: If True, the event is hidden from the athlete's view.
        moving_time: Target duration in seconds.
        color: Hex color string (e.g. '#FF5733').
    """
    optional = {
        "name": name,
        "description": description,
        "indoor": indoor,
        "hide_from_athlete": hide_from_athlete,
        "moving_time": moving_time,
        "color": color,
    }
    body: dict = {k: v for k, v in optional.items() if v is not None}
    if date is not None:
        body["start_date_local"] = f"{date}T00:00:00"

    resp = await ctx.lifespan_context["client"].put(
        f"/athlete/{athlete_id}/events/{event_id}", json=body
    )
    resp.raise_for_status()
    return {"message": f"Event {event_id} updated.", "status": resp.status_code}


@mcp.tool(tags={"Calendar"})
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
    resp.raise_for_status()
    return {"message": f"Note '{name}' created.", "status": resp.status_code}



if __name__ == "__main__":
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport=transport, host="0.0.0.0", port=port)
