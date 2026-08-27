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


# --- projection -----------------------------------------------------------

from datetime import date as _date  # noqa: E402

from blocks import (  # noqa: E402
    apply_overlay,
    compare_block,
    compare_session,
    date_range,
    decay,
    event_load,
    planned_loads,
    project_fitness_series,
    zone_adherence,
)


def test_decay_moves_toward_the_load():
    assert decay(50, 100, 42) == pytest.approx(50 + 50 / 42)
    assert decay(50, 0, 42) == pytest.approx(50 - 50 / 42)


def test_decay_is_stable_when_load_equals_current():
    assert decay(50, 50, 42) == 50


def test_decay_rejects_a_zero_window():
    with pytest.raises(ValueError, match="days must be positive"):
        decay(50, 100, 0)


def test_date_range_is_inclusive():
    days = date_range(_date(2026, 3, 9), _date(2026, 3, 11))
    assert [d.isoformat() for d in days] == ["2026-03-09", "2026-03-10", "2026-03-11"]


def test_date_range_rejects_a_backwards_range():
    with pytest.raises(ValueError, match="is before"):
        date_range(_date(2026, 3, 11), _date(2026, 3, 9))


def test_event_load_prefers_derived_over_typed():
    assert event_load({"icu_training_load": 90, "load_target": 70}) == (90, "derived")
    assert event_load({"load_target": 70}) == (70, "target")
    assert event_load({}) == (0, "none")


def test_planned_loads_groups_by_local_date():
    plan = planned_loads(
        [
            {"id": 1, "start_date_local": "2026-03-10T00:00:00", "icu_training_load": 90},
            {"id": 2, "start_date_local": "2026-03-10T00:00:00", "load_target": 60},
        ]
    )
    assert len(plan["2026-03-10"]) == 2
    assert plan["2026-03-10"][0]["load_source"] == "derived"
    assert plan["2026-03-10"][1]["load_source"] == "target"


SATURDAY = {
    "id": 7,
    "start_date_local": "2026-03-14T00:00:00",
    "icu_training_load": 120,
    "moving_time": 7200,
    "name": "Long ride",
}


def base_plan():
    return planned_loads([SATURDAY])


# --- overlay --------------------------------------------------------------

def test_overlay_of_none_changes_nothing():
    plan, echo = apply_overlay(base_plan(), None)
    assert echo == []
    assert plan["2026-03-14"][0]["load"] == 120


def test_overlay_does_not_mutate_the_input():
    original = base_plan()
    apply_overlay(original, [{"date": "2026-03-14", "load": 60}])
    assert original["2026-03-14"][0]["load"] == 120


def test_overlay_sets_load_exactly():
    plan, echo = apply_overlay(base_plan(), [{"date": "2026-03-14", "load": 85}])
    assert plan["2026-03-14"][0]["load"] == 85
    assert echo[0]["action"] == "modified"


def test_overlay_scales_load_by_duration_and_marks_it_approximate():
    # 2h/120 TSS trimmed to 1h30 scales to 90.
    plan, echo = apply_overlay(base_plan(), [{"date": "2026-03-14", "moving_time": 5400}])
    assert plan["2026-03-14"][0]["load"] == 90
    assert plan["2026-03-14"][0]["load_source"] == "overlay_scaled"
    assert echo[0]["approximate"] is True


def test_overlay_refuses_to_scale_without_something_to_scale_from():
    plan = planned_loads([{"id": 9, "start_date_local": "2026-03-14T00:00:00"}])
    with pytest.raises(ValueError, match="no existing load and duration"):
        apply_overlay(plan, [{"date": "2026-03-14", "moving_time": 5400}])


def test_overlay_skips_a_session():
    plan, echo = apply_overlay(base_plan(), [{"date": "2026-03-14", "skip": True}])
    assert plan["2026-03-14"] == []
    assert echo[0]["action"] == "skipped"


def test_overlay_adds_a_session_where_none_is_planned():
    plan, echo = apply_overlay(base_plan(), [{"date": "2026-03-19", "load": 60}])
    assert plan["2026-03-19"][0]["load"] == 60
    assert echo[0]["action"] == "added"


def test_overlay_addition_is_visible_in_the_echo():
    # A typo'd date becomes a phantom session; the echo is how it is caught.
    _, echo = apply_overlay(base_plan(), [{"date": "2026-03-12", "load": 60}])
    assert echo == [{"date": "2026-03-12", "action": "added", "load": 60}]


def test_overlay_addition_without_a_load_is_an_error():
    with pytest.raises(ValueError, match="no 'load' to add"):
        apply_overlay(base_plan(), [{"date": "2026-03-19", "moving_time": 3600}])


