"""Unit tests for interval shaping and editing.

Payloads mirror the shape /activity/{id}/intervals really returns: a wrapper
holding icu_intervals and icu_groups, with every metric present as a key even
when it is null.
"""

import pytest

from intervals import (
    IntervalError,
    apply_edits,
    extract_intervals,
    find_interval,
    shape_intervals,
)
from intervals import find_section, plan_cuts
from windows import WindowError, resolve_section

ONE_HZ = list(range(0, 3600))
SMART = list(range(0, 3600, 4))


def _interval(**overrides) -> dict:
    base = {
        "id": 6524075,
        "type": "WORK",
        "label": None,
        "group_id": "580s@218w89rpm",
        "start_index": 13,
        "end_index": 593,
        "start_time": 13,
        "end_time": 593,
        "elapsed_time": 580,
        "moving_time": 580,
        "distance": 5751.79,
        "average_watts": 218,
        "weighted_average_watts": 218,
        "max_watts": 339,
        "intensity": 76,
        "training_load": 9.4,
        "average_heartrate": 125,
        "average_cadence": 89,
        "min_lactate": None,
        "average_smo2": None,
        "total_elevation_gain": 24,
    }
    base.update(overrides)
    return base


PAYLOAD = {
    "id": "i179293086",
    "icu_intervals": [
        _interval(),
        _interval(id=9534209, type="RECOVERY", group_id=None, average_watts=211),
    ],
    "icu_groups": [{"id": "580s@218w89rpm", "count": 2, "average_watts": 218}],
}


def test_headline_drops_the_long_tail_of_metrics() -> None:
    shaped = shape_intervals(PAYLOAD, ["HEADLINE"])
    first = shaped["intervals"][0]

    assert first["id"] == 6524075
    assert first["type"] == "WORK"
    assert first["average_watts"] == 218
    # Present in the raw payload, not in HEADLINE.
    assert "max_watts" not in first
    assert "total_elevation_gain" not in first


def test_nulls_are_pruned_not_reported_as_data() -> None:
    """A ride without lactate or SmO2 should not carry those keys at all."""
    shaped = shape_intervals(PAYLOAD, ["ALL"])
    assert "min_lactate" not in shaped["intervals"][0]
    assert "average_smo2" not in shaped["intervals"][0]


def test_all_is_a_raw_passthrough() -> None:
    shaped = shape_intervals(PAYLOAD, ["ALL"])
    assert shaped["intervals"][0]["total_elevation_gain"] == 24


def test_timing_group_exposes_the_seconds_an_edit_is_addressed_by() -> None:
    shaped = shape_intervals(PAYLOAD, ["TIMING"])
    first = shaped["intervals"][0]
    assert first["start_time"] == 13 and first["end_time"] == 593
    assert "average_watts" not in first


def test_rep_groups_survive_shaping() -> None:
    """icu_groups is what answers '4x5min or 4 unrelated efforts'."""
    shaped = shape_intervals(PAYLOAD, ["HEADLINE"])
    assert shaped["groups"][0]["count"] == 2
    assert shaped["activity_id"] == "i179293086"


def test_empty_activity_shapes_to_empty_lists() -> None:
    shaped = shape_intervals({"id": "i1"}, ["HEADLINE"])
    assert shaped == {"activity_id": "i1", "intervals": [], "groups": []}


def test_extract_accepts_a_bare_list() -> None:
    assert extract_intervals([{"id": 1}]) == [{"id": 1}]


def test_missing_interval_error_names_the_ids_that_exist() -> None:
    intervals = extract_intervals(PAYLOAD)
    with pytest.raises(IntervalError) as exc:
        find_interval(intervals, 999)

    assert "6524075" in str(exc.value) and "9534209" in str(exc.value)


