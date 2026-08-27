"""Unit tests for the blocks aggregation module — literal inputs, no network."""

import pytest

from blocks import (
    METRICS,
    SUMMARY_FIELDS,
    bucket_of,
    intensity_split,
    parse_local_date,
    pool_zone_secs,
    summarise,
    summarise_bucket,
    zone_bounds,
    zone_ceiling,
    zone_number,
    zone_secs,
)


# --- date bucketing -------------------------------------------------------

def test_parse_local_date_handles_datetime_and_bare_date():
    assert parse_local_date("2026-03-10T07:14:00").isoformat() == "2026-03-10"
    assert parse_local_date("2026-03-10").isoformat() == "2026-03-10"


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_parse_local_date_returns_none_on_junk(value):
    assert parse_local_date(value) is None


def test_week_bucket_is_the_iso_monday():
    # 2026-03-10 is a Tuesday; its ISO week starts Monday the 9th.
    assert bucket_of("2026-03-10T07:14:00", "week") == "2026-03-09"
    assert bucket_of("2026-03-09", "week") == "2026-03-09"
    assert bucket_of("2026-03-15", "week") == "2026-03-09"  # Sunday still week of the 9th


def test_week_bucket_crosses_a_month_boundary():
    assert bucket_of("2026-04-01", "week") == "2026-03-30"


def test_month_bucket_is_year_month():
    assert bucket_of("2026-03-10T07:14:00", "month") == "2026-03"


def test_bucket_of_rejects_unknown_grouping():
    with pytest.raises(ValueError, match="group_by must be"):
        bucket_of("2026-03-10", "quarter")


def test_bucket_of_returns_none_for_undated():
    assert bucket_of(None, "week") is None


# --- zone normalisation ---------------------------------------------------

def test_zone_number_reads_ids_and_falls_back_to_position():
    assert zone_number("Z3", 0) == 3
    assert zone_number("z3", 0) == 3
    assert zone_number("3", 0) == 3
    assert zone_number(None, 4) == 5


def test_zone_secs_normalises_power_objects():
    activity = {"icu_zone_times": [{"id": "Z1", "secs": 600}, {"id": "Z2", "secs": 1800}]}
    assert zone_secs(activity, "power") == {"Z1": 600, "Z2": 1800}


def test_zone_secs_normalises_positional_hr_array():
    activity = {"icu_hr_zone_times": [600, 1800, 300]}
    assert zone_secs(activity, "hr") == {"Z1": 600, "Z2": 1800, "Z3": 300}


def test_zone_secs_is_empty_when_metric_absent():
    # A padel match has no power. Empty is the exclusion signal, not zero.
    assert zone_secs({"icu_hr_zone_times": [600]}, "power") == {}


def test_zone_secs_drops_zero_buckets():
    assert zone_secs({"icu_hr_zone_times": [600, 0, 300]}, "hr") == {"Z1": 600, "Z3": 300}


def test_zone_secs_rejects_unknown_metric():
    with pytest.raises(ValueError, match="metric must be one of"):
        zone_secs({}, "cadence")


# --- zone bounds ----------------------------------------------------------

def test_zone_bounds_come_from_the_activity_not_the_athlete():
    activity = {"icu_power_zones": [151, 214, 250, 285, 320, 400]}
    assert zone_bounds(activity, "power")[1] == 214.0


def test_zone_ceiling_resolves_a_named_zone():
    activity = {"icu_power_zones": [151, 214, 250]}
    assert zone_ceiling(activity, "power", "Z2") == 214.0
    assert zone_ceiling(activity, "power", "Z1") == 151.0


def test_zone_ceiling_is_none_without_zones_or_out_of_range():
    assert zone_ceiling({}, "power", "Z2") is None
    assert zone_ceiling({"icu_power_zones": [151, 214]}, "power", "Z6") is None


def test_zone_ceiling_tracks_a_changed_ftp_across_two_activities():
    old = {"icu_power_zones": [140, 200]}
    new = {"icu_power_zones": [151, 214]}
    assert zone_ceiling(old, "power", "Z2") == 200.0
    assert zone_ceiling(new, "power", "Z2") == 214.0


# --- pooling and the split ------------------------------------------------

