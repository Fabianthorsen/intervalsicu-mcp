"""Shared Intervals.icu HTTP client.

Used by both the server lifespan (stdio transport) and every resource tool
(HTTP transport, where the lifespan context is not populated). Centralising
this avoids the per-tool fallback duplication and guarantees every request
goes through the same auth + 4xx/5xx error hook.
"""

import os

import httpx
from dotenv import load_dotenv
from fastmcp import Context

load_dotenv()

BASE_URL = "https://intervals.icu/api/v1"

# Shared client used when the lifespan context isn't available (HTTP transport).
_global_client: httpx.AsyncClient | None = None


async def _error_hook(response: httpx.Response) -> None:
    """Raise HTTPStatusError on all 4xx/5xx responses.

    Must be a coroutine: httpx awaits response hooks on async clients.
    """
    if response.status_code >= 400:
        await response.aread()  # body must be read before raise_for_status on a stream
        response.raise_for_status()


def build_client() -> httpx.AsyncClient:
    """Construct an HTTP client with auth and the 4xx/5xx error hook installed."""
    return httpx.AsyncClient(
        base_url=BASE_URL,
        auth=("API_KEY", os.environ["INTERVALS_API_KEY"]),
        event_hooks={"response": [_error_hook]},
    )


async def get_client(ctx: Context) -> httpx.AsyncClient:
    """Return the HTTP client for this request.

    Prefers the lifespan-provided client (stdio transport). Falls back to a
    shared module-global client under HTTP transport, where FastMCP does not
    populate the lifespan context.
    """
    try:
        return ctx.lifespan_context["client"]
    except (KeyError, AttributeError, TypeError):
        global _global_client
        if _global_client is None:
            _global_client = build_client()
        return _global_client
