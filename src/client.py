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
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

load_dotenv()

BASE_URL = "https://intervals.icu/api/v1"

# Shared client used when the lifespan context isn't available (HTTP transport).
_global_client: httpx.AsyncClient | None = None


def describe_http_error(exc: httpx.HTTPStatusError) -> str:
    """Turn an intervals.icu HTTP failure into something the model can act on.

    A bare HTTPStatusError tells the model a request failed but not what to do
    next, so it tends to retry the identical call. These messages name the
    likely cause and the recovery, which is usually "use a different athlete_id"
    or "stop retrying".
    """
    status = exc.response.status_code
    method = exc.request.method
    path = exc.request.url.path

    if status in (401, 403):
        detail = (
            "Either INTERVALS_API_KEY is invalid, or this athlete has not shared "
            "their data with you. Coaches only see athletes returned by "
            "list_coached_athletes — check the athlete_id before retrying."
        )
    elif status == 404:
        detail = (
            "No such resource. Check the id exists and belongs to this athlete; "
            "activity ids look like 'i129230824' and event ids are integers."
        )
    elif status == 422:
        detail = f"intervals.icu rejected the request body or parameters: {_body(exc)}"
    elif status == 429:
        detail = "Rate limited by intervals.icu. Wait before retrying; do not retry immediately."
    elif status >= 500:
        detail = "intervals.icu is failing server-side. This is not a problem with the request; retrying later may work."
    else:
        detail = _body(exc)

    return f"intervals.icu {method} {path} failed ({status}). {detail}"


def _body(exc: httpx.HTTPStatusError) -> str:
    """Best-effort response body, truncated — some errors return an HTML page."""
    try:
        text = exc.response.text.strip()
    except Exception:  # noqa: BLE001 - body may not have been read
        return "(no response body)"
    return (text[:300] + "…") if len(text) > 300 else (text or "(empty response body)")


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


class HTTPErrorMiddleware(Middleware):
    """Convert uncaught HTTP failures into ToolErrors carrying an actionable message.

    Applied centrally rather than per-tool so a new tool cannot forget it. Tools
    that treat a status as data rather than failure — the curve tools return
    ``curve: None`` on 404 — catch HTTPStatusError themselves and never reach here.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext):
        try:
            return await call_next(context)
        except httpx.HTTPStatusError as exc:
            raise ToolError(describe_http_error(exc)) from exc
        except httpx.RequestError as exc:
            raise ToolError(
                f"Could not reach intervals.icu ({type(exc).__name__}: {exc}). "
                "The API may be down or the network blocked."
            ) from exc


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
