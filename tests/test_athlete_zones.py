"""Unit tests for the per-sport threshold summary.

Literal inputs copied from a real GET /athlete/0 response — sportSettings is an
array of activity-type groups, and most athletes have several with thresholds
set for only some of them.
"""

from athletes import _summarize_sport_settings

RIDE = {
    "types": ["Ride", "GravelRide", "VirtualRide"],
    "ftp": 285,
    "indoor_ftp": 285,
    "lthr": 167,
    "max_hr": 194,
    "threshold_pace": None,
    "w_prime": 26800,
    "p_max": None,
    "power_zones": [55, 75, 90, 105, 120, 150, 999],
}

RUN = {
    "types": ["Run", "TrailRun"],
    "ftp": None,
    "lthr": 171,
    "max_hr": 192,
    "threshold_pace": None,
    "w_prime": None,
    "hr_zones": [144, 152, 161, 170, 175, 180, 192],
}

UNCONFIGURED = {"types": ["Yoga"], "ftp": None, "lthr": None, "max_hr": None}


def test_summarizes_thresholds_per_sport_group() -> None:
    assert _summarize_sport_settings([RIDE]) == [
        {
            "types": ["Ride", "GravelRide", "VirtualRide"],
            "ftp": 285,
            "indoor_ftp": 285,
            "lthr": 167,
            "max_hr": 194,
            "w_prime": 26800,
        }
    ]


def test_omits_unset_thresholds_rather_than_returning_nulls() -> None:
    (run,) = _summarize_sport_settings([RUN])
    assert run == {"types": ["Run", "TrailRun"], "lthr": 171, "max_hr": 192}


def test_drops_sports_with_no_thresholds_configured() -> None:
    assert _summarize_sport_settings([UNCONFIGURED]) == []


def test_zone_boundaries_are_left_to_get_sport_settings() -> None:
    """The summary answers 'what are her numbers', not 'where are her zones'."""
    (ride,) = _summarize_sport_settings([RIDE])
    assert "power_zones" not in ride


def test_preserves_order_and_handles_multiple_groups() -> None:
    result = _summarize_sport_settings([RIDE, RUN, UNCONFIGURED])
    assert [r["types"][0] for r in result] == ["Ride", "Run"]


def test_empty_input() -> None:
    assert _summarize_sport_settings([]) == []
