import enum
from datetime import date as _date, timedelta

import httpx
from fastmcp import Context, FastMCP

from client import get_client
from shaping import project_and_prune_list

wellness = FastMCP("wellness")


class WellnessFields(enum.Enum):
    """Semantic field groups for wellness data."""

    HEADLINE = "headline"
    HRV = "hrv"
    CTL_ATL_TSB = "ctl_atl_tsb"
    SUBJECTIVE = "subjective"
    NUTRITION = "nutrition"
    ALL = "all"


WELLNESS_TAXONOMY = {
    "HEADLINE": [
        "sleepScore",
        "sleepSecs",
        "restingHR",
        "weight",
        # These flag weight/restingHR as carried forward from an earlier day
        # rather than measured. Without them a stale value reads as today's.
        "tempWeight",
        "tempRestingHR",
    ],
    "HRV": [
        "hrv",
        "hrvSDNN",
        "baevskySI",
    ],
    "CTL_ATL_TSB": [
        "ctl",
        "ctlLoad",
        "atl",
        "atlLoad",
        "rampRate",
        # Derived in _add_form, not returned by the API — see below.
        "tsb",
    ],
    # What the athlete reports about themselves, as opposed to what a device
    # measured. These are the fields update_wellness is mostly used to set.
    "SUBJECTIVE": [
        "fatigue",
        "soreness",
        "stress",
        "mood",
        "motivation",
        "sleepQuality",
        "readiness",
        "injury",
        "comments",
    ],
    "NUTRITION": [
        "kcalConsumed",
        "carbohydrates",
        "protein",
        "fatTotal",
        "hydration",
        "hydrationVolume",
        "bloodGlucose",
    ],
}


def _add_form(record: dict) -> dict:
    """Add TSB (form) — intervals.icu returns CTL and ATL but never their difference.

    Trivial arithmetic over two already-summarised values, which ADR-0003
    explicitly permits.
    """
    ctl, atl = record.get("ctl"), record.get("atl")
    if ctl is not None and atl is not None:
        record["tsb"] = round(ctl - atl, 1)
    return record


@wellness.tool(tags={"Wellness"}, annotations={"readOnlyHint": True})
async def get_wellness(
    ctx: Context,
    days: int = 7,
    athlete_id: str = "0",
    include: list[str] | None = None,
) -> list:
    """Get daily wellness records (CTL, ATL, HRV, sleep, weight, etc.).

    Args:
        days: How many days of history to return (default 7). Use 1 for today only, 30 for a month.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        include: List of field groups to include (e.g. ['HEADLINE', 'HRV']). Omit for core + HEADLINE.
                 Options: HEADLINE (default), HRV, CTL_ATL_TSB (fitness/fatigue/form),
                 SUBJECTIVE (self-reported fatigue, soreness, mood, readiness),
                 NUTRITION (calories, macros, hydration), ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    # Normalize enum values to string group names
    include_groups = [
        (g.value if isinstance(g, WellnessFields) else g).upper()
        for g in include
    ]

    oldest = (_date.today() - timedelta(days=days - 1)).isoformat()
    client = await get_client(ctx)

    data = await client.get(
        f"/athlete/{athlete_id}/wellness", params=httpx.QueryParams(oldest=oldest)
    )
    records = [_add_form(r) for r in data.json()]

    return project_and_prune_list(records, include_groups, WELLNESS_TAXONOMY)


@wellness.tool(tags={"Wellness"})
async def update_wellness(
    ctx: Context,
    date: str,
    athlete_id: str = "0",
    weight: float | None = None,
    restingHR: int | None = None,
    hrv: float | None = None,
    sleepSecs: int | None = None,
    sleepScore: float | None = None,
    sleepQuality: int | None = None,
    fatigue: int | None = None,
    soreness: int | None = None,
    stress: int | None = None,
    mood: int | None = None,
    motivation: int | None = None,
    readiness: float | None = None,
    injury: int | None = None,
    spO2: float | None = None,
    steps: int | None = None,
    vo2max: float | None = None,
    kcalConsumed: int | None = None,
    carbohydrates: float | None = None,
    protein: float | None = None,
    fatTotal: float | None = None,
    hydrationVolume: float | None = None,
    comments: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Record or update wellness data for a single day.

    Only the fields you pass are changed — anything already recorded for that
    date, including metrics synced from a watch, is left alone.

    The 1-4 scale fields (fatigue, soreness, stress, mood, motivation,
    sleepQuality, injury) follow the intervals.icu convention where 1 is best
    and 4 is worst. `readiness` is a 0-100 score.

    Args:
        date: The day to update, ISO-8601 (e.g. '2026-08-26').
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        weight: Body weight in kg.
        restingHR: Resting heart rate in bpm.
        hrv: Heart rate variability (rMSSD).
        sleepSecs: Sleep duration in seconds.
        sleepScore: Sleep score, typically 0-100.
        sleepQuality: Subjective sleep quality, 1 (best) to 4 (worst).
        fatigue: Subjective fatigue, 1 (fresh) to 4 (exhausted).
        soreness: Subjective muscle soreness, 1 (none) to 4 (severe).
        stress: Subjective stress, 1 (low) to 4 (high).
        mood: Subjective mood, 1 (good) to 4 (poor).
        motivation: Subjective motivation, 1 (high) to 4 (low).
        readiness: Readiness score, 0-100.
        injury: Injury severity, 1 (none) to 4 (severe).
        spO2: Blood oxygen saturation, percent.
        steps: Step count for the day.
        vo2max: VO2 max in ml/kg/min.
        kcalConsumed: Total energy consumed for the day, in kcal.
        carbohydrates: Carbohydrate intake in grams.
        protein: Protein intake in grams.
        fatTotal: Fat intake in grams.
        hydrationVolume: Fluid intake in millilitres.
        comments: Free-text note — illness, travel, or anything worth remembering.
        extra: Any other Wellness field not listed above, as a dict
               (e.g. {'bodyFat': 12.5, 'systolic': 118, 'lactate': 1.4}).
    """
    named = {
        "weight": weight,
        "restingHR": restingHR,
        "hrv": hrv,
        "sleepSecs": sleepSecs,
        "sleepScore": sleepScore,
        "sleepQuality": sleepQuality,
        "fatigue": fatigue,
        "soreness": soreness,
        "stress": stress,
        "mood": mood,
        "motivation": motivation,
        "readiness": readiness,
        "injury": injury,
        "spO2": spO2,
        "steps": steps,
        "vo2max": vo2max,
        "kcalConsumed": kcalConsumed,
        "carbohydrates": carbohydrates,
        "protein": protein,
        "fatTotal": fatTotal,
        "hydrationVolume": hydrationVolume,
        "comments": comments,
    }
    body = {k: v for k, v in named.items() if v is not None}
    if extra:
        body.update(extra)

    if not body:
        return {"note": "No fields supplied; nothing was updated."}

    client = await get_client(ctx)
    resp = await client.put(f"/athlete/{athlete_id}/wellness/{date}", json=body)

    return {
        "date": date,
        "athlete_id": athlete_id,
        "updated": sorted(body),
        "record": _add_form(resp.json()),
    }
