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
        server_curve: Dict with curve data (label or seconds → value).
        metric: 'POWER', 'HR', or 'PACE' — determines output format.
        requested_durations: List of duration labels (e.g. ['5s', '1m', '5m']).
                            Defaults to all canonical durations.
        weight: Athlete weight in kg (required if metric is POWER, for W/kg calculation).

    Returns:
        Dict with formatted curve: {label: value} or {label: {w, wkg}} for power.
    """
    if requested_durations is None:
        requested_durations = DEFAULT_DURATIONS

    # Server curve is typically keyed by seconds; normalize to canonical labels
    curve_by_seconds = _normalize_curve_input(server_curve)

    result = {}
    for label in requested_durations:
        if label not in CANONICAL_DURATIONS:
            continue  # Skip unknown durations
        seconds = CANONICAL_DURATIONS[label]
        if seconds not in curve_by_seconds:
            continue  # Duration not in server data

        value = curve_by_seconds[seconds]

        if metric == "POWER":
            # For power, return {w, wkg}
            if weight is None:
                weight = 1.0  # Fallback
            result[label] = {"w": value, "wkg": round(value / weight, 2)}
        else:
            # For HR and pace, just the value
            result[label] = value

    return result


def _normalize_curve_input(curve: dict) -> dict:
    """Normalize curve data to {seconds: value} format.

    The server may return curves keyed by seconds (int), duration labels (str),
    or a mix. Normalize to {seconds: value}.
    """
    normalized = {}
    for key, value in curve.items():
        if isinstance(key, int):
            # Already in seconds
            normalized[key] = value
        elif isinstance(key, str) and key in CANONICAL_DURATIONS:
            # Convert label to seconds
            normalized[CANONICAL_DURATIONS[key]] = value
    return normalized
