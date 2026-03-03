"""Integration tests for the intervals.icu MCP server tools.

Requires INTERVALS_API_KEY and INTERVALS_ATHLETE_ID in .env.
Run with: uv run pytest tests/
"""

import pytest
from dotenv import load_dotenv

load_dotenv()

from server import (  # noqa: E402
    create_note,
    delete_event,
    get_activity_intervals,
    get_athlete,
    get_event,
    get_training_plan,
    get_wellness,
    list_activities,
    list_athlete_activities,
    list_athlete_events,
    list_coached_athletes,
    list_events,
    list_gear,
    list_workouts,
    set_coach_evaluation,
)


async def test_get_athlete():
    result = await get_athlete()
    assert isinstance(result, dict)
    assert "id" in result
    assert "name" in result


async def test_list_activities():
    result = await list_activities(days=14, limit=3)
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "type" in result[0]
        assert "start_date_local" in result[0]


async def test_get_wellness():
    result = await get_wellness(days=7)
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]  # date string e.g. "2026-02-24"
        assert "ctl" in result[0]
        assert "atl" in result[0]


async def test_list_gear():
    result = await list_gear()
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "name" in result[0]


@pytest.fixture
async def recent_activity_id():
    activities = await list_activities(days=14, limit=1)
    if not activities:
        pytest.skip("no recent activities")
    return activities[0]["id"]


async def test_get_activity_intervals(recent_activity_id):
    result = await get_activity_intervals(recent_activity_id)
    assert isinstance(result, dict)
    assert "icu_intervals" in result


# --- Coaching ---


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


async def test_list_workouts():
    result = await list_workouts()
    assert isinstance(result, list)


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
    result = await list_athlete_activities(coached_athlete_id, days=14, limit=3)
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "start_date_local" in result[0]


async def test_create_note():
    result = await create_note(
        date="2026-03-15",
        name="Test trip note",
        description="Travelling to Bergen.",
        end_date="2026-03-17",
    )
    try:
        assert isinstance(result, dict)
        assert result.get("category") == "NOTE"
        assert result.get("name") == "Test trip note"
    finally:
        await delete_event(result["id"])


async def test_set_coach_evaluation(recent_activity_id):
    original = await set_coach_evaluation(recent_activity_id, 5)
    prev_tick = original.get("coach_tick")
    try:
        assert original.get("coach_tick") == 5
    finally:
        if prev_tick != 5:
            await set_coach_evaluation(recent_activity_id, prev_tick)