def test_edit_carries_every_untouched_field_through() -> None:
    """The PUT replaces the interval, so a sparse patch would lose data."""
    edited = apply_edits(_interval(), label="threshold rep 1")

    assert edited["label"] == "threshold rep 1"
    assert edited["average_watts"] == 218
    assert edited["start_index"] == 13
    assert edited["type"] == "WORK"


def test_edit_does_not_mutate_the_server_object() -> None:
    original = _interval()
    apply_edits(original, label="renamed")
    assert original["label"] is None


def test_empty_label_clears_rather_than_being_ignored() -> None:
    edited = apply_edits(_interval(label="old"), label="")
    assert edited["label"] == ""


def test_type_can_be_changed_without_touching_the_label() -> None:
    edited = apply_edits(_interval(label="keep me"), interval_type="RECOVERY")
    assert edited["type"] == "RECOVERY"
    assert edited["label"] == "keep me"


def test_an_edit_that_changes_nothing_is_rejected() -> None:
    with pytest.raises(IntervalError):
        apply_edits(_interval())


def test_a_sections_duration_is_exactly_what_was_asked_for() -> None:
    """Verified against i179293086: indices 13-593 are the 580s interval 13-593."""
    start, end = resolve_section(ONE_HZ, 1200, 2400)
    assert (start, end) == (1200, 2400)
    assert end - start == 1200


def test_consecutive_sections_tile_without_gap_or_overlap() -> None:
    """intervals.icu's own intervals share a boundary; carved ones must too."""
    _, first_end = resolve_section(ONE_HZ, 1200, 2400)
    second_start, _ = resolve_section(ONE_HZ, 2400, 3000)
    assert first_end == second_start


def test_cut_points_resolve_through_the_time_stream() -> None:
    """Smart recording: 1200s is index 300, not index 1200."""
    assert resolve_section(SMART, 1200, 2400) == (300, 600)


def test_a_section_running_to_the_end_reaches_the_final_sample() -> None:
    """time_stream[-1] is 3599 but the last boundary is 3600, or a sliver is left."""
    assert resolve_section(ONE_HZ, 1200, 3599) == (1200, len(ONE_HZ))


def test_a_section_may_span_the_whole_recording() -> None:
    assert resolve_section(ONE_HZ, 0, 3599) == (0, len(ONE_HZ))


def test_a_section_past_the_end_is_refused() -> None:
    with pytest.raises(WindowError):
        resolve_section(ONE_HZ, 1200, 7200)


def test_an_inverted_range_is_refused_before_any_cut() -> None:
    with pytest.raises(WindowError):
        resolve_section(ONE_HZ, 2400, 1200)


def test_cutting_without_a_time_stream_says_what_still_works() -> None:
    with pytest.raises(WindowError) as exc:
        resolve_section([], 600, 1200)
    assert "relabelled by id" in str(exc.value)


def test_a_section_inside_one_interval_needs_both_ends_cut() -> None:
    intervals = extract_intervals(PAYLOAD)  # boundaries at 13 and 593
    assert plan_cuts(intervals, 100, 400) == [100, 400]


def test_a_cut_is_skipped_where_a_boundary_already_exists() -> None:
    """Splitting on an existing boundary would be a no-op or an empty half."""
    intervals = extract_intervals(PAYLOAD)
    assert plan_cuts(intervals, 13, 400) == [400]
    assert plan_cuts(intervals, 13, 593) == []


def test_an_inverted_section_is_refused() -> None:
    with pytest.raises(IntervalError):
        plan_cuts(extract_intervals(PAYLOAD), 600, 200)


def test_the_carved_section_is_found_by_its_bounds() -> None:
    section = find_section(extract_intervals(PAYLOAD), 13, 593)
    assert section["id"] == 6524075


def test_an_unexpected_cut_result_is_not_labelled_blind() -> None:
    """If the server split elsewhere, naming the wrong interval is worse than failing."""
    with pytest.raises(IntervalError) as exc:
        find_section(extract_intervals(PAYLOAD), 100, 400)
    assert "nothing was labelled" in str(exc.value)
