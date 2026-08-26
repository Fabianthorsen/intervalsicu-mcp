"""Arbitrary time-window metrics for an activity (ADR-0003).

intervals.icu computes windowed statistics server-side via interval-stats, but
addresses windows by *stream index* rather than by elapsed time. Index equals
elapsed second only when a device records at exactly 1Hz and never pauses;
smart recording and mid-ride stops break that assumption silently, so a window
picked by arithmetic would quietly describe the wrong segment.

So the time stream is fetched purely to resolve seconds to indices. It is an
implementation detail that never crosses the tool boundary — the caller sends
seconds and receives a handful of scalars. See docs/adr/0003.
"""

from bisect import bisect_left, bisect_right


def extract_time_stream(payload: object) -> list[int]:
    """Pull the elapsed-time array out of a /streams response.

    The endpoint returns a list of stream objects; the time stream holds
    elapsed seconds per sample index. A bare list is also accepted so callers
    can pass the array directly.
    """
    if isinstance(payload, list) and payload and isinstance(payload[0], (int, float)):
        return [int(v) for v in payload]

    if isinstance(payload, dict):
        payload = payload.get("streams", payload.get("data", []))

    if not isinstance(payload, list):
        return []

    for stream in payload:
        if not isinstance(stream, dict):
            continue
        if stream.get("type") == "time" or stream.get("name") == "time":
            data = stream.get("data")
            if isinstance(data, list):
                return [int(v) for v in data if v is not None]
    return []


class WindowError(ValueError):
    """The requested window cannot be resolved against this activity."""


def resolve_window(
    time_stream: list[int], start_seconds: int, end_seconds: int
) -> tuple[int, int]:
    """Map an elapsed-time window to the stream index range covering it.

    Returns the first index at or after ``start_seconds`` and the last index at
    or before ``end_seconds``, so the window never silently extends past what
    was asked for.

    Raises:
        WindowError: if the range is inverted, or falls outside the recording.
    """
    if end_seconds <= start_seconds:
        raise WindowError(
            f"end_seconds ({end_seconds}) must be greater than start_seconds ({start_seconds})."
        )
    if not time_stream:
        raise WindowError(
            "This activity has no time stream, so a window cannot be resolved. "
            "Use get_activity_intervals for its recorded intervals instead."
        )

    duration = time_stream[-1]
    if start_seconds >= duration:
        raise WindowError(
            f"start_seconds ({start_seconds}) is at or past the end of the "
            f"activity, which is {duration}s long."
        )

    start_index = bisect_left(time_stream, start_seconds)
    end_index = bisect_right(time_stream, end_seconds) - 1

    if end_index <= start_index:
        raise WindowError(
            f"The window {start_seconds}-{end_seconds}s covers fewer than two "
            "samples in this activity's recording."
        )

    return start_index, end_index


# Interval fields worth reporting, mapped to names that say what they are.
# intervals.icu uses `intensity` for IF and `training_load` for TSS.
_METRICS = {
    "average_watts": "avg_power_w",
    "weighted_average_watts": "normalized_power_w",
    "max_watts": "max_power_w",
    "average_watts_kg": "avg_power_wkg",
    "average_heartrate": "avg_hr_bpm",
    "max_heartrate": "max_hr_bpm",
    "average_cadence": "avg_cadence_rpm",
    "average_speed": "avg_speed_mps",
    "decoupling": "decoupling_percent",
    "intensity": "intensity_factor",
    "training_load": "tss",
    "elapsed_time": "elapsed_seconds",
    "moving_time": "moving_seconds",
    "distance": "distance_m",
    "joules": "work_joules",
}


def format_window_metrics(interval: dict) -> dict:
    """Shape an interval-stats response into the metrics a coach reads.

    Variability index is derived here rather than requested: it is NP over
    average power, arithmetic over two values the server already computed.
    """
    if not isinstance(interval, dict):
        return {}

    metrics = {
        name: interval[field]
        for field, name in _METRICS.items()
        if interval.get(field) is not None
    }

    avg = metrics.get("avg_power_w")
    normalized = metrics.get("normalized_power_w")
    if avg and normalized:
        metrics["variability_index"] = round(normalized / avg, 3)

    return metrics


def resolve_boundary(time_stream: list[int], at_seconds: int) -> int:
    """Map a single elapsed time to the first stream index at or after it.

    Used for cutting an interval, where the API wants one index rather than a
    range. Unlike resolve_window this accepts the very start and end of the
    recording: a section can legitimately begin at 0:00 or run to the finish,
    and a cut there is a no-op rather than an error.

    Raises:
        WindowError: if the time falls outside the recording.
    """
    if not time_stream:
        raise WindowError(
            "This activity has no time stream, so a position in it cannot be "
            "resolved. Its existing intervals can still be relabelled by id."
        )

    duration = time_stream[-1]
    if at_seconds < time_stream[0] or at_seconds > duration:
        raise WindowError(
            f"at_seconds ({at_seconds}) falls outside the recording, "
            f"which runs 0-{duration}s."
        )

    return bisect_left(time_stream, at_seconds)
