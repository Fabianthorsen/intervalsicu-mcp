"""Intervals.icu MCP server — exposes training data as MCP tools."""

import os
from typing import AsyncIterator

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.auth import AuthContext
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.server.lifespan import lifespan

import client as _client
from client import HTTPErrorMiddleware, build_client
from activities import activities
from athletes import athletes
from chats import chats
from events import events
from gear import gear
from library import library
from wellness import wellness

load_dotenv()

GITHUB_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
GITHUB_CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
JWT_SIGNING_KEY = os.environ["JWT_SIGNING_KEY"]
ALLOWED_GITHUB_USERS = {u.lower() for u in os.environ.get("ALLOWED_GITHUB_USERS", "").split(",") if u}


@lifespan
async def client_lifespan(_: FastMCP) -> AsyncIterator[dict]:
    # Share the lifespan client with client.get_client's fallback global so
    # both transports resolve to the same instance.
    _client._global_client = build_client()
    try:
        yield {"client": _client._global_client}
    finally:
        await _client._global_client.aclose()
        _client._global_client = None


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
    - `athlete_id`: '0' is the authenticated user. For a coached athlete use their ID
      (e.g. 'i12345') — get IDs from list_coached_athletes.
    - Activity IDs look like 'i129230824'; event IDs are integers.
    - Dates are ISO-8601 strings (e.g. '2026-03-10').
    - Distances are metres, durations seconds, power watts.
    - Read tools take an `include` list of field groups and default to a headline set.
      Ask for more groups when you need them; 'ALL' is a raw passthrough and is large.
    - Subjective wellness scales (fatigue, soreness, stress, mood, motivation,
      sleepQuality) run 1 (best) to 4 (worst).

    ## Tool groups
    - **Athletes** — profile, plus per-sport thresholds and zones. FTP is per sport, not
      per athlete: get_athlete include=['ZONES'] for the numbers, get_sport_settings for
      full zone boundaries, update_sport_settings to change them.
    - **Activities** — completed sessions, intervals, best-effort curves, and coaching
      actions (evaluation ticks, feedback). search_activities finds a session when the
      date is unknown. get_activity_window_metrics gives NP/IF/TSS/decoupling for any
      time window, not just recorded intervals.
    - **Wellness** — HRV, resting HR, sleep, CTL/ATL/TSB, self-reported readiness and
      nutrition. update_wellness records any of it for a given day.
    - **Gear** — bikes, shoes, components, distance covered and maintenance reminders
    - **Calendar & Events** — planned workouts, notes and races; create inline or
      schedule from the library; training plan
    - **Workout Library** — folders and structured workouts. list_workout_folders nests
      workouts under each folder as 'children'.
    - **Chats** — the standing coach/athlete conversation. Separate from
      post_activity_message, which comments on one session. Sending is limited to
      one-to-one chats.

    ## Common workflows
    - Review an athlete's week: list_events + list_activities_between_dates
    - Check readiness: get_wellness with days=1 for today, 7 or 30 for a trend; include
      CTL_ATL_TSB for form and SUBJECTIVE for how they say they feel
    - Give feedback: set_coach_evaluation and/or post_activity_message
    - Compare halves of a ride: get_activity_window_metrics twice with different windows
    - Build a library: create_workout_folder, then create_workout_in_folder
    - Schedule from the library: list_workout_folders to find the workout id in
      'children', then schedule_workout

    ## Writing workouts
    Always populate `description`. create_workout's documentation carries the full
    format, including the Intervals.icu structured-interval syntax for Ride and Run and
    the prose-only convention for other sports. Follow it for schedule_workout and
    create_workout_in_folder too.

    ## Changing an athlete's numbers
    update_sport_settings affects future analysis only and is safe to correct.
    apply_sport_settings recalculates every past activity against the new zones — run it
    only on an explicit request, never as a follow-up to changing a threshold.
    """,
)

def check_github_user(ctx: AuthContext) -> bool:
    if ctx.token is None:
        return False
    return ctx.token.claims.get("login", "").lower() in ALLOWED_GITHUB_USERS


mcp.add_middleware(AuthMiddleware(auth=check_github_user))
mcp.add_middleware(HTTPErrorMiddleware())

mcp.mount(athletes)
mcp.mount(activities)
mcp.mount(events)
mcp.mount(gear)
mcp.mount(wellness)
mcp.mount(library)
mcp.mount(chats)



if __name__ == "__main__":
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport=transport, host="0.0.0.0", port=port)
