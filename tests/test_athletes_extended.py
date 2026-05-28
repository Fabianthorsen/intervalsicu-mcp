"""Unit tests for athletes module — verify coaching-related additions."""

from athletes import list_coached_athletes


def test_list_coached_athletes_is_callable():
    """list_coached_athletes function exists and is callable."""
    assert callable(list_coached_athletes)
