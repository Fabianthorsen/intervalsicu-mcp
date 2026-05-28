"""Unit tests for events module — verify structure and tool definitions."""

import pytest

from events import (
    create_note,
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
