import enum

from fastmcp import Context, FastMCP

from shaping import project_and_prune_list

gear = FastMCP("gear")


class GearFields(enum.Enum):
    """Semantic field groups for gear data."""

    HEADLINE = "headline"
    MAINTENANCE = "maintenance"
    METADATA = "metadata"
    ALL = "all"


GEAR_TAXONOMY = {
    "HEADLINE": [
        "name",
        "type",
        "total_distance",
        "total_time",
        "activity_count",
    ],
    "MAINTENANCE": [
        "maintenance_reminders",
        "maintenance_interval",
        "last_maintenance_date",
    ],
    "METADATA": [
        "date_added",
        "notes",
        "brand",
        "model",
        "status",
    ],
}


@gear.tool(tags={"Gear"}, annotations={"readOnlyHint": True})
async def list_gear(
    ctx: Context, athlete_id: str = "0", include: list[str] | None = None
) -> list:
    """List gear (bikes, shoes, components) with optional field selection.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        include: List of field groups to include. Omit for core + HEADLINE.
                 Options: HEADLINE (default), MAINTENANCE, METADATA, ALL (raw passthrough).
    """
    if include is None:
        include = ["HEADLINE"]

    include_groups = [
        g.value if isinstance(g, GearFields) else g
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

    resp = await client.get(f"/athlete/{athlete_id}/gear")
    items = resp.json()

    return project_and_prune_list(items, include_groups, GEAR_TAXONOMY)
