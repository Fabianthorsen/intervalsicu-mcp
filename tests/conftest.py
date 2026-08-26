"""Pytest fixtures for integration tests."""

import os
from typing import AsyncGenerator

import httpx
import pytest
import truststore

# Use the OS trust store rather than certifi's bundle. Behind a TLS-intercepting
# corporate proxy the root CA lives in the system keychain only, so certifi-based
# verification fails where curl succeeds. Test-time only — the Fly deployment
# sits behind no such proxy.
truststore.inject_into_ssl()


@pytest.fixture
async def api_context() -> AsyncGenerator:
    """Provide a Context-like object with a real httpx client for integration tests."""
    api_key = os.environ.get("INTERVALS_API_KEY")
    if not api_key:
        pytest.skip("INTERVALS_API_KEY not set in .env")

    async with httpx.AsyncClient(
        base_url="https://intervals.icu/api/v1",
        auth=("API_KEY", api_key),
    ) as client:
        # Create a mock context object that has the lifespan_context attribute
        class MockContext:
            def __init__(self, http_client):
                self.lifespan_context = {"client": http_client}

        yield MockContext(client)
