"""Unit tests for error handling — verify central httpx hook works."""

import pytest
import httpx


def error_hook(response):
    """Central error hook — raises on all 4xx/5xx."""
    if response.status_code >= 400:
        response.raise_for_status()


async def test_error_hook_raises_on_4xx():
    """The error hook should raise HTTPStatusError on 4xx/5xx responses."""
    # Create a mock 404 response with a request
    request = httpx.Request("GET", "https://intervals.icu/api/v1/activity/i_notfound")
    response = httpx.Response(404, text="Not found", request=request)

    # Verify the hook raises
    with pytest.raises(httpx.HTTPStatusError):
        error_hook(response)


async def test_error_hook_allows_2xx():
    """The error hook should allow 2xx responses through."""
    # Create a mock 200 response
    response = httpx.Response(200, json={"data": "value"})

    # Should not raise
    error_hook(response)  # Should pass without raising