def test_pool_zone_secs_sums_and_orders_by_zone_number():
    pooled = pool_zone_secs([{"Z2": 1800, "Z10": 60}, {"Z2": 900, "Z1": 600}])
    assert pooled == {"Z1": 600, "Z2": 2700, "Z10": 60}
    assert list(pooled) == ["Z1", "Z2", "Z10"]  # numeric, not lexicographic


def test_intensity_split_buckets_z1_2_z3_and_z4_plus():
    split = intensity_split({"Z1": 3000, "Z2": 3000, "Z3": 1000, "Z5": 1000})
    assert split["easy_secs"] == 6000
    assert split["moderate_secs"] == 1000
    assert split["hard_secs"] == 1000
    assert split["easy_pct"] == 75.0
    assert split["total_secs"] == 8000


def test_intensity_split_is_empty_for_no_time():
    assert intensity_split({}) == {"total_secs": 0}


def test_intensity_split_weights_by_seconds_not_by_session():
    # A long easy ride must outweigh a short hard one — the reason the pooled
    # split is not an average of per-activity indices.
    long_easy = {"Z2": 18000}
    short_hard = {"Z5": 1800}
    split = intensity_split(pool_zone_secs([long_easy, short_hard]))
    assert split["easy_pct"] > 90


# --- bucket summaries -----------------------------------------------------

RIDE = {
    "type": "Ride",
    "start_date_local": "2026-03-10T07:00:00",
    "icu_training_load": 120,
    "moving_time": 7200,
    "icu_zone_times": [{"id": "Z1", "secs": 1200}, {"id": "Z2", "secs": 6000}],
}
PADEL = {
    "type": "Padel",
    "start_date_local": "2026-03-11T18:00:00",
    "icu_training_load": 60,
    "moving_time": 5400,
    "icu_hr_zone_times": [600, 3000, 1800],
}
SWIM = {
    "type": "Swim",
    "start_date_local": "2026-03-18T07:00:00",
    "icu_training_load": 40,
    "moving_time": 2700,
}


def test_summarise_bucket_totals_and_splits_by_sport():
    out = summarise_bucket([RIDE, PADEL], metric=None)
    assert out["sessions"] == 2
    assert out["load"] == 180
    assert out["moving_time"] == 12600
    assert out["by_sport"]["Ride"]["load"] == 120
    assert out["by_sport"]["Padel"]["sessions"] == 1


def test_by_sport_keeps_a_camp_legible():
    # The point of the sport split: cycling load collapsing while total load
    # holds is invisible in a single aggregate.
    out = summarise_bucket([PADEL, SWIM], metric=None)
    assert "Ride" not in out["by_sport"]
    assert out["load"] == 100


def test_summarise_bucket_excludes_sessions_without_the_metric():
    out = summarise_bucket([RIDE, PADEL], metric="power")
    assert out["sessions_without_metric"] == 1  # padel has no power
    assert out["zone_secs"] == {"Z1": 1200, "Z2": 6000}
    assert out["intensity_split"]["easy_pct"] == 100.0


def test_summarise_bucket_omits_zone_data_when_no_metric_asked_for():
    out = summarise_bucket([RIDE], metric=None)
    assert "zone_secs" not in out
    assert "intensity_split" not in out


def test_summarise_groups_by_week_and_totals_across_buckets():
    out = summarise([RIDE, PADEL, SWIM], group_by="week")
    assert set(out["buckets"]) == {"2026-03-09", "2026-03-16"}
    assert out["buckets"]["2026-03-09"]["sessions"] == 2
    assert out["buckets"]["2026-03-16"]["load"] == 40
    assert out["total"]["load"] == 220


def test_summarise_groups_by_month():
    out = summarise([RIDE, PADEL, SWIM], group_by="month")
    assert list(out["buckets"]) == ["2026-03"]
    assert out["buckets"]["2026-03"]["sessions"] == 3


def test_summarise_counts_undated_rather_than_dropping_them():
    out = summarise([RIDE, {"type": "Ride", "icu_training_load": 10}], group_by="week")
    assert out["undated"] == 1
    assert out["total"]["load"] == 120  # the undated one is not in the total


def test_summarise_omits_undated_key_when_all_dated():
    assert "undated" not in summarise([RIDE], group_by="week")


def test_summary_fields_cover_what_the_reducers_read():
    for field in ("icu_training_load", "moving_time", "type", "start_date_local"):
        assert field in SUMMARY_FIELDS
    assert set(METRICS) == {"power", "hr", "pace"}
