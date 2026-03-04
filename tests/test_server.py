"""Integration tests for the intervals.icu MCP server tools.

Requires INTERVALS_API_KEY in .env.
Run with: uv run pytest tests/
"""

from datetime import date, timedelta

import pytest
from dotenv import load_dotenv

load_dotenv()

from server import (  # noqa: E402
    create_note,
    get_activity_intervals,
    get_athlete,
    get_event,
    get_training_plan,
    get_wellness,
    list_activities_between_dates,
    list_athlete_events,
    list_coached_athletes,
    list_events,
    list_gear,
    set_coach_evaluation,
)


async def test_get_athlete():
    result = await get_athlete()
    assert isinstance(result, dict)
    assert "id" in result
    assert "name" in result


async def test_list_activities():
    result = await list_activities_between_dates(
        from_date=date.today() - timedelta(days=14),
        to_date=date.today(),
    )
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "type" in result[0]
        assert "start_date_local" in result[0]


async def test_get_wellness():
    result = await get_wellness(days=7)
    assert isinstance(result, list)
    assert len(result) == 7
    day = result[0]
    assert len(day) == 3  # id, load, health
    assert len(day["load"]) == 3  # ctl, atl, rampRate
    assert len(day["health"]) == 4  # hrv, restingHR, sleepScore, sleeptSecs
    assert "id" in day
    assert "ctl" in day["load"]
    assert "atl" in day["load"]


async def test_list_gear():
    result = await list_gear()
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "name" in result[0]


@pytest.fixture
async def recent_activity_id():
    activities = await list_activities_between_dates(
        from_date=date.today() - timedelta(days=14),
        to_date=date.today(),
    )
    if not activities:
        pytest.skip("no recent activities")
    return activities[0]["id"]


async def test_get_activity_intervals(recent_activity_id):
    result = await get_activity_intervals(recent_activity_id)
    assert isinstance(result, dict)
    assert "icu_intervals" in result


# --- Events ---


async def test_list_events():
    result = await list_events(days_ahead=14, days_back=7)
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "name" in result[0]
        assert "start_date_local" in result[0]


async def test_list_events_workouts_only():
    result = await list_events(days_ahead=14, days_back=7, category="WORKOUT")
    assert isinstance(result, list)
    for event in result:
        assert event.get("category") == "WORKOUT"


@pytest.fixture
async def recent_event_id():
    events = await list_events(days_ahead=0, days_back=14, category="WORKOUT")
    if not events:
        pytest.skip("no recent workout events")
    return events[0]["id"]


async def test_get_event(recent_event_id):
    result = await get_event(recent_event_id)
    assert isinstance(result, dict)
    assert result["id"] == recent_event_id


async def test_get_training_plan():
    result = await get_training_plan()
    assert isinstance(result, dict)


# --- Coaching: athletes ---


async def test_list_coached_athletes():
    result = await list_coached_athletes()
    assert isinstance(result, list)


@pytest.fixture
async def coached_athlete_id():
    athletes = await list_coached_athletes()
    if not athletes:
        pytest.skip("no coached athletes")
    return athletes[0]["athlete_id"]


async def test_list_athlete_events(coached_athlete_id):
    result = await list_athlete_events(coached_athlete_id, days_ahead=14, days_back=7)
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "start_date_local" in result[0]


async def test_list_athlete_activities(coached_athlete_id):
    result = await list_activities_between_dates(
        athlete_id=coached_athlete_id,
        from_date=date.today() - timedelta(days=14),
        to_date=date.today(),
    )
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "start_date_local" in result[0]
