"""Unit tests for correctness fixes."""

from datetime import date, timedelta
import inspect

from activities import list_activities_between_dates
from library import update_workout, delete_workout


def test_list_activities_defaults_not_mutable():
    """Default args should not be mutable date objects (should be None, resolved at call time)."""
    sig = inspect.signature(list_activities_between_dates)

    from_date_default = sig.parameters["from_date"].default
    to_date_default = sig.parameters["to_date"].default

    # Defaults should be None, not date() objects (which are mutable/time-dependent)
    assert from_date_default is None, f"from_date default should be None, got {from_date_default}"
    assert to_date_default is None, f"to_date default should be None, got {to_date_default}"


def test_delete_workout_id_type_consistency():
    """delete_workout and update_workout should use same type for workout_id."""
    update_sig = inspect.signature(update_workout)
    delete_sig = inspect.signature(delete_workout)

    update_id_type = update_sig.parameters["workout_id"].annotation
    delete_id_type = delete_sig.parameters["workout_id"].annotation

    # Both should be int
    assert update_id_type == int, f"update_workout id should be int, got {update_id_type}"
    assert delete_id_type == int, f"delete_workout id should be int, got {delete_id_type}"
