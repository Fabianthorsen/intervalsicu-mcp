"""Unit tests for reorg structure — verify old modules are gone."""

import pytest


def test_coaching_module_deleted():
    """The old coaching module should not be importable."""
    with pytest.raises(ImportError, match="No module named 'coaching'"):
        import coaching  # noqa: F401
