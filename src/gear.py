from fastmcp import Context, FastMCP

from client import get_client
from shaping import project_and_prune_list

gear = FastMCP("gear")


# Field groups for gear. Only HEADLINE is surfaced today (list_gear is the sole
# gear tool, and per ADR-0002 list tools take no selector); the rest document
# the taxonomy for a future get_gear drill-in tool.
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
async def list_gear(ctx: Context, athlete_id: str = "0") -> list:
    """List gear (bikes, shoes, components) — core + HEADLINE fields.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    client = await get_client(ctx)
    resp = await client.get(f"/athlete/{athlete_id}/gear")
    items = resp.json()

    return project_and_prune_list(items, ["HEADLINE"], GEAR_TAXONOMY)
