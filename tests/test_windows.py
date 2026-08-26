"""Unit tests for window resolution and metric shaping.

The point of resolving through the time stream rather than by arithmetic is
that index only equals elapsed second on an unpaused 1Hz recording. These
tests cover the cases where that assumption breaks.
"""

import pytest

from windows import (
    WindowError,
    extract_time_stream,
    format_window_metrics,
    resolve_window,
)

# A clean 1Hz recording: index == second.
ONE_HZ = list(range(0, 3600))

# Smart recording at roughly 4s intervals: index is a quarter of the second.
SMART = list(range(0, 3600, 4))

# A ride paused for 10 minutes at the 30 minute mark: elapsed time jumps.
PAUSED = list(range(0, 1800)) + list(range(2400, 3600))


def test_one_hz_window_maps_to_matching_indices() -> None:
    assert resolve_window(ONE_HZ, 600, 1200) == (600, 1200)


def test_smart_recording_does_not_use_seconds_as_indices() -> None:
    """The whole reason for the time stream: naive arithmetic would be 4x off."""
    start, end = resolve_window(SMART, 600, 1200)
    assert (start, end) == (150, 300)
    assert SMART[start] == 600 and SMART[end] == 1200


def test_paused_activity_skips_the_gap() -> None:
    """No sample exists between 1800s and 2400s, so the window starts after it."""
    start, end = resolve_window(PAUSED, 2000, 2600)
    assert PAUSED[start] == 2400
    assert PAUSED[end] == 2600


def test_window_never_extends_past_what_was_asked_for() -> None:
    """end_index is the last sample at or before end_seconds, not the next one."""
    _, end = resolve_window(SMART, 0, 1001)
    assert SMART[end] == 1000


def test_start_snaps_forward_not_backward() -> None:
    start, _ = resolve_window(SMART, 999, 2000)
    assert SMART[start] == 1000


def test_inverted_window_is_rejected() -> None:
    with pytest.raises(WindowError, match="must be greater than"):
        resolve_window(ONE_HZ, 1200, 600)


def test_zero_length_window_is_rejected() -> None:
    with pytest.raises(WindowError, match="must be greater than"):
        resolve_window(ONE_HZ, 600, 600)


def test_start_past_end_of_activity_reports_the_duration() -> None:
    with pytest.raises(WindowError, match="3599"):
        resolve_window(ONE_HZ, 5000, 6000)


def test_missing_time_stream_suggests_the_alternative() -> None:
    with pytest.raises(WindowError, match="get_activity_intervals"):
        resolve_window([], 0, 600)


def test_window_covering_too_few_samples_is_rejected() -> None:
    with pytest.raises(WindowError, match="fewer than two samples"):
        resolve_window(SMART, 100, 102)


def test_end_beyond_the_recording_clamps_to_the_last_sample() -> None:
    _, end = resolve_window(ONE_HZ, 3000, 99999)
    assert end == len(ONE_HZ) - 1


class TestExtractTimeStream:
    def test_reads_the_streams_response_shape(self) -> None:
        payload = [
            {"type": "watts", "data": [200, 210, 220]},
            {"type": "time", "data": [0, 1, 2]},
        ]
        assert extract_time_stream(payload) == [0, 1, 2]

    def test_falls_back_to_the_name_field(self) -> None:
        assert extract_time_stream([{"name": "time", "data": [0, 4, 8]}]) == [0, 4, 8]

    def test_accepts_a_bare_array(self) -> None:
        assert extract_time_stream([0, 1, 2]) == [0, 1, 2]

    def test_missing_time_stream_yields_empty(self) -> None:
        assert extract_time_stream([{"type": "watts", "data": [1, 2]}]) == []

    def test_tolerates_unexpected_payloads(self) -> None:
        assert extract_time_stream(None) == []
        assert extract_time_stream({}) == []
        assert extract_time_stream("nope") == []

    def test_drops_null_samples(self) -> None:
        assert extract_time_stream([{"type": "time", "data": [0, None, 2]}]) == [0, 2]


class TestFormatWindowMetrics:
    # Shape taken from the Interval schema returned by interval-stats.
    INTERVAL = {
        "average_watts": 240.0,
        "weighted_average_watts": 265.0,
        "max_watts": 780,
        "average_heartrate": 154.2,
        "average_cadence": 88.0,
        "decoupling": 4.7,
        "intensity": 0.93,
        "training_load": 68,
        "elapsed_time": 1200,
        "moving_time": 1195,
        "distance": 11200.0,
        # Not reported:
        "wbal_start": 26800,
        "zone": 4,
        "segment_effort_ids": [],
    }

    def test_renames_intervalsicu_terms_to_what_they_mean(self) -> None:
        m = format_window_metrics(self.INTERVAL)
        assert m["normalized_power_w"] == 265.0
        assert m["intensity_factor"] == 0.93
        assert m["tss"] == 68

    def test_derives_variability_index(self) -> None:
        m = format_window_metrics(self.INTERVAL)
        assert m["variability_index"] == round(265.0 / 240.0, 3)

    def test_omits_fields_the_coach_did_not_ask_for(self) -> None:
        m = format_window_metrics(self.INTERVAL)
        assert "wbal_start" not in m
        assert "segment_effort_ids" not in m

    def test_no_variability_index_without_power(self) -> None:
        m = format_window_metrics({"average_heartrate": 150})
        assert "variability_index" not in m
        assert m["avg_hr_bpm"] == 150

    def test_zero_average_power_does_not_divide_by_zero(self) -> None:
        m = format_window_metrics({"average_watts": 0, "weighted_average_watts": 0})
        assert "variability_index" not in m

    def test_nulls_are_omitted_rather_than_reported(self) -> None:
        m = format_window_metrics({"average_watts": 200, "average_cadence": None})
        assert "avg_cadence_rpm" not in m

    def test_tolerates_unexpected_payload(self) -> None:
        assert format_window_metrics(None) == {}
