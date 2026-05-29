"""Integration tests for MCP tools via HTTP transport."""

import asyncio
import json
import subprocess
import time
from datetime import date, timedelta

import httpx
import pytest


@pytest.fixture(scope="module")
def mcp_server():
    """Start the MCP server in HTTP mode and yield the base URL."""
    # Start server
    proc = subprocess.Popen(
        ["uv", "run", "python", "src/server.py"],
        env={**asyncio.os.environ, "MCP_TRANSPORT": "http", "PORT": "8001"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(3)

    yield "http://localhost:8001/mcp"

    # Cleanup
    proc.terminate()
    proc.wait(timeout=5)


@pytest.mark.asyncio
async def test_list_activities_via_http(mcp_server):
    """Call list_activities_between_dates via HTTP and verify it works."""
    from_date = (date.today() - timedelta(days=7)).isoformat()
    to_date = date.today().isoformat()

    request_body = {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "tools/call",
        "params": {
            "name": "list_activities_between_dates",
            "arguments": {
                "athlete_id": "0",
                "from_date": from_date,
                "to_date": to_date,
            },
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(mcp_server, json=request_body)

    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    result = resp.json()
    assert "result" in result or "error" not in result
    if "error" in result:
        raise AssertionError(f"Tool call failed: {result['error']}")


@pytest.mark.asyncio
async def test_get_activity_via_http(mcp_server):
    """Call get_activity via HTTP and verify it works."""
    request_body = {
        "jsonrpc": "2.0",
        "id": "test-2",
        "method": "tools/call",
        "params": {
            "name": "get_activity",
            "arguments": {
                "activity_id": "i129230824",
                "include": ["HEADLINE"],
            },
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(mcp_server, json=request_body)

    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    result = resp.json()
    if "error" in result:
        raise AssertionError(f"Tool call failed: {result['error']}")
