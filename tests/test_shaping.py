"""Tests for the shaping module (ADR-0002: field group projection + pruning)."""

import pytest

from shaping import project_and_prune, project_and_prune_list


# Fixture: a simple taxonomy for testing
MINIMAL_TAXONOMY = {
    "HEADLINE": ["duration", "distance", "load"],
    "POWER": ["avg_watts", "max_watts"],
    "HR": ["avg_hr", "max_hr", "has_heartrate"],
}


class TestProjectAndPrune:
    """Unit tests for project_and_prune (single object shaping)."""

    def test_single_group_selection_returns_exact_fields_plus_core(self):
        """Selecting a single group returns only those fields + core."""
        obj = {
            "id": "i123",
            "name": "Morning ride",
            "start_date_local": "2026-05-29",
            "type": "Ride",
            "duration": 3600,
            "distance": 42000,
            "load": 150,
            "avg_watts": 250,
            "max_watts": 1000,
            "avg_hr": 145,
            "max_hr": 180,
        }

        result = project_and_prune(
            obj, include=["HEADLINE"], taxonomy=MINIMAL_TAXONOMY
        )

        # Should have core + headline fields only
        assert set(result.keys()) == {
            "id",
            "name",
            "start_date_local",
            "type",
            "duration",
            "distance",
            "load",
        }
        assert result["id"] == "i123"
        assert result["name"] == "Morning ride"
        assert result["start_date_local"] == "2026-05-29"
        assert result["type"] == "Ride"
        assert result["duration"] == 3600

    def test_core_always_present_even_when_not_requested(self):
        """Core fields are always included, even if not in include list."""
        obj = {
            "id": "i456",
            "name": "Evening run",
            "start_date_local": "2026-05-29",
            "type": "Run",
            "avg_hr": 155,
            "max_hr": 175,
        }

        # Request only HR group, no explicit core
        result = project_and_prune(obj, include=["HR"], taxonomy=MINIMAL_TAXONOMY)

        # Core must be present regardless
        assert "id" in result
        assert "name" in result
        assert "start_date_local" in result
        assert "type" in result
        # HR fields should be there
        assert "avg_hr" in result
        assert "max_hr" in result
        # Other groups should not
        assert "duration" not in result

    def test_empties_dropped_but_zero_and_false_kept(self):
        """Drop null/[]/''/{}, but preserve 0 and False as real measurements."""
        obj = {
            "id": "i789",
            "name": "Swim",
            "start_date_local": "2026-05-29",
            "type": "Swim",
            "avg_watts": 0,  # Real: no power meter on a swim
            "has_heartrate": False,  # Real: didn't record HR
            "avg_hr": None,  # Empty: should drop
            "power_zones": [],  # Empty: should drop
            "description": "",  # Empty: should drop
            "metadata": {},  # Empty: should drop
        }

        result = project_and_prune(obj, include=["POWER", "HR"], taxonomy=MINIMAL_TAXONOMY)

        # 0 and False must be kept
        assert result["avg_watts"] == 0
        assert result["has_heartrate"] is False
        # Empties must be dropped
        assert "avg_hr" not in result
        assert "power_zones" not in result
        assert "description" not in result
        assert "metadata" not in result

    def test_multiple_groups_take_union(self):
        """Multiple groups are unioned: all requested fields are included."""
        obj = {
            "id": "i999",
            "name": "Hard session",
            "start_date_local": "2026-05-29",
            "type": "Ride",
            "duration": 5400,
            "distance": 60000,
            "load": 200,
            "avg_watts": 350,
            "max_watts": 1200,
            "avg_hr": 165,
            "max_hr": 190,
            "has_heartrate": True,
        }

        result = project_and_prune(obj, include=["HEADLINE", "POWER", "HR"], taxonomy=MINIMAL_TAXONOMY)

        # Should have all three groups + core
        expected = {
            "id",
            "name",
            "start_date_local",
            "type",
            # HEADLINE
            "duration",
            "distance",
            "load",
            # POWER
            "avg_watts",
            "max_watts",
            # HR
            "avg_hr",
            "max_hr",
            "has_heartrate",
        }
        assert set(result.keys()) == expected

    def test_all_returns_everything_still_pruned(self):
        """ALL special group means return all fields from object (but still prune empties)."""
        obj = {
            "id": "i111",
            "name": "Full test",
            "start_date_local": "2026-05-29",
            "type": "Ride",
            "field_a": "value_a",
            "field_b": 123,
            "field_c": None,  # Should be pruned
            "field_d": [],  # Should be pruned
        }

        result = project_and_prune(obj, include=["ALL"], taxonomy=MINIMAL_TAXONOMY)

        # Should have everything except the empty values
        assert result["id"] == "i111"
        assert result["name"] == "Full test"
        assert result["field_a"] == "value_a"
        assert result["field_b"] == 123
        assert "field_c" not in result
        assert "field_d" not in result


class TestProjectAndPruneList:
    """Unit tests for project_and_prune_list (list shaping)."""

    def test_list_shaped_element_wise(self):
        """Each item in the list is shaped independently."""
        items = [
            {
                "id": "i001",
                "name": "Ride 1",
                "start_date_local": "2026-05-29",
                "type": "Ride",
                "duration": 3600,
                "distance": 40000,
                "load": 150,
                "avg_watts": 250,
                "max_watts": 900,
            },
            {
                "id": "i002",
                "name": "Run 1",
                "start_date_local": "2026-05-28",
                "type": "Run",
                "duration": 1800,
                "distance": 6000,
                "load": 80,
                "avg_hr": 160,
                "max_hr": 175,
                "has_heartrate": True,
            },
        ]

        result = project_and_prune_list(items, include=["HEADLINE"], taxonomy=MINIMAL_TAXONOMY)

        assert len(result) == 2

        # First item: Ride
        assert set(result[0].keys()) == {"id", "name", "start_date_local", "type", "duration", "distance", "load"}
        assert result[0]["id"] == "i001"
        # POWER fields should not be included (not in HEADLINE)
        assert "avg_watts" not in result[0]

        # Second item: Run
        assert set(result[1].keys()) == {"id", "name", "start_date_local", "type", "duration", "distance", "load"}
        assert result[1]["id"] == "i002"
        # HR fields should not be included
        assert "avg_hr" not in result[1]
