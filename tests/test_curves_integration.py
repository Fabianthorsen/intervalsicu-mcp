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


def _fallback_ctx():
    """A Context whose lifespan_context has no client, forcing get_client to
    fall back to the real hooked global client (built from INTERVALS_API_KEY)."""
    from fastmcp import Context
    from unittest.mock import MagicMock

    ctx = MagicMock(spec=Context)
    ctx.lifespan_context.__getitem__.side_effect = KeyError("client")
    return ctx


@pytest.mark.asyncio
async def test_get_power_curve_tool_returns_populated_curve():
    """get_power_curve returns an actual sampled curve, not an empty dict.

    Regression: the tool previously returned {} because the formatter couldn't
    parse the real {"list": [{"secs": [...], "watts": [...]}]} payload.
    """
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + "/../src")
    from activities import get_power_curve

    result = await get_power_curve(_fallback_ctx(), athlete_id="0", sport_type="Ride", days=90)

    print(f"\n✓ get_power_curve curve: {result.get('curve')}")
    assert result["sport_type"] == "Ride"
    assert result["window"] == "90d"

    curve = result["curve"]
    assert isinstance(curve, dict) and curve, "curve must be a non-empty mapping"
    # Canonical labels with watts present.
    sample = next(iter(curve.values()))
    assert "w" in sample and isinstance(sample["w"], (int, float))
    # Weight came from the payload, so W/kg is derived (not fabricated).
    assert result["weight"] and result["weight"] > 0
    assert "wkg" in sample


@pytest.mark.asyncio
async def test_get_activity_curve_tool_returns_populated_curve():
    """get_activity_curve returns a populated curve for an activity that has one."""
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + "/../src")
    from activities import get_activity_curve

    # Find a recent activity that actually has a power curve.
    activity_id = None
    async with httpx.AsyncClient(base_url=BASE_URL, auth=("API_KEY", API_KEY)) as client:
        resp = await client.get(
            "/athlete/0/activities",
            params={
                "oldest": (date.today() - timedelta(days=30)).isoformat(),
                "newest": date.today().isoformat(),
            },
        )
        for activity in resp.json():
            probe = await client.get(f"/activity/{activity['id']}/power-curve.json")
            if probe.status_code == 200:
                activity_id = activity["id"]
                break

    if not activity_id:
        pytest.skip("No recent activities with a power curve found")

    result = await get_activity_curve(_fallback_ctx(), activity_id=activity_id)

    print(f"\n✓ get_activity_curve curve: {result.get('curve')}")
    assert result["activity_id"] == activity_id
    assert result["metric"] == "POWER"

    curve = result["curve"]
    assert isinstance(curve, dict) and curve, "curve must be a non-empty mapping"
    sample = next(iter(curve.values()))
    assert "w" in sample and isinstance(sample["w"], (int, float))


@pytest.mark.asyncio
async def test_get_activity_curve_missing_curve_is_graceful():
    """A pace curve on a non-distance/typeless activity 404s; the tool reports it."""
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + "/../src")
    from activities import get_activity_curve

    # Unknown activity id → 404 from the curve endpoint → graceful note, no raise.
    result = await get_activity_curve(_fallback_ctx(), activity_id="i_does_not_exist")

    assert result["curve"] is None
    assert "note" in result
