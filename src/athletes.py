import enum

from fastmcp import Context, FastMCP

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
        "weight",
        "ftp",
        "restingHR",
        "timezone",
        "gender",
        "country",
    ],
    "ZONES": [
        "power_zone_1_start",
        "power_zone_2_start",
        "power_zone_3_start",
        "power_zone_4_start",
        "power_zone_5_start",
        "power_zone_6_start",
        "power_zone_7_start",
        "hr_zone_1_start",
        "hr_zone_2_start",
        "hr_zone_3_start",
        "hr_zone_4_start",
        "hr_zone_5_start",
        "lthr",
        "threshold_pace",
        "pace_zone_1_start",
        "pace_zone_2_start",
        "pace_zone_3_start",
        "pace_zone_4_start",
        "pace_zone_5_start",
    ],
    "METADATA": [
        "created",
        "last_update",
        "notes",
        "locale",
        "use_metric",
    ],
}


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
        g.value if isinstance(g, AthleteFields) else g
        for g in include
    ]

    # Get client from lifespan context (stdio) or fallback to creating one (HTTP)
    try:
        client = ctx.lifespan_context.get("client")
    except (AttributeError, TypeError):
        client = None

    if client is None:
        # HTTP transport fallback: create a client
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get("INTERVALS_API_KEY")
        client = httpx.AsyncClient(
            base_url="https://intervals.icu/api/v1",
            auth=("API_KEY", api_key),
        )

    data = await client.get(f"/athlete/{athlete_id}")
    obj = data.json()

    return project_and_prune(obj, include_groups, ATHLETE_TAXONOMY)


@athletes.tool(tags={"Athletes"}, annotations={"readOnlyHint": True})
async def list_coached_athletes(ctx: Context, include: list[str] | None = None) -> list:
    """List athletes the current user coaches with optional field group selection.

    Args:
        include: List of field groups to include. Omit for core + HEADLINE.
                 Options: HEADLINE (default), ZONES, METADATA, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        g.value if isinstance(g, AthleteFields) else g
        for g in include
    ]

    # Get client from lifespan context (stdio) or fallback to creating one (HTTP)
    try:
        client = ctx.lifespan_context.get("client")
    except (AttributeError, TypeError):
        client = None

    if client is None:
        # HTTP transport fallback: create a client
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get("INTERVALS_API_KEY")
        client = httpx.AsyncClient(
            base_url="https://intervals.icu/api/v1",
            auth=("API_KEY", api_key),
        )

    resp = await client.get("/athlete/0/athlete-summary")
    athletes_list = resp.json()

    return project_and_prune_list(athletes_list, include_groups, ATHLETE_TAXONOMY)
