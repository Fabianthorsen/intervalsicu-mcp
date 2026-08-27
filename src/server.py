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

# GitHub OAuth is only used by the remote (HTTP) deployment. A local stdio run
# is already scoped to the person's own machine and API key, so requiring these
# would break `uv run python src/server.py` for anyone who just cloned the repo.
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://intervalsicu-mcp.fly.dev")
ALLOWED_GITHUB_USERS = {u.lower() for u in os.environ.get("ALLOWED_GITHUB_USERS", "").split(",") if u}
AUTH_ENABLED = bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and JWT_SIGNING_KEY)


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


auth = (
    GitHubProvider(
        client_id=GITHUB_CLIENT_ID,
        client_secret=GITHUB_CLIENT_SECRET,
        base_url=PUBLIC_BASE_URL,
        jwt_signing_key=JWT_SIGNING_KEY,
    )
    if AUTH_ENABLED
    else None
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
      time window, not just recorded intervals. An activity's intervals can be
      edited: create_activity_interval carves a named section out of an
      unstructured ride, update_activity_interval names a detected one. Editing
      makes intervals.icu stop auto-detecting intervals for that activity, and
      is visible to the athlete — say so first. update_activity corrects an
      activity's name, description or sport type; type is what decides which
      sport settings its load is computed against.
    - **Wellness** — HRV, resting HR, sleep, CTL/ATL/TSB, self-reported readiness and
      nutrition. update_wellness records any of it for a given day.
    - **Gear** — bikes, shoes, components, distance covered and maintenance reminders
    - **Calendar & Events** — planned workouts, notes and races; create inline or
      schedule from the library; training plan. create_race puts an A/B/C race on
      the calendar, create_note covers holidays and spells of illness or injury,
      and create_events lays out a whole week in one call.
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
    - Plan a block: create_events with the whole week's entries — workouts, races
      and rest notes in one call — rather than one create_workout per day

    ## Writing workouts
    Always populate `description`. create_workout's documentation carries the full
    format, including the Intervals.icu structured-interval syntax and the rules on
    which sports need a spec. Follow it for schedule_workout, create_workout_in_folder
    and create_events too.

    Planning an unstructured sport (Padel, Football, Tennis, Climbing and similar):
    intervals.icu derives planned load from the description's structured steps, so a
    prose-only session plans zero load and never reaches the fitness chart. Give it a
    minimal spec instead — a duration at an %LTHR range, calibrated from what previous
    sessions of that type actually cost. Do not set load_target by hand to work around
    a missing spec. This needs the sport's settings group to have an LTHR; if the
    planned load comes back as zero, check get_sport_settings.

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


if AUTH_ENABLED:
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
    if transport != "stdio" and not AUTH_ENABLED:
        # Local stdio is fine unauthenticated; a network-exposed transport is not.
        # Failing loudly here beats a deploy that silently drops its allowlist.
        raise SystemExit(
            f"Refusing to serve transport '{transport}' without auth: set "
            "GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET and JWT_SIGNING_KEY "
            "(and ALLOWED_GITHUB_USERS)."
        )
    mcp.run(transport=transport, host="0.0.0.0", port=port)
