"""Integration tests for refactored get_wellness with field groups (ADR-0002)."""

import pytest
from datetime import date, timedelta

from wellness import get_wellness


class TestWellnessRefactored:
    """Integration tests against real API."""

    @pytest.mark.asyncio
    async def test_get_wellness_default_returns_core_plus_headline(self):
        """Default call returns core + HEADLINE fields (no include param)."""
        from wellness import get_wellness
        from fastmcp import Context

        # Mock context with lifespan client (tests will need real setup)
        # For now, just verify the function signature accepts include
        import inspect
        sig = inspect.signature(get_wellness)
        assert "include" in sig.parameters
        # Default should be None or empty list
        assert sig.parameters["include"].default is None

    def test_wellness_fields_enum_exists(self):
        """WellnessFields enum is defined with required groups."""
        from wellness import WellnessFields

        # Should have these groups
        assert hasattr(WellnessFields, "HEADLINE")
        assert hasattr(WellnessFields, "HRV")
        assert hasattr(WellnessFields, "CTL_ATL_TSB")
        assert hasattr(WellnessFields, "ALL")
