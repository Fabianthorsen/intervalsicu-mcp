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
                 ZONES returns `sport_thresholds` — FTP/LTHR/max HR per sport group.
                 For full zone boundaries use get_sport_settings.
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


# Fields a coach reasonably reads or writes. The full SportSettings object also
# carries display preferences, chart layouts and device sync flags — none of
# which belong in a coaching conversation.
SPORT_SETTINGS_FIELDS = (
    "ftp",
    "indoor_ftp",
    "lthr",
    "max_hr",
    "threshold_pace",
    "w_prime",
    "p_max",
    "power_zones",
    "hr_zones",
    "pace_zones",
    "pace_units",
    "sweet_spot_min",
    "sweet_spot_max",
)


def _shape_sport_settings(entry: dict) -> dict:
    """Project one sport-settings record, noting the units of each zone array.

    power_zones are percentages of FTP while hr_zones are absolute bpm — the
    arrays look alike and are trivially misread, so the units are labelled.
    """
    shaped = {"id": entry.get("id"), "types": entry.get("types", [])}
    shaped.update(
        {f: entry[f] for f in SPORT_SETTINGS_FIELDS if entry.get(f) is not None}
    )
    if "power_zones" in shaped:
        shaped["power_zones_unit"] = "percent_of_ftp"
    if "hr_zones" in shaped:
        shaped["hr_zones_unit"] = "bpm"
    return shaped


def _match_sport(entries: list[dict], sport: str) -> dict | None:
    """Find the settings record covering an activity type, case-insensitively."""
    wanted = sport.strip().lower()
    for entry in entries:
        if any(t.lower() == wanted for t in entry.get("types", [])):
            return entry
    return None


@athletes.tool(tags={"Athletes"}, annotations={"readOnlyHint": True})
async def get_sport_settings(
    ctx: Context, athlete_id: str = "0", sport: str | None = None
) -> dict | list:
    """Get an athlete's thresholds and training zones for a sport.

    Settings are grouped by activity type — one record covers e.g. Ride,
    GravelRide and VirtualRide together. Zone boundaries are returned as the
    API stores them: power_zones as percentages of FTP, hr_zones as absolute
    bpm (each is labelled with its unit).

    For a quick "what are her numbers" view across all sports, use
    get_athlete with include=['ZONES'] instead — it needs no extra call.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        sport: Activity type to return, e.g. 'Ride' or 'Run'. Omit for all sports.
    """
    client = await get_client(ctx)
    resp = await client.get(f"/athlete/{athlete_id}/sport-settings")
    entries = resp.json()

    if sport is None:
        return [_shape_sport_settings(e) for e in entries]

    entry = _match_sport(entries, sport)
    if entry is None:
        known = sorted({t for e in entries for t in e.get("types", [])})
        return {
            "note": f"No sport settings for '{sport}'.",
            "known_sports": known,
        }
    return _shape_sport_settings(entry)


