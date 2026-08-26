"""Unit tests for derived form (TSB).

intervals.icu returns CTL and ATL but never their difference, so the
CTL_ATL_TSB group promised a field it never delivered until this was added.
Literal values taken from real wellness records.
"""

from wellness import WELLNESS_TAXONOMY, _add_form


def test_form_is_ctl_minus_atl() -> None:
    record = _add_form({"id": "2026-08-26", "ctl": 33.83729, "atl": 52.011055})
    assert record["tsb"] == -18.2


def test_positive_form_when_fresh() -> None:
    """Mid-taper: fitness above fatigue."""
    record = _add_form({"ctl": 36.20806, "atl": 23.580084})
    assert record["tsb"] == 12.6


def test_zero_form_is_kept_not_pruned_as_empty() -> None:
    record = _add_form({"ctl": 30.0, "atl": 30.0})
    assert record["tsb"] == 0


def test_missing_components_produce_no_form() -> None:
    assert "tsb" not in _add_form({"ctl": 30.0})
    assert "tsb" not in _add_form({"atl": 30.0})
    assert "tsb" not in _add_form({})


def test_does_not_disturb_other_fields() -> None:
    record = _add_form({"id": "2026-08-26", "ctl": 10.0, "atl": 4.0, "hrv": 69})
    assert record["hrv"] == 69
    assert record["id"] == "2026-08-26"


def test_tsb_is_declared_in_the_taxonomy() -> None:
    """Otherwise projection would prune it before it reached the caller."""
    assert "tsb" in WELLNESS_TAXONOMY["CTL_ATL_TSB"]


def test_temp_flags_are_headline_so_stale_values_are_visible() -> None:
    """weight/restingHR can be carried forward from an earlier day."""
    assert "tempWeight" in WELLNESS_TAXONOMY["HEADLINE"]
    assert "tempRestingHR" in WELLNESS_TAXONOMY["HEADLINE"]
