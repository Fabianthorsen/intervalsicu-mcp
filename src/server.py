"""Intervals.icu MCP server — exposes training data as MCP tools."""

import os
from datetime import date, timedelta
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

API_KEY = os.environ["INTERVALS_API_KEY"]
BASE_URL = "https://intervals.icu/api/v1"

mcp = FastMCP("intervals-icu")


async def _get(path: str, **params):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}{path}",
            auth=("API_KEY", API_KEY),
            params={k: v for k, v in params.items() if v is not None},
        )
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}{path}",
            auth=("API_KEY", API_KEY),
            json=body,
        )
        r.raise_for_status()
        return r.json()


async def _delete(path: str):
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{BASE_URL}{path}",
            auth=("API_KEY", API_KEY),
        )
        r.raise_for_status()


async def _put(path: str, body: dict):
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{BASE_URL}{path}",
            auth=("API_KEY", API_KEY),
            json=body,
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def get_athlete(athlete_id: str = "0") -> dict:
    """Get an athlete's profile (name, weight, FTP, resting HR, timezone, gear).

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    return await _get(f"/athlete/{athlete_id}")


@mcp.tool()
async def list_activities(days: int = 14, limit: int = 10) -> list:
    """List recent activities in descending date order.

    Args:
        days: How many days back to look (default 14).
        limit: Maximum number of activities to return (default 10).
    """
    oldest = (date.today() - timedelta(days=days)).isoformat()
    return await _get(f"/athlete/0/activities", oldest=oldest, limit=limit)


@mcp.tool()
async def get_wellness(days: int = 7, athlete_id: str = "0") -> list:
    """Get daily wellness records including fitness (CTL), fatigue (ATL), form (TSB),
    HRV, resting HR, sleep duration and score, weight, and other health metrics.

    Args:
        days: How many days of history to return (default 7).
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    oldest = (date.today() - timedelta(days=days)).isoformat()
    return await _get(f"/athlete/{athlete_id}/wellness", oldest=oldest)


@mcp.tool()
async def list_gear() -> list:
    """List all gear (bikes, shoes, components) with total distance, time, activity
    count, and any maintenance reminders."""
    return await _get(f"/athlete/0/gear")


@mcp.tool()
async def get_activity_intervals(activity_id: str) -> dict:
    """Get the analysed intervals for a specific activity, including power, HR,
    pace, TSS, and other metrics per interval.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    return await _get(f"/activity/{activity_id}/intervals")


@mcp.tool()
async def list_events(days_ahead: int = 7, days_back: int = 0, category: str | None = None) -> list:
    """List planned events (workouts, notes, races) on the athlete's calendar.

    Args:
        days_ahead: How many days into the future to return (default 7).
        days_back: How many days into the past to include (default 0).
        category: Comma-separated event categories to filter for, e.g. 'WORKOUT,NOTE'.
    """
    oldest = (date.today() - timedelta(days=days_back)).isoformat()
    newest = (date.today() + timedelta(days=days_ahead)).isoformat()
    return await _get(
        f"/athlete/0/events",
        oldest=oldest,
        newest=newest,
        category=category,
    )


@mcp.tool()
async def get_event(event_id: int, athlete_id: str = "0") -> dict:
    """Get a single planned event (workout, note, race) by ID.

    Args:
        event_id: The event ID.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    return await _get(f"/athlete/{athlete_id}/events/{event_id}")


@mcp.tool()
async def get_training_plan() -> dict:
    """Get the athlete's current training plan."""
    return await _get(f"/athlete/0/training-plan")


@mcp.tool()
async def list_workouts() -> list:
    """List all workouts in the athlete's workout library."""
    return await _get(f"/athlete/0/workouts")


@mcp.tool()
async def get_activity_streams(activity_id: str) -> dict:
    """Get the raw time-series data streams for an activity (power, HR, speed,
    cadence, altitude, etc.) at one-second resolution.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    return await _get(f"/activity/{activity_id}/streams")


# --- Coaching ---


@mcp.tool()
async def list_coached_athletes() -> list:
    """List all athletes the current user is coaching, with a recent summary of
    their training load, fitness, and activity data."""
    return await _get(f"/athlete/0/athlete-summary")


@mcp.tool()
async def list_athlete_activities(athlete_id: str, days: int = 14, limit: int = 10) -> list:
    """List recent activities for a coached athlete in descending date order.

    Args:
        athlete_id: The athlete's ID (e.g. 'i12345'). Get IDs from list_coached_athletes.
        days: How many days back to look (default 14).
        limit: Maximum number of activities to return (default 10).
    """
    oldest = (date.today() - timedelta(days=days)).isoformat()
    return await _get(f"/athlete/{athlete_id}/activities", oldest=oldest, limit=limit)


@mcp.tool()
async def list_athlete_events(
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
    return await _get(
        f"/athlete/{athlete_id}/events",
        oldest=oldest,
        newest=newest,
        category=category,
    )


@mcp.tool()
async def update_athlete_event(
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
    return await _put(
        f"/athlete/{athlete_id}/events/{event_id}",
        {k: v for k, v in body.items() if v is not None},
    )


@mcp.tool()
async def delete_event(event_id: int, athlete_id: str = "0") -> None:
    """Delete an event (planned workout, note, race etc.) from an athlete's calendar.

    Args:
        event_id: The event ID to delete.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    await _delete(f"/athlete/{athlete_id}/events/{event_id}")


@mcp.tool()
async def create_note(
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
    return await _post(f"/athlete/{athlete_id}/events", body)


CoachTick = Literal[1, 2, 3, 4, 5]


@mcp.tool()
async def set_coach_evaluation(activity_id: str, evaluation: CoachTick) -> dict:
    """Set the coach's evaluation tick on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        evaluation: 1 = WTF, 2 = POOR, 3 = SEEN, 4 = GOOD, 5 = AMAZING.
    """
    return await _put(f"/activity/{activity_id}", {"coach_tick": evaluation})


@mcp.tool()
async def post_activity_message(activity_id: str, content: str) -> dict:
    """Post a coaching message or feedback comment on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        content: The message text to post.
    """
    return await _post(f"/activity/{activity_id}/messages", {"content": content})


if __name__ == "__main__":
    mcp.run()
