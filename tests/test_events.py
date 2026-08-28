"""Unit tests for events module — verify structure and tool definitions."""

import pytest

from events import (
    BATCH_CATEGORIES,
    NOTE_CATEGORIES,
    _event_body,
    create_events,
    create_note,
    create_race,
    create_workout,
    delete_event,
    get_event,
    get_training_plan,
    list_events,
    schedule_workout,
    update_event,
)


def test_create_note_is_callable():
    """create_note function exists and is callable."""
    assert callable(create_note)


def test_create_workout_is_callable():
    """create_workout function exists and is callable."""
    assert callable(create_workout)


def test_delete_event_is_callable():
    """delete_event function exists and is callable."""
    assert callable(delete_event)


def test_get_event_is_callable():
    """get_event function exists and is callable."""
    assert callable(get_event)


def test_get_training_plan_is_callable():
    """get_training_plan function exists and is callable."""
    assert callable(get_training_plan)


def test_list_events_is_callable():
    """list_events function exists and is callable."""
    assert callable(list_events)


def test_schedule_workout_is_callable():
    """schedule_workout function exists and is callable."""
    assert callable(schedule_workout)


def test_update_event_is_callable():
    """update_event function exists and is callable."""
    assert callable(update_event)


def test_create_race_is_callable():
    """create_race function exists and is callable."""
    assert callable(create_race)


def test_create_events_is_callable():
    """create_events function exists and is callable."""
    assert callable(create_events)


def test_event_body_defaults_to_workout():
    body = _event_body({"date": "2026-03-10", "name": "Endurance"})
    assert body["category"] == "WORKOUT"
    assert body["start_date_local"] == "2026-03-10T00:00:00"
    assert body["name"] == "Endurance"


def test_event_body_passes_through_optional_fields():
    body = _event_body(
        {
            "date": "2026-03-10",
            "name": "Padel",
            "description": "Main set\n- 90m 70-80% LTHR",
            "type": "Padel",
            "moving_time": 5400,
            "color": "#FF5733",
            "tags": ["match"],
        }
    )
    assert body["type"] == "Padel"
    assert body["moving_time"] == 5400
    assert body["color"] == "#FF5733"
    assert body["tags"] == ["match"]


def test_event_body_omits_unset_fields():
    body = _event_body({"date": "2026-03-10", "name": "Rest", "category": "NOTE"})
    assert "moving_time" not in body
    assert "color" not in body
    assert "end_date_local" not in body


def test_event_body_passes_through_for_week():
    """A week note is how a block's weeks get labelled, so the batch path must carry it."""
    body = _event_body(
        {"date": "2026-03-10", "name": "Build 2 — 9h", "category": "NOTE", "for_week": True}
    )
    assert body["for_week"] is True


def test_event_body_keeps_for_week_false():
    """False is a meaningful value here, not an absent one — it must not be pruned."""
    body = _event_body(
        {"date": "2026-03-10", "name": "Day note", "category": "NOTE", "for_week": False}
    )
    assert body["for_week"] is False


def test_event_body_omits_for_week_when_unset():
    body = _event_body({"date": "2026-03-10", "name": "Day note", "category": "NOTE"})
    assert "for_week" not in body


def test_event_body_maps_end_date():
    body = _event_body(
        {"date": "2026-03-10", "name": "Alps", "category": "HOLIDAY", "end_date": "2026-03-17"}
    )
    assert body["end_date_local"] == "2026-03-17T00:00:00"


def test_event_body_normalises_category_case():
    assert _event_body({"date": "2026-03-10", "name": "A race", "category": "race_a"})["category"] == "RACE_A"


def test_event_body_rejects_unknown_category():
    with pytest.raises(ValueError, match="category must be one of"):
        _event_body({"date": "2026-03-10", "name": "x", "category": "SET_EFTP"})


@pytest.mark.parametrize("spec", [{"name": "x"}, {"date": "2026-03-10"}, {}])
def test_event_body_requires_date_and_name(spec):
    with pytest.raises(ValueError, match="missing required field"):
        _event_body(spec)


def test_note_categories_cover_the_day_describing_set():
    assert set(NOTE_CATEGORIES) == {"NOTE", "HOLIDAY", "SICK", "INJURED", "SEASON_START"}


def test_batch_categories_include_workout_races_and_notes():
    assert "WORKOUT" in BATCH_CATEGORIES
    assert {"RACE_A", "RACE_B", "RACE_C"} <= set(BATCH_CATEGORIES)
    assert set(NOTE_CATEGORIES) <= set(BATCH_CATEGORIES)
    assert "SET_EFTP" not in BATCH_CATEGORIES
