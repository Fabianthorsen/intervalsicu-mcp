"""Integration tests for interval editing against the real API.

These mutate a real activity, so each one restores what it changed. The
activity is picked at runtime — the most recent one that has intervals — so
nothing here depends on a fixed id.

Skipped without INTERVALS_API_KEY. They will also fail on a network that
blocks intervals.icu; see the note in tests/conftest.py.
"""

from datetime import date, timedelta

import pytest

from activities import (
    create_activity_interval,
    delete_activity_intervals,
    get_activity_intervals,
    update_activity_interval,
)


async def _activity_with_intervals(api_context) -> tuple[str, dict]:
    """Find the most recent activity that has at least one interval."""
    client = api_context.lifespan_context["client"]
    resp = await client.get(
        "/athlete/0/activities",
        params={
            "oldest": (date.today() - timedelta(days=60)).isoformat(),
            "newest": date.today().isoformat(),
        },
    )
    for activity in resp.json():
        activity_id = activity.get("id")
        if not isinstance(activity_id, str) or not activity_id.startswith("i"):
            continue
        shaped = await get_activity_intervals(api_context, activity_id)
        if shaped["intervals"]:
            return activity_id, shaped

    pytest.skip("No recent activity with intervals to test against")


@pytest.mark.asyncio
async def test_intervals_are_shaped_not_dumped(api_context) -> None:
    activity_id, shaped = await _activity_with_intervals(api_context)
    first = shaped["intervals"][0]

    assert shaped["activity_id"] == activity_id
    assert isinstance(first["id"], int)
    # HEADLINE is a small slice of the 75 fields the API returns.
    assert len(first) < 20


@pytest.mark.asyncio
async def test_all_returns_more_than_headline(api_context) -> None:
    activity_id, headline = await _activity_with_intervals(api_context)
    raw = await get_activity_intervals(api_context, activity_id, include=["ALL"])

    assert len(raw["intervals"][0]) > len(headline["intervals"][0])


@pytest.mark.asyncio
async def test_label_round_trips_and_is_restored(api_context) -> None:
    activity_id, shaped = await _activity_with_intervals(api_context)
    target = shaped["intervals"][0]
    original_label = target.get("label")

    try:
        updated = await update_activity_interval(
            api_context, activity_id, target["id"], label="pytest label"
        )
        edited = next(i for i in updated["intervals"] if i["id"] == target["id"])
        assert edited["label"] == "pytest label"

        # Metrics the edit never touched must survive the read-modify-write.
        assert edited.get("average_watts") == target.get("average_watts")
    finally:
        await update_activity_interval(
            api_context, activity_id, target["id"], label=original_label or ""
        )


@pytest.mark.asyncio
async def test_carve_a_section_then_delete_it(api_context) -> None:
    """A section is cut out of its neighbours, so deleting it restores them."""
    activity_id, shaped = await _activity_with_intervals(api_context)
    before = shaped["intervals"]

    longest = max(before, key=lambda i: i.get("elapsed_time") or 0)
    quarter = (longest["end_time"] - longest["start_time"]) // 4
    start = longest["start_time"] + quarter
    end = longest["end_time"] - quarter

    after = await create_activity_interval(
        api_context, activity_id, start, end, label="pytest section"
    )

    section = next(i for i in after["intervals"] if i.get("label") == "pytest section")
    assert section["start_time"] == start
    assert section["end_time"] == end
    # One interval became three: before the section, the section, after it.
    assert len(after["intervals"]) == len(before) + 2

    new_ids = {i["id"] for i in after["intervals"]} - {i["id"] for i in before}
    restored = await delete_activity_intervals(
        api_context, activity_id, sorted(new_ids)
    )
    assert len(restored["intervals"]) <= len(before) + 1
