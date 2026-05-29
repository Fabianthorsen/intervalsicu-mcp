"""Curve sampling and formatting (ADR-0003: server-compute and sample, never streams)."""

# Canonical duration labels → seconds
CANONICAL_DURATIONS = {
    "5s": 5,
    "15s": 15,
    "30s": 30,
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "8m": 480,
    "20m": 1200,
    "60m": 3600,
}

# Default: all canonical durations
DEFAULT_DURATIONS = list(CANONICAL_DURATIONS.keys())


def format_curve(
    server_curve: dict,
    metric: str,
    requested_durations: list[str] | None = None,
    weight: float | None = None,
) -> dict:
    """Format a server-computed curve to canonical durations with optional W/kg derivation.

    Args:
        server_curve: The raw curve payload from intervals.icu. Either a single
            curve (parallel ``secs`` / ``watts`` / ``values`` arrays) or the
            athlete-curves envelope ``{"list": [<curve>, ...]}``. A plain
            ``{seconds: value}`` mapping is also accepted.
        metric: 'POWER', 'HR', or 'PACE' — determines output format.
        requested_durations: List of duration labels (e.g. ['5s', '1m', '5m']).
                            Defaults to all canonical durations.
        weight: Athlete weight in kg. When present and positive, POWER results
            include a derived ``wkg``; otherwise only raw watts are returned.

    Returns:
        Dict with formatted curve: {label: value} or {label: {w, wkg}} for power.
    """
    if requested_durations is None:
        requested_durations = DEFAULT_DURATIONS

    curve_by_seconds = _normalize_curve_input(server_curve, metric)

    result = {}
    for label in requested_durations:
        if label not in CANONICAL_DURATIONS:
            continue  # Skip unknown durations
        seconds = CANONICAL_DURATIONS[label]
        if seconds not in curve_by_seconds:
            continue  # Duration not in server data

        value = curve_by_seconds[seconds]

        if metric == "POWER":
            entry = {"w": value}
            if weight and weight > 0:
                entry["wkg"] = round(value / weight, 2)
            result[label] = entry
        else:
            # For HR and pace, just the value
            result[label] = value

    return result


def _normalize_curve_input(curve: dict, metric: str) -> dict:
    """Normalize a server curve payload to a {seconds: value} mapping.

    Handles the three shapes intervals.icu actually returns:
      - athlete curves: ``{"list": [{"secs": [...], "watts": [...]}], ...}``
      - activity curve: ``{"secs": [...], "values": [...], "watts": [...]}``
      - a plain ``{seconds: value}`` (or canonical-label) mapping
    """
    if not isinstance(curve, dict):
        return {}

    # Unwrap the athlete-curves envelope; we request a single window, so take it.
    entries = curve.get("list")
    if isinstance(entries, list):
        if not entries:
            return {}
        curve = entries[0]

    secs = curve.get("secs")
    if isinstance(secs, list):
        # Parallel-array form. Power lives in `watts`; HR/pace in `values`.
        values = curve.get("watts") if metric == "POWER" else None
        if not isinstance(values, list):
            values = curve.get("values")
        if not isinstance(values, list):
            return {}
        return {s: v for s, v in zip(secs, values) if v is not None}

    # Plain mapping: {seconds:int -> value} or {label:str -> value}.
    normalized = {}
    for key, value in curve.items():
        if isinstance(key, int):
            normalized[key] = value
        elif isinstance(key, str) and key in CANONICAL_DURATIONS:
            normalized[CANONICAL_DURATIONS[key]] = value
    return normalized
