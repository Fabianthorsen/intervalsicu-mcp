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
