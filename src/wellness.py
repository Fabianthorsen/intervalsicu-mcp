from datetime import date, timedelta

import httpx
from fastmcp import Context, FastMCP

wellness = FastMCP("wellness")

KEYS = ("id", "ctl", "atl", "rampRate", "hrv", "restingHR", "sleepScore", "sleepSecs")


@wellness.tool(tags={"Wellness"}, annotations={"readOnlyHint": True})
async def get_wellness(ctx: Context, days: int = 7, athlete_id: str = "0") -> list:
    """Get daily wellness records including fitness (CTL), fatigue (ATL), form (TSB),
    HRV, resting HR, sleep duration and score, weight, and other health metrics.

    Args:
        days: How many days of history to return (default 7). Use 1 for today only, 30 for a month.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    oldest = (date.today() - timedelta(days=days - 1)).isoformat()
    data = await ctx.lifespan_context["client"].get(
        f"/athlete/{athlete_id}/wellness", params=httpx.QueryParams(oldest=oldest)
    )
    return [{k: day.get(k) for k in KEYS} for day in data.json()]
