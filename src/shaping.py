"""Response shaping: project to field groups and prune empties (ADR-0002)."""


CORE_FIELDS = {"id", "name", "start_date_local", "type"}


def project_and_prune(obj: dict, include: list[str], taxonomy: dict) -> dict:
    """Project an object to requested groups + core, then prune empties.

    Args:
        obj: Raw API object
        include: List of group names from taxonomy (e.g. ['HEADLINE', 'POWER'])
        taxonomy: Dict mapping group name -> list of field names

    Returns:
        Shaped and pruned object with only selected fields + core.
    """
    # Collect all field names for requested groups
    selected_fields = set(CORE_FIELDS)
    for group in include:
        if group == "ALL":
            # ALL means return all fields from the object
            return _prune(obj)
        if group in taxonomy:
            selected_fields.update(taxonomy[group])

    # Project to selected fields
    projected = {k: v for k, v in obj.items() if k in selected_fields}

    # Prune empties
    return _prune(projected)


def project_and_prune_list(
    items: list[dict], include: list[str], taxonomy: dict
) -> list[dict]:
    """Shape a list of objects element-wise.

    Args:
        items: List of raw API objects
        include: List of group names
        taxonomy: Group -> field mapping

    Returns:
        List of shaped and pruned objects.
    """
    return [project_and_prune(item, include, taxonomy) for item in items]


def _prune(obj: dict) -> dict:
    """Remove empty values: null, [], '', {}. Keep 0 and False."""
    return {
        k: v
        for k, v in obj.items()
        if v is not None and v != [] and v != "" and v != {}
    }