def test_overlay_needs_a_date():
    with pytest.raises(ValueError, match="needs a 'date'"):
        apply_overlay(base_plan(), [{"load": 60}])


def test_overlay_entry_that_changes_nothing_is_an_error():
    with pytest.raises(ValueError, match="changes nothing"):
        apply_overlay(base_plan(), [{"date": "2026-03-14"}])


def test_overlay_refuses_an_ambiguous_day():
    plan = planned_loads(
        [
            {"id": 1, "start_date_local": "2026-03-14T00:00:00", "icu_training_load": 90},
            {"id": 2, "start_date_local": "2026-03-14T00:00:00", "icu_training_load": 40},
        ]
    )
    with pytest.raises(ValueError, match="pass 'event_id'"):
        apply_overlay(plan, [{"date": "2026-03-14", "load": 50}])


def test_overlay_disambiguates_with_event_id():
    plan = planned_loads(
        [
            {"id": 1, "start_date_local": "2026-03-14T00:00:00", "icu_training_load": 90},
            {"id": 2, "start_date_local": "2026-03-14T00:00:00", "icu_training_load": 40},
        ]
    )
    out, _ = apply_overlay(plan, [{"date": "2026-03-14", "event_id": 2, "load": 10}])
    loads = {s["event_id"]: s["load"] for s in out["2026-03-14"]}
    assert loads == {1: 90, 2: 10}


def test_overlay_skip_on_an_empty_day_reports_no_match():
    _, echo = apply_overlay(base_plan(), [{"date": "2026-03-20", "skip": True}])
    assert echo[0]["action"] == "no_match"


# --- the series -----------------------------------------------------------

DAYS = date_range(_date(2026, 3, 9), _date(2026, 3, 11))


def test_series_prefers_platform_values():
    platform = {"2026-03-09": {"ctl": 60, "atl": 70}}
    series = project_fitness_series(DAYS, {}, seed_ctl=50, seed_atl=50, platform=platform)
    assert series[0]["ctl"] == 60
    assert series[0]["tsb"] == -10
    assert series[0]["source"] == "platform"
    assert series[1]["source"] == "extrapolated"


def test_series_extrapolates_from_the_seed_without_platform_data():
    series = project_fitness_series(DAYS, {}, seed_ctl=42, seed_atl=42)
    assert all(d["source"] == "extrapolated" for d in series)
    assert series[0]["ctl"] < 42  # no load, so fitness decays


def test_series_carries_load_into_ctl():
    plan = {"2026-03-09": [{"load": 100, "load_source": "derived"}]}
    series = project_fitness_series(DAYS, plan, seed_ctl=50, seed_atl=50)
    assert series[0]["load"] == 100
    assert series[0]["ctl"] > 50
    assert series[0]["atl"] > series[0]["ctl"]  # ATL is the faster window


def test_a_hypothetical_carries_forward_through_the_series():
    # The whole point: a change on day one is not confined to day one.
    platform = {d.isoformat(): {"ctl": 60, "atl": 60} for d in DAYS}
    series = project_fitness_series(
        DAYS, {}, seed_ctl=60, seed_atl=60,
        platform=platform, overlaid_dates={"2026-03-10"},
    )
    assert series[0]["source"] == "platform"
    assert series[1]["source"] == "hypothetical"
    assert series[2]["source"] == "hypothetical"  # after the change, not just on it


def test_series_flags_a_typed_in_load_as_estimated():
    plan = {"2026-03-09": [{"load": 60, "load_source": "target"}]}
    series = project_fitness_series(DAYS, plan, seed_ctl=50, seed_atl=50)
    assert series[0]["load_is_estimated"] is True
    assert "load_is_estimated" not in series[1]


def test_series_does_not_flag_a_derived_load():
    plan = {"2026-03-09": [{"load": 60, "load_source": "derived"}]}
    series = project_fitness_series(DAYS, plan, seed_ctl=50, seed_atl=50)
    assert "load_is_estimated" not in series[0]


# --- adherence and planned-versus-actual ----------------------------------

Z2_RIDE = {
    "id": "i1",
    "name": "Endurance",
    "type": "Ride",
    "start_date_local": "2026-03-10T07:00:00",
    "icu_training_load": 110,
    "moving_time": 7200,
    "paired_event_id": 7,
    "icu_power_zones": [151, 214, 250, 285, 320, 400],
    "icu_zone_times": [
        {"id": "Z1", "secs": 1800},
        {"id": "Z2", "secs": 5000},
        {"id": "Z4", "secs": 400},
    ],
}


