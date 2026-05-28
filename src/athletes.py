from fastmcp import Context, FastMCP

athletes = FastMCP("athletes")


@athletes.tool(tags={"Athletes"}, annotations={"readOnlyHint": True})
async def get_athlete(ctx: Context, athlete_id: str = "0") -> dict:
    """Get an athlete's profile (name, weight, FTP, resting HR, timezone, gear).

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    data = await ctx.lifespan_context["client"].get(f"/athlete/{athlete_id}")
    return data.json()


@athletes.tool(tags={"Athletes"}, annotations={"readOnlyHint": True})
async def list_coached_athletes(ctx: Context) -> list:
    """List all athletes the current user is coaching, with a recent summary of
    their training load, fitness, and activity data."""
    resp = await ctx.lifespan_context["client"].get("/athlete/0/athlete-summary")
    return resp.json()
