import enum

from fastmcp import Context, FastMCP

from client import get_client
from shaping import project_and_prune, project_and_prune_list

athletes = FastMCP("athletes")


class AthleteFields(enum.Enum):
    """Semantic field groups for athlete profile data."""

    HEADLINE = "headline"
    ZONES = "zones"
    METADATA = "metadata"
    ALL = "all"


ATHLETE_TAXONOMY = {
    "HEADLINE": [
        "name",
        "firstname",
        "sex",
        "city",
        "country",
        "timezone",
        "icu_weight",
        "icu_resting_hr",
    ],
    # Thresholds and zones are per-sport and live in the embedded `sportSettings`
    # array, not on the athlete itself — there is no top-level `ftp`. ZONES is
    # therefore assembled by _summarize_sport_settings rather than projected.
    "ZONES": ["sportSettings"],
    "METADATA": [
        "icu_date_of_birth",
        "locale",
        "measurement_preference",
        "weight_pref_lb",
        "icu_last_seen",
        "icu_activated",
        "icu_coach",
    ],
}

# Threshold fields worth summarising per sport. Full zone boundaries are left to
# get_sport_settings — this is the "what are her numbers" view.
_THRESHOLD_FIELDS = ("ftp", "indoor_ftp", "lthr", "max_hr", "threshold_pace", "w_prime")


def _summarize_sport_settings(settings: list[dict]) -> list[dict]:
    """Reduce the sportSettings array to a per-sport threshold summary.

    Each entry covers a group of activity types (e.g. Ride/GravelRide/VirtualRide).
    Entries with no thresholds set at all are dropped rather than returned empty.
    """
    summary = []
    for entry in settings:
        thresholds = {
            f: entry[f]
            for f in _THRESHOLD_FIELDS
            if entry.get(f) is not None
        }
        if not thresholds:
            continue
        summary.append({"types": entry.get("types", []), **thresholds})
    return summary


@athletes.tool(tags={"Athletes"}, annotations={"readOnlyHint": True})
async def get_athlete(
    ctx: Context, athlete_id: str = "0", include: list[str] | None = None
) -> dict:
    """Get an athlete's profile with optional field group selection.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        include: List of field groups to include (e.g. ['HEADLINE', 'ZONES']). Omit for core + HEADLINE.
                 Options: HEADLINE (default), ZONES, METADATA, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        (g.value if isinstance(g, AthleteFields) else g).upper()
        for g in include
    ]

    client = await get_client(ctx)
    data = await client.get(f"/athlete/{athlete_id}")
    obj = data.json()

    shaped = project_and_prune(obj, include_groups, ATHLETE_TAXONOMY)

    # Replace the raw sportSettings array with the threshold summary. ALL is a
    # deliberate raw passthrough, so leave it untouched there.
    if "ZONES" in include_groups and "ALL" not in include_groups:
        summary = _summarize_sport_settings(shaped.pop("sportSettings", []))
        if summary:
            shaped["sport_thresholds"] = summary

    return shaped


@athletes.tool(tags={"Athletes"}, annotations={"readOnlyHint": True})
async def list_coached_athletes(ctx: Context) -> list:
    """List athletes the current user coaches (core + HEADLINE fields).

    Use get_athlete with an athlete's id to drill into zones or metadata.
    """
    client = await get_client(ctx)
    resp = await client.get("/athlete/0/athlete-summary")
    athletes_list = resp.json()

    return project_and_prune_list(athletes_list, ["HEADLINE"], ATHLETE_TAXONOMY)
