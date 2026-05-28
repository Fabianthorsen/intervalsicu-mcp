"""Intervals.icu MCP server — exposes training data as MCP tools."""

import os
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
from events import events
from gear import gear
from library import library
from wellness import wellness

load_dotenv()

API_KEY = os.environ["INTERVALS_API_KEY"]
GITHUB_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"]
GITHUB_CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
JWT_SIGNING_KEY = os.environ["JWT_SIGNING_KEY"]
ALLOWED_GITHUB_USERS = {u.lower() for u in os.environ.get("ALLOWED_GITHUB_USERS", "").split(",") if u}
BASE_URL = "https://intervals.icu/api/v1"


def _error_hook(response: httpx.Response) -> None:
    """Raise HTTPStatusError on all 4xx/5xx responses."""
    if response.status_code >= 400:
        response.raise_for_status()


@lifespan
async def client_lifespan(_: FastMCP) -> AsyncIterator[dict]:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        auth=("API_KEY", API_KEY),
        event_hooks={"response": [_error_hook]},
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
    - **Athletes** — profile data (FTP, weight, HR zones, timezone), list coaches and coached athletes
    - **Activities** — completed workouts with intervals, power, HR, pace and TSS; includes coaching tools
      (set evaluation ticks, post feedback) for coaches reviewing athlete workouts
    - **Wellness** — daily HRV, resting HR, sleep, CTL/ATL/TSB (fitness/fatigue/form)
    - **Gear** — bikes, shoes, components and maintenance reminders
    - **Calendar & Events** — planned workouts, notes, races, and rest days; create inline workouts or
      schedule from the library; get training plan
    - **Workout Library** — folders and structured workout definitions. list_workout_folders returns folders
      with workouts nested inside as 'children'.

    ## Common workflows
    - To review an athlete's week: use list_events + list_activities_between_dates
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
mcp.mount(events)
mcp.mount(gear)
mcp.mount(wellness)
mcp.mount(library)



if __name__ == "__main__":
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport=transport, host="0.0.0.0", port=port)
