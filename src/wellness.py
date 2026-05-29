import enum
from datetime import date, timedelta

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
    ALL = "all"


WELLNESS_TAXONOMY = {
    "HEADLINE": [
        "sleepScore",
        "sleepSecs",
        "restingHR",
        "weight",
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
    ],
}


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
                 Options: HEADLINE (default), HRV, CTL_ATL_TSB, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    # Normalize enum values to string group names
    include_groups = [
        g.value if isinstance(g, WellnessFields) else g
        for g in include
    ]

    oldest = (date.today() - timedelta(days=days - 1)).isoformat()
    client = await get_client(ctx)

    data = await client.get(
        f"/athlete/{athlete_id}/wellness", params=httpx.QueryParams(oldest=oldest)
    )
    records = data.json()

    return project_and_prune_list(records, include_groups, WELLNESS_TAXONOMY)
