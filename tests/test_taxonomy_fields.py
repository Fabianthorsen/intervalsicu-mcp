"""Every taxonomy field must exist on the API schema it shapes.

Field groups are hand-written, so a typo or an invented field name silently
prunes to nothing — the tool returns core fields only and looks merely sparse
rather than broken. That is how athletes.ZONES shipped returning 0 of 19 fields
and gear.MAINTENANCE 0 of 3.

This guard reads the checked-in OpenAPI spec rather than calling the API: it
needs no credentials, runs offline in CI, and is deterministic. Behavioural
checks against the live API live in the integration tests.
"""

import json
from pathlib import Path

import pytest

from activities import ACTIVITY_TAXONOMY
from athletes import ATHLETE_TAXONOMY
from events import EVENT_TAXONOMY
from gear import GEAR_TAXONOMY
from shaping import CORE_FIELDS
from wellness import WELLNESS_TAXONOMY

SPEC_PATH = Path(__file__).parent.parent / "openapi-spec.json"

# taxonomy -> the OpenAPI schema whose objects the tools actually shape.
TAXONOMIES = {
    "activities": (ACTIVITY_TAXONOMY, "Activity"),
    "athletes": (ATHLETE_TAXONOMY, "WithSportSettings"),
    "events": (EVENT_TAXONOMY, "Event"),
    "gear": (GEAR_TAXONOMY, "Gear"),
    "wellness": (WELLNESS_TAXONOMY, "Wellness"),
}

# Fields the tools derive rather than read from the API, so they are absent from
# the schema by design. Keep this list short and justified.
DERIVED_FIELDS = {
    ("wellness", "tsb"),  # ctl - atl; the API returns the components, not the result
}


def _schema_properties(name: str) -> set[str]:
    spec = json.loads(SPEC_PATH.read_text())
    schema = spec["components"]["schemas"][name]
    return set(schema.get("properties", {}))


@pytest.mark.parametrize("resource", sorted(TAXONOMIES))
def test_taxonomy_fields_exist_in_schema(resource: str) -> None:
    taxonomy, schema_name = TAXONOMIES[resource]
    properties = _schema_properties(schema_name)

    unknown = {
        f"{group}.{field}"
        for group, fields in taxonomy.items()
        for field in fields
        if field not in properties and (resource, field) not in DERIVED_FIELDS
    }

    assert not unknown, (
        f"{resource} taxonomy references fields absent from the {schema_name} "
        f"schema: {sorted(unknown)}. These prune to nothing at runtime."
    )


@pytest.mark.parametrize("resource", sorted(TAXONOMIES))
def test_no_group_is_entirely_derived_or_empty(resource: str) -> None:
    """A group that resolves to nothing is dead weight in the tool's docstring."""
    taxonomy, _ = TAXONOMIES[resource]
    empty = [group for group, fields in taxonomy.items() if not fields]
    assert not empty, f"{resource} has empty field groups: {empty}"


@pytest.mark.parametrize("resource", sorted(TAXONOMIES))
def test_groups_do_not_restate_core_fields(resource: str) -> None:
    """Core fields ship unconditionally; repeating them in a group is misleading."""
    taxonomy, _ = TAXONOMIES[resource]
    # `name` and `type` are core but also genuinely headline data, so only flag
    # the identity fields that a group could never sensibly own.
    identity = {"id", "start_date_local"} & CORE_FIELDS
    offenders = {
        f"{group}.{field}"
        for group, fields in taxonomy.items()
        for field in fields
        if field in identity
    }
    assert not offenders, f"{resource} groups restate core fields: {sorted(offenders)}"
