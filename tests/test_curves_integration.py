"""Integration tests for curve tools against real API."""

import asyncio
import os
from datetime import date, timedelta

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("INTERVALS_API_KEY")
BASE_URL = "https://intervals.icu/api/v1"


@pytest.mark.asyncio
async def test_power_curves_endpoint_with_type():
    """Test power curves endpoint with required type parameter."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        auth=("API_KEY", API_KEY),
    ) as client:
        athlete_id = "0"

        # Try with type=Ride and curves parameter
        try:
            resp = await client.get(
                f"/athlete/{athlete_id}/power-curves.json",
                params={
                    "type": "Ride",
                    "curves": "90d",  # Past 90 days
                }
            )
            print(f"\n✓ Power curves (type=Ride, 90d)")
            print(f"Status: {resp.status_code}")
            data = resp.json()
            print(f"Response: {data}")
            assert resp.status_code == 200
        except Exception as e:
            print(f"✗ Error: {e}")
            raise


@pytest.mark.asyncio
async def test_activity_curve_endpoint_with_multiple_types():
    """Test activity curve endpoint with activities of different types."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        auth=("API_KEY", API_KEY),
    ) as client:
        # Get recent activities
        resp = await client.get(
            "/athlete/0/activities",
            params={
                "oldest": (date.today() - timedelta(days=30)).isoformat(),
                "newest": date.today().isoformat(),
            }
        )
        activities = resp.json()

        if not activities:
            pytest.skip("No recent activities found")

        # Try first 3 activities to find one with a curve
        for activity in activities[:3]:
            activity_id = activity["id"]
            activity_type = activity.get("type", "Unknown")
            print(f"\nTesting activity {activity_id} (type: {activity_type})")

            try:
                resp = await client.get(f"/activity/{activity_id}/power-curve.json")
                print(f"Status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"✓ Got curve data: {data}")
                    return  # Found one with a curve
                elif resp.status_code == 404:
                    print(f"No curve available for this activity")
            except Exception as e:
                print(f"✗ Error: {e}")

        pytest.skip("No activities with curves found in recent history")


@pytest.mark.asyncio
async def test_get_power_curve_tool():
    """Test the get_power_curve tool implementation."""
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + "/../src")

    from activities import get_power_curve
    from fastmcp import Context
    from unittest.mock import MagicMock

    ctx = MagicMock(spec=Context)
    ctx.lifespan_context.get.side_effect = lambda x: None

    result = await get_power_curve(ctx, athlete_id="0", sport_type="Ride", days=90)

    print(f"\n✓ get_power_curve result:")
    print(f"  athlete_id: {result.get('athlete_id')}")
    print(f"  sport_type: {result.get('sport_type')}")
    print(f"  window: {result.get('window')}")
    print(f"  weight: {result.get('weight')}")

    assert result.get("athlete_id") == "0"
    assert result.get("sport_type") == "Ride"
    assert result.get("window") == "90d"


@pytest.mark.asyncio
async def test_get_activity_curve_tool():
    """Test the get_activity_curve tool implementation."""
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + "/../src")

    from activities import get_activity_curve
    from fastmcp import Context
    from unittest.mock import MagicMock

    ctx = MagicMock(spec=Context)
    ctx.lifespan_context.get.side_effect = lambda x: None

    # Get a recent activity that has curves
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        auth=("API_KEY", API_KEY),
    ) as client:
        resp = await client.get(
            "/athlete/0/activities",
            params={
                "oldest": (date.today() - timedelta(days=30)).isoformat(),
                "newest": date.today().isoformat(),
            }
        )
        activities = resp.json()

    if not activities:
        pytest.skip("No recent activities found")

    # Find an activity with a curve
    activity_id = None
    for activity in activities:
        test_resp = await httpx.AsyncClient(
            base_url=BASE_URL,
            auth=("API_KEY", API_KEY),
        ).get(f"/activity/{activity['id']}/power-curve.json")
        if test_resp.status_code == 200:
            activity_id = activity["id"]
            break

    if not activity_id:
        pytest.skip("No activities with curves found")

    result = await get_activity_curve(ctx, activity_id=activity_id)

    print(f"\n✓ get_activity_curve result:")
    print(f"  activity_id: {result.get('activity_id')}")
    print(f"  metric: {result.get('metric')}")
    print(f"  weight: {result.get('weight')}")

    assert result.get("activity_id") == activity_id
    assert result.get("metric") == "POWER"
