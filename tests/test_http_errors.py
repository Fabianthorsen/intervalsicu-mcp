"""Unit tests for HTTP failure descriptions.

The value of these messages is that the model can act on them, so the
assertions are about recovery guidance, not exact wording.
"""

import httpx
import pytest

from client import describe_http_error


def error(status: int, body: str = "", method: str = "GET", path: str = "/athlete/0") -> httpx.HTTPStatusError:
    request = httpx.Request(method, f"https://intervals.icu/api/v1{path}")
    response = httpx.Response(status, text=body, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_point_at_the_athlete_id(status: int) -> None:
    message = describe_http_error(error(status, path="/athlete/i999/wellness"))
    assert "list_coached_athletes" in message
    assert str(status) in message


def test_404_explains_the_id_formats() -> None:
    message = describe_http_error(error(404, path="/activity/nope"))
    assert "i129230824" in message


def test_422_includes_the_rejection_reason() -> None:
    message = describe_http_error(error(422, body='{"error":"start_date_local required"}'))
    assert "start_date_local required" in message


def test_429_tells_the_model_not_to_retry_immediately() -> None:
    message = describe_http_error(error(429))
    assert "do not retry immediately" in message.lower()


def test_5xx_is_attributed_to_the_server_not_the_request() -> None:
    message = describe_http_error(error(503))
    assert "not a problem with the request" in message


def test_message_names_the_failed_call() -> None:
    message = describe_http_error(error(500, method="PUT", path="/athlete/0/wellness"))
    assert "PUT" in message and "/athlete/0/wellness" in message


def test_long_bodies_are_truncated() -> None:
    message = describe_http_error(error(422, body="x" * 5000))
    assert len(message) < 500
    assert "…" in message


def test_empty_body_does_not_produce_a_dangling_message() -> None:
    message = describe_http_error(error(400, body=""))
    assert "empty response body" in message
