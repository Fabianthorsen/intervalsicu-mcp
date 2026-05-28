from fastmcp import Context, FastMCP

gear = FastMCP("gear")


@gear.tool(tags={"Gear"}, annotations={"readOnlyHint": True})
async def list_gear(ctx: Context, athlete_id: str = "0") -> list:
    """List all gear (bikes, shoes, components) with total distance, time, activity
    count, and any maintenance reminders.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    resp = await ctx.lifespan_context["client"].get(f"/athlete/{athlete_id}/gear")
    return resp.json()