@athletes.tool(tags={"Athletes"})
async def update_sport_settings(
    ctx: Context,
    sport: str,
    athlete_id: str = "0",
    ftp: int | None = None,
    indoor_ftp: int | None = None,
    lthr: int | None = None,
    max_hr: int | None = None,
    threshold_pace: float | None = None,
    w_prime: int | None = None,
    power_zones: list[int] | None = None,
    hr_zones: list[int] | None = None,
    pace_zones: list[float] | None = None,
    sweet_spot_min: int | None = None,
    sweet_spot_max: int | None = None,
    recalc_hr_zones: bool = False,
) -> dict:
    """Update an athlete's thresholds or zones for a sport.

    Changes affect how future analysis is calculated. Activities already
    recorded keep the zones they were analysed with until apply_sport_settings
    is called — so updating FTP alone is a safe, reversible change.

    Only the arguments you pass are changed; everything else is preserved.

    Args:
        sport: Activity type, e.g. 'Ride' or 'Run'. The whole type group is updated.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        ftp: Functional threshold power in watts.
        indoor_ftp: Separate indoor FTP in watts, if the athlete uses one.
        lthr: Lactate threshold heart rate in bpm.
        max_hr: Maximum heart rate in bpm.
        threshold_pace: Threshold pace in metres per second.
        w_prime: W' (anaerobic work capacity) in joules.
        power_zones: Zone upper bounds as percentages of FTP, e.g. [55, 75, 90, 105, 120, 150, 999].
        hr_zones: Zone upper bounds as absolute bpm, e.g. [134, 148, 155, 166, 171, 176, 194].
        pace_zones: Zone upper bounds for pace.
        sweet_spot_min: Sweet spot lower bound as a percentage of FTP.
        sweet_spot_max: Sweet spot upper bound as a percentage of FTP.
        recalc_hr_zones: Ask intervals.icu to recompute HR zones from the new lthr/max_hr.
    """
    changes = {
        "ftp": ftp,
        "indoor_ftp": indoor_ftp,
        "lthr": lthr,
        "max_hr": max_hr,
        "threshold_pace": threshold_pace,
        "w_prime": w_prime,
        "power_zones": power_zones,
        "hr_zones": hr_zones,
        "pace_zones": pace_zones,
        "sweet_spot_min": sweet_spot_min,
        "sweet_spot_max": sweet_spot_max,
    }
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return {"note": "No changes supplied; nothing was updated."}

    client = await get_client(ctx)

    # Read-modify-write: the endpoint takes a whole SportSettings object and
    # does not document partial-merge semantics, so send the current record
    # with the changes layered on rather than risk blanking untouched fields.
    resp = await client.get(f"/athlete/{athlete_id}/sport-settings")
    entries = resp.json()
    current = _match_sport(entries, sport)
    if current is None:
        known = sorted({t for e in entries for t in e.get("types", [])})
        return {
            "note": f"No sport settings for '{sport}'; nothing was updated.",
            "known_sports": known,
        }

    before = {k: current.get(k) for k in changes}
    body = {**current, **changes}

    updated = await client.put(
        f"/athlete/{athlete_id}/sport-settings/{current['id']}",
        params={"recalcHrZones": str(recalc_hr_zones).lower()},
        json=body,
    )

    return {
        "sport": sport,
        "types": current.get("types", []),
        "changed": {k: {"from": before[k], "to": v} for k, v in changes.items()},
        "settings": _shape_sport_settings(updated.json()),
        "note": (
            "Existing activities still use their original zones. Call "
            "apply_sport_settings to recalculate them."
        ),
    }


@athletes.tool(tags={"Athletes"}, annotations={"destructiveHint": True})
async def apply_sport_settings(ctx: Context, sport: str, athlete_id: str = "0") -> dict:
    """Recalculate past activities against the athlete's current zones.

    Destructive and not readily undoable: this rewrites zone times and
    load/intensity figures on every matching activity in the athlete's history.
    If the thresholds are wrong, months of training data are recalculated
    against them, and the only remedy is to correct the numbers and apply again.

    Run this only when explicitly asked. Updating thresholds does not require
    it — future activities pick up new zones on their own.

    Args:
        sport: Activity type whose settings should be applied, e.g. 'Ride'.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    client = await get_client(ctx)
    resp = await client.get(f"/athlete/{athlete_id}/sport-settings")
    entries = resp.json()
    current = _match_sport(entries, sport)
    if current is None:
        known = sorted({t for e in entries for t in e.get("types", [])})
        return {
            "note": f"No sport settings for '{sport}'; nothing was applied.",
            "known_sports": known,
        }

    await client.put(f"/athlete/{athlete_id}/sport-settings/{current['id']}/apply")

    return {
        "sport": sport,
        "types": current.get("types", []),
        "status": "Recalculation started.",
        "note": (
            "intervals.icu applies this asynchronously, so activity figures may "
            "take a few minutes to reflect the new zones."
        ),
    }
