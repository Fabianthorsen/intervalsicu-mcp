"""Unit tests for sport-settings shaping and sport matching.

Literal inputs taken from a real GET /athlete/0/sport-settings response.
"""

from athletes import _match_sport, _shape_sport_settings

RIDE = {
    "id": 1001,
    "types": ["Ride", "GravelRide", "VirtualRide"],
    "ftp": 285,
    "indoor_ftp": 285,
    "lthr": 167,
    "max_hr": 194,
    "threshold_pace": None,
    "w_prime": 26800,
    "p_max": None,
    "power_zones": [55, 75, 90, 105, 120, 150, 999],
    "hr_zones": [134, 148, 155, 166, 171, 176, 194],
    "pace_zones": None,
    "sweet_spot_min": 84,
    "sweet_spot_max": 97,
    # Noise the coach never needs:
    "activity_charts": ["a", "b"],
    "default_gear_id": "b123",
    "tiz_order": 3,
}

RUN = {"id": 1002, "types": ["Run", "TrailRun"], "lthr": 171, "max_hr": 192}


def test_drops_display_and_device_fields() -> None:
    shaped = _shape_sport_settings(RIDE)
    assert "activity_charts" not in shaped
    assert "default_gear_id" not in shaped
    assert "tiz_order" not in shaped


def test_keeps_thresholds_and_zones() -> None:
    shaped = _shape_sport_settings(RIDE)
    assert shaped["ftp"] == 285
    assert shaped["w_prime"] == 26800
    assert shaped["power_zones"] == [55, 75, 90, 105, 120, 150, 999]
    assert shaped["id"] == 1001


def test_zone_units_are_labelled() -> None:
    """power_zones and hr_zones are both bare int arrays but mean different things."""
    shaped = _shape_sport_settings(RIDE)
    assert shaped["power_zones_unit"] == "percent_of_ftp"
    assert shaped["hr_zones_unit"] == "bpm"


def test_unit_labels_absent_when_zones_are() -> None:
    shaped = _shape_sport_settings(RUN)
    assert "power_zones_unit" not in shaped
    assert "hr_zones_unit" not in shaped


def test_unset_thresholds_are_omitted_not_null() -> None:
    shaped = _shape_sport_settings(RIDE)
    assert "threshold_pace" not in shaped
    assert "p_max" not in shaped


def test_matches_any_type_in_the_group() -> None:
    assert _match_sport([RIDE, RUN], "GravelRide") is RIDE
    assert _match_sport([RIDE, RUN], "TrailRun") is RUN


def test_match_is_case_insensitive_and_trims() -> None:
    assert _match_sport([RIDE, RUN], "  ride  ") is RIDE
    assert _match_sport([RIDE, RUN], "RUN") is RUN


def test_unknown_sport_returns_none() -> None:
    assert _match_sport([RIDE, RUN], "Swim") is None


def test_no_partial_matching() -> None:
    """'Rid' must not match 'Ride' — a typo should fail loudly, not pick a sport."""
    assert _match_sport([RIDE, RUN], "Rid") is None
