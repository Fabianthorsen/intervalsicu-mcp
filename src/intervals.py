"""Interval shaping and editing for an activity (ADR-0002, ADR-0003).

intervals.icu detects intervals automatically and returns 75 fields per
interval, which is unreadable at any useful number of reps. So reads project
to field groups the way every other resource does.

Editing is deliberately narrow. The API can replace an activity's whole
interval list in one call; that is not exposed. What is exposed is the pair a
coach actually needs — cut a stretch of riding into its own interval, and give
an interval a name — plus a delete to undo a bad cut. Every edit is a
read-modify-write of the interval as the server returned it, so no field the
model never saw can be dropped on the way through.
"""

import enum

from shaping import project_and_prune_list


class IntervalFields(enum.Enum):
    """Semantic field groups for interval data."""

    HEADLINE = "headline"
    TIMING = "timing"
    POWER = "power"
    HR = "hr"
    PACE = "pace"
    CADENCE = "cadence"
    ELEVATION = "elevation"
    ALL = "all"


# `id` and `type` (WORK/RECOVERY) arrive free via shaping.CORE_FIELDS.
INTERVAL_TAXONOMY = {
    "HEADLINE": [
        "label",
        "group_id",
        "count",
        "start_time",
        "end_time",
        "elapsed_time",
        "moving_time",
        "distance",
        "average_watts",
        "weighted_average_watts",
        "intensity",
        "training_load",
        "average_heartrate",
        "average_cadence",
        "zone",
    ],
    "TIMING": [
        "start_time",
        "end_time",
        "start_index",
        "end_index",
        "elapsed_time",
        "moving_time",
    ],
    "POWER": [
        "average_watts",
        "weighted_average_watts",
        "min_watts",
        "max_watts",
        "average_watts_kg",
        "max_watts_kg",
        "intensity",
        "training_load",
        "joules",
        "joules_above_ftp",
        "w5s_variability",
        "decoupling",
        "wbal_start",
        "wbal_end",
        "zone",
        "zone_min_watts",
        "zone_max_watts",
    ],
    "HR": [
        "average_heartrate",
        "min_heartrate",
        "max_heartrate",
        "decoupling",
    ],
    "PACE": [
        "average_speed",
        "min_speed",
        "max_speed",
        "gap",
        "distance",
        "average_stride",
    ],
    "CADENCE": [
        "average_cadence",
        "min_cadence",
        "max_cadence",
        "average_torque",
        "min_torque",
        "max_torque",
    ],
    "ELEVATION": [
        "total_elevation_gain",
        "min_altitude",
        "max_altitude",
        "average_gradient",
    ],
}


class IntervalType(enum.Enum):
    """How intervals.icu classifies an interval. Drives its own analysis."""

    WORK = "WORK"
    RECOVERY = "RECOVERY"


class IntervalError(ValueError):
    """The requested interval edit cannot be applied to this activity."""


def extract_intervals(payload: object) -> list[dict]:
    """Pull the interval list out of a /activity/{id}/intervals response."""
    if isinstance(payload, dict):
        intervals = payload.get("icu_intervals")
        return intervals if isinstance(intervals, list) else []
    return payload if isinstance(payload, list) else []


def shape_intervals(payload: dict, include: list[str]) -> dict:
    """Project an intervals response to the requested groups.

    ``groups`` carries intervals.icu's own repeat detection — the reps it
    considers the same effort, keyed by a label like '365s@226w80rpm'. It is
    what answers "was that 4×5min or 4 unrelated efforts", so it survives
    shaping alongside the intervals themselves.
    """
    return {
        "activity_id": payload.get("id"),
        "intervals": project_and_prune_list(
            extract_intervals(payload), include, INTERVAL_TAXONOMY
        ),
        "groups": project_and_prune_list(
            payload.get("icu_groups") or [], include, INTERVAL_TAXONOMY
        ),
    }


def find_interval(intervals: list[dict], interval_id: int) -> dict:
    """Return the interval with this id.

    Raises:
        IntervalError: naming the ids that do exist, because the recovery is
            always "pick one of these" rather than "retry the same call".
    """
    for interval in intervals:
        if interval.get("id") == interval_id:
            return interval

    available = ", ".join(str(i.get("id")) for i in intervals) or "none"
    raise IntervalError(
        f"This activity has no interval with id {interval_id}. "
        f"Its interval ids are: {available}."
    )


def apply_edits(
    interval: dict,
    label: str | None = None,
    interval_type: str | None = None,
) -> dict:
    """Return a copy of the interval with label and/or type changed.

    The whole object is carried through rather than a sparse patch: the PUT
    replaces the interval server-side, so anything omitted here would be
    omitted there.
    """
    if label is None and interval_type is None:
        raise IntervalError(
            "Nothing to change — pass a label, a type, or both."
        )

    edited = dict(interval)
    if label is not None:
        # '' is how a label is cleared; prune would drop the key entirely, so
        # the empty string has to survive as far as the request body.
        edited["label"] = label
    if interval_type is not None:
        edited["type"] = interval_type
    return edited


def plan_cuts(
    intervals: list[dict], start_index: int, end_index: int
) -> list[int]:
    """Which sample indices must be split to isolate a section.

    intervals.icu's intervals tile the recording end to end — one interval's
    end_index is the next one's start_index, with no gaps. So a new section is
    not inserted, it is carved out: cut at each end that is not already an
    interval boundary. A section whose ends both coincide with existing
    boundaries needs no cut at all, and only wants naming.
    """
    if end_index <= start_index:
        raise IntervalError(
            f"The section's end ({end_index}) must come after its start "
            f"({start_index})."
        )

    boundaries = set()
    for interval in intervals:
        boundaries.add(interval.get("start_index"))
        boundaries.add(interval.get("end_index"))

    return sorted(i for i in (start_index, end_index) if i not in boundaries)


def find_section(
    intervals: list[dict], start_index: int, end_index: int
) -> dict:
    """Return the interval spanning exactly this index range.

    Raises:
        IntervalError: if the cuts did not produce the expected section, which
            means the server split somewhere other than asked and the result
            should not be labelled blind.
    """
    for interval in intervals:
        if (
            interval.get("start_index") == start_index
            and interval.get("end_index") == end_index
        ):
            return interval

    raise IntervalError(
        f"No interval spans samples {start_index}-{end_index} after cutting. "
        "The activity's intervals were changed but nothing was labelled; call "
        "get_activity_intervals to see the current state."
    )