def test_zone_adherence_reports_both_percentages():
    out = zone_adherence(Z2_RIDE, "power", "Z2")
    assert out["ceiling"] == 214.0
    assert out["recorded_secs"] == 7200
    # Under the ceiling counts Z1 as well as Z2; in-band counts only Z2.
    assert out["under_ceiling_pct"] == pytest.approx(94.4, abs=0.1)
    assert out["in_band_pct"] == pytest.approx(69.4, abs=0.1)


def test_the_two_percentages_separate_coasting_from_attacking():
    disciplined = {"icu_power_zones": [151, 214], "icu_zone_times": [
        {"id": "Z1", "secs": 3000}, {"id": "Z2", "secs": 6000}]}
    hot = {"icu_power_zones": [151, 214], "icu_zone_times": [
        {"id": "Z2", "secs": 6000}, {"id": "Z5", "secs": 3000}]}
    a = zone_adherence(disciplined, "power", "Z2")
    b = zone_adherence(hot, "power", "Z2")
    # Same time in Z2, so in_band_pct is identical — and useless on its own.
    assert a["in_band_pct"] == b["in_band_pct"] == pytest.approx(66.7, abs=0.1)
    # Only the ceiling number separates the easy-spinning ride from the one
    # that spent 50 minutes above threshold.
    assert a["under_ceiling_pct"] == 100.0
    assert b["under_ceiling_pct"] == pytest.approx(66.7, abs=0.1)


def test_zone_adherence_is_none_without_the_metric():
    assert zone_adherence({"icu_hr_zone_times": [600]}, "power", "Z2") is None


def test_compare_session_reports_deltas_against_the_plan():
    row = compare_session(Z2_RIDE, {"id": 7, "icu_training_load": 100, "moving_time": 7200})
    assert row["planned"] is True
    assert row["planned_load"] == 100
    assert row["load_delta"] == 10
    assert row["load_pct"] == 110.0
    assert row["time_delta"] == 0


def test_compare_session_marks_an_unplanned_activity():
    row = compare_session({"id": "i2", "icu_training_load": 30}, None)
    assert row["planned"] is False
    assert "load_delta" not in row


def test_compare_session_passes_platform_compliance_through():
    row = compare_session({**Z2_RIDE, "compliance": 87.5}, None)
    assert row["compliance"] == 87.5


PLANNED = {
    "id": 7,
    "category": "WORKOUT",
    "start_date_local": "2026-03-10T00:00:00",
    "name": "Endurance",
    "icu_training_load": 100,
    "moving_time": 7200,
}
MISSED = {
    "id": 8,
    "category": "WORKOUT",
    "start_date_local": "2026-03-12T00:00:00",
    "name": "Threshold",
    "icu_training_load": 90,
}


def test_compare_block_pairs_activities_to_events():
    out = compare_block([Z2_RIDE], [PLANNED], metric=None, zone=None)
    assert out["aggregate"]["planned_sessions"] == 1
    assert out["aggregate"]["actual_load"] == 110
    assert out["aggregate"]["load_pct"] == 110.0


def test_compare_block_reports_a_missed_workout():
    out = compare_block([Z2_RIDE], [PLANNED, MISSED], metric=None, zone=None)
    assert out["aggregate"]["missed_sessions"] == 1
    assert out["missed"][0]["name"] == "Threshold"


def test_compare_block_reports_an_unplanned_activity():
    extra = {"id": "i9", "start_date_local": "2026-03-11T00:00:00", "icu_training_load": 40}
    out = compare_block([Z2_RIDE, extra], [PLANNED], metric=None, zone=None)
    assert out["aggregate"]["unplanned_sessions"] == 1


def test_compare_block_pools_adherence_and_counts_exclusions():
    padel = {
        "id": "i3",
        "type": "Padel",
        "start_date_local": "2026-03-11T18:00:00",
        "icu_training_load": 60,
        "icu_hr_zone_times": [600, 3000],
    }
    out = compare_block([Z2_RIDE, padel], [PLANNED], metric="power", zone="Z2")
    assert out["adherence"]["scored_sessions"] == 1
    assert out["adherence"]["sessions_without_metric"] == 1
    assert out["adherence"]["ceilings_used"] == [214.0]


def test_compare_block_flags_a_ceiling_that_moved_mid_block():
    older = {**Z2_RIDE, "id": "i0", "icu_power_zones": [140, 200]}
    out = compare_block([older, Z2_RIDE], [PLANNED], metric="power", zone="Z2")
    assert out["adherence"]["ceilings_used"] == [200.0, 214.0]
    assert "note" in out["adherence"]


def test_compare_block_omits_adherence_when_not_asked():
    out = compare_block([Z2_RIDE], [PLANNED], metric=None, zone=None)
    assert "adherence" not in out
