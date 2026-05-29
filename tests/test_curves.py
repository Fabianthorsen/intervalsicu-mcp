"""Unit tests for the curves module (ADR-0003: server-compute and sample).

Inputs mirror the shapes intervals.icu actually returns:
  - a single activity curve: parallel ``secs`` / ``values`` / ``watts`` arrays
  - the athlete-curves envelope: ``{"list": [<curve>, ...]}``
"""

import pytest

from curves import format_curve


def _activity_curve(secs, values, watts=None):
    """Build a single-activity curve payload (parallel arrays)."""
    curve = {"secs": list(secs), "values": list(values)}
    if watts is not None:
        curve["watts"] = list(watts)
    return curve


def _athlete_envelope(secs, watts, weight=None):
    """Build the athlete power-curves envelope: {"list": [<curve>]}."""
    entry = {"secs": list(secs), "watts": list(watts), "values": list(watts)}
    if weight is not None:
        entry["weight"] = weight
    return {"list": [entry], "activities": {}}


# All nine canonical durations, in seconds, as the API actually reports them.
ALL_SECS = [5, 15, 30, 60, 120, 300, 480, 1200, 3600]
ALL_VALS = [1100, 950, 850, 600, 480, 380, 350, 320, 290]


class TestFormatCurve:
    """Unit tests for curve formatting and sampling."""

    def test_default_durations_all_canonical_points(self):
        """When durations omitted, all 9 canonical points are returned."""
        result = format_curve(_activity_curve(ALL_SECS, ALL_VALS), metric="HR")

        assert set(result.keys()) == {
            "5s", "15s", "30s", "1m", "2m", "5m", "8m", "20m", "60m",
        }

    def test_explicit_durations_subset(self):
        """Explicit durations parameter returns only those points."""
        result = format_curve(
            _activity_curve([5, 60, 300, 1200, 3600], [1100, 600, 380, 320, 290]),
            metric="HR",
            requested_durations=["1m", "5m", "60m"],
        )

        assert set(result.keys()) == {"1m", "5m", "60m"}
        assert result["1m"] == 600
        assert result["5m"] == 380
        assert result["60m"] == 290

    def test_power_metric_returns_watts_and_wkg(self):
        """Power metric returns {w, wkg} per duration, using the watts array."""
        result = format_curve(
            _activity_curve([300, 1200], [380, 320], watts=[380, 320]),
            metric="POWER",
            requested_durations=["5m", "20m"],
            weight=72.0,
        )

        assert result["5m"]["w"] == 380
        assert result["5m"]["wkg"] == pytest.approx(380 / 72.0, abs=0.01)
        assert result["20m"]["w"] == 320
        assert result["20m"]["wkg"] == pytest.approx(320 / 72.0, abs=0.01)

    def test_power_without_weight_omits_wkg(self):
        """With no usable weight, power returns raw watts and no fabricated W/kg."""
        result = format_curve(
            _activity_curve([300], [380], watts=[380]),
            metric="POWER",
            requested_durations=["5m"],
            weight=None,
        )

        assert result["5m"] == {"w": 380}
        assert "wkg" not in result["5m"]

    def test_athlete_envelope_is_unwrapped(self):
        """The {"list": [...]} athlete envelope is unwrapped to its curve."""
        payload = _athlete_envelope([300, 1200], [380, 320], weight=90.0)

        result = format_curve(
            payload, metric="POWER", requested_durations=["5m", "20m"], weight=90.0
        )

        assert result["5m"]["w"] == 380
        assert result["20m"]["w"] == 320

    def test_hr_metric_returns_bpm(self):
        """HR metric returns bare bpm values from the values array."""
        result = format_curve(
            _activity_curve([300, 1200], [160, 145]),
            metric="HR",
            requested_durations=["5m", "20m"],
        )

        assert result["5m"] == 160
        assert result["20m"] == 145
        assert not isinstance(result["5m"], dict)

    def test_pace_metric_returns_pace(self):
        """Pace metric returns bare pace values."""
        result = format_curve(
            _activity_curve([300, 1200], [4.5, 4.2]),
            metric="PACE",
            requested_durations=["5m", "20m"],
        )

        assert result["5m"] == 4.5
        assert result["20m"] == 4.2

    def test_missing_durations_skipped(self):
        """Durations not present in the server curve are skipped."""
        result = format_curve(
            _activity_curve([300], [380]),  # only 5m present
            metric="HR",
            requested_durations=["5m", "20m"],
        )

        assert "5m" in result
        assert "20m" not in result

    def test_unknown_durations_skipped(self):
        """Unknown duration labels are silently skipped."""
        result = format_curve(
            _activity_curve([300, 1200], [380, 320]),
            metric="HR",
            requested_durations=["5m", "invalid_duration", "20m"],
        )

        assert set(result.keys()) == {"5m", "20m"}

    def test_empty_payload_returns_empty(self):
        """A payload with no recognisable curve data yields an empty result."""
        assert format_curve({}, metric="POWER", weight=70) == {}
        assert format_curve({"list": []}, metric="POWER", weight=70) == {}
