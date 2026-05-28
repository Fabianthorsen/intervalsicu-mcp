import enum
from datetime import date

import httpx
from fastmcp import Context, FastMCP

activities = FastMCP("activities")


class CoachTick(enum.IntEnum):
    WTF = enum.auto()
    POOR = enum.auto()
    SEEN = enum.auto()
    GOOD = enum.auto()
    AMAZING = enum.auto()


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def list_activities_between_dates(
    ctx: Context,
    athlete_id: str = "0",
    from_date: date = date.today(),
    to_date: date = date.today(),
) -> list:
    """List recent activities in descending date order.

    Args:
        from_date:
        to_date:
    """
    data = await ctx.lifespan_context["client"].get(
        f"/athlete/{athlete_id}/activities",
        params=httpx.QueryParams(
            oldest=from_date.isoformat(), newest=to_date.isoformat()
        ),
    )
    return data.json()


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity(ctx: Context, activity_id: str) -> dict:
    """Get full details for a single activity including power, HR, TSS, pace,
    distance, elevation, training load, feel, compliance and coaching data.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    resp = await ctx.lifespan_context["client"].get(f"/activity/{activity_id}")
    return resp.json()


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_intervals(ctx: Context, activity_id: str) -> dict:
    """Get the analysed intervals for a specific activity, including power, HR,
    pace, TSS, and other metrics per interval.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    resp = await ctx.lifespan_context["client"].get(
        f"/activity/{activity_id}/intervals"
    )
    return resp.json()


@activities.tool(tags={"Activities"}, annotations={"readOnlyHint": True})
async def get_activity_messages(ctx: Context, activity_id: str) -> list:
    """Get all messages/comments posted on an activity (athlete and coach feedback).

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
    """
    resp = await ctx.lifespan_context["client"].get(
        f"/activity/{activity_id}/messages"
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json() or []


@activities.tool(tags={"Coaching"})
async def set_coach_evaluation(
    ctx: Context, activity_id: str, evaluation: CoachTick
) -> dict:
    """Set the coach's evaluation tick on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        evaluation: 1 = WTF, 2 = POOR, 3 = SEEN, 4 = GOOD, 5 = AMAZING.
    """
    resp = await ctx.lifespan_context["client"].put(
        f"/activity/{activity_id}", json={"coach_tick": evaluation}
    )
    resp.raise_for_status()
    return {
        "message": f"Coach evaluation for activity {activity_id} set to {evaluation.name}.",
        "status": resp.status_code,
    }


@activities.tool(tags={"Coaching"})
async def post_activity_message(ctx: Context, activity_id: str, content: str) -> dict:
    """Post a coaching message or feedback comment on an athlete's activity.

    Args:
        activity_id: The activity ID (e.g. 'i129230824').
        content: The message text to post.
    """
    resp = await ctx.lifespan_context["client"].post(
        f"/activity/{activity_id}/messages", json={"content": content}
    )
    resp.raise_for_status()
    return {"message": f"Message posted to activity {activity_id}.", "status": resp.status_code}
