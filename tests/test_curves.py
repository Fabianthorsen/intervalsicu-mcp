"""Unit tests for the curves module (ADR-0003: server-compute and sample)."""

import pytest

from curves import format_curve


class TestFormatCurve:
    """Unit tests for curve formatting and sampling."""

    def test_default_durations_all_canonical_points(self):
        """When durations omitted, all 9 canonical points are returned."""
        server_curve = {
            5: 1100,
            15: 950,
            30: 850,
            60: 600,
            120: 480,
            300: 380,
            480: 350,
            1200: 320,
            3600: 290,
        }

        result = format_curve(server_curve, metric="HR")

        # All 9 durations should be present
        assert len(result) == 9
        assert set(result.keys()) == {
            "5s",
            "15s",
            "30s",
            "1m",
            "2m",
            "5m",
            "8m",
            "20m",
            "60m",
        }

    def test_explicit_durations_subset(self):
        """Explicit durations parameter returns only those points."""
        server_curve = {
            5: 1100,
            60: 600,
            300: 380,
            1200: 320,
            3600: 290,
        }

        result = format_curve(
            server_curve, metric="HR", requested_durations=["1m", "5m", "60m"]
        )

        assert set(result.keys()) == {"1m", "5m", "60m"}
        assert result["1m"] == 600
        assert result["5m"] == 380
        assert result["60m"] == 290

    def test_power_metric_returns_watts_and_wkg(self):
        """Power metric returns {w, wkg} per duration."""
        server_curve = {
            300: 380,  # 5m @ 380 watts
            1200: 320,  # 20m @ 320 watts
        }
        weight = 72.0

        result = format_curve(
            server_curve,
            metric="POWER",
            requested_durations=["5m", "20m"],
            weight=weight,
        )

        assert result["5m"]["w"] == 380
        assert result["5m"]["wkg"] == pytest.approx(380 / 72.0, abs=0.01)
        assert result["20m"]["w"] == 320
        assert result["20m"]["wkg"] == pytest.approx(320 / 72.0, abs=0.01)

    def test_hr_metric_returns_bpm(self):
        """HR metric returns bare bpm values."""
        server_curve = {
            300: 160,  # 5m @ 160 bpm
            1200: 145,  # 20m @ 145 bpm
        }

        result = format_curve(
            server_curve,
            metric="HR",
            requested_durations=["5m", "20m"],
        )

        assert result["5m"] == 160
        assert result["20m"] == 145
        assert not isinstance(result["5m"], dict)

    def test_pace_metric_returns_pace(self):
        """Pace metric returns bare pace values."""
        server_curve = {
            300: 4.5,  # 5m @ 4:30/km
            1200: 4.2,  # 20m @ 4:12/km
        }

        result = format_curve(
            server_curve,
            metric="PACE",
            requested_durations=["5m", "20m"],
        )

        assert result["5m"] == 4.5
        assert result["20m"] == 4.2

    def test_missing_durations_skipped(self):
        """Durations not in server curve are skipped."""
        server_curve = {
            300: 380,  # 5m available
            # 20m not available
        }

        result = format_curve(
            server_curve,
            metric="HR",
            requested_durations=["5m", "20m"],
        )

        # Only 5m should be present; 20m is missing
        assert "5m" in result
        assert "20m" not in result

    def test_unknown_durations_skipped(self):
        """Unknown duration labels are silently skipped."""
        server_curve = {
            300: 380,
            1200: 320,
        }

        result = format_curve(
            server_curve,
            metric="HR",
            requested_durations=["5m", "invalid_duration", "20m"],
        )

        # Only valid durations should be present
        assert set(result.keys()) == {"5m", "20m"}
