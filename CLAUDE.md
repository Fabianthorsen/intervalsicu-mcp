# Project guidance for Claude Code

## Commit message format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>
```

**Types:**
- `feat` — new feature or tool
- `refactor` — code restructuring, no behavior change
- `fix` — bug fix
- `test` — test addition or update
- `docs` — documentation, ADRs, CONTEXT.md

**Scope** — the resource or module affected (optional but recommended):
- `shaping` — the shaping module
- `curves` — the curves module
- `wellness`, `activities`, `athletes`, `events`, `gear` — resource tools
- `adr` — architectural decision records
- `context` — CONTEXT.md glossary

**Examples:**

```
feat(shaping): implement project_and_prune module with pruning

Deliver core shaping logic: project to requested groups, always include
core fields (id/name/date/type), prune empties (null/[]/''/{}) while
preserving 0 and false.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

```
refactor(activities): apply shaping to get_activity with include param

Add ActivityFields enum (12 groups + ALL), default to core+HEADLINE,
integrate shaping module.
```

```
test(shaping): unit tests for group selection and emptiness pruning
```

**Commit body** — explain the *why* and any non-obvious decisions. Keep commit messages terse; use the PR description or issue for detailed rationale.

## Testing

- **Pure modules** (`shaping`, `curves`) — unit tests with literal inputs, no mocks or network
- **Tools** — integration tests hitting the real intervals.icu API (requires `.env` with `INTERVALS_API_KEY`)
- See `tests/` and `pyproject.toml` for test setup

Run tests: `uv run pytest tests/ -v`

## Architecture

Read `CONTEXT.md` for the domain glossary (Athlete, Activity, Event, Workout, Note, Best-effort curve).

Read `docs/adr/` for architectural decisions:
- `0001-organize-tools-by-resource.md` — tools grouped by resource, not by self-vs-coached
- `0002-shape-read-responses-with-field-groups.md` — read responses use semantic field groups + pruning
- `0003-compute-server-side-never-expose-streams.md` — server-compute and sample; never raw streams

## Adding a new read tool

1. Define a `<Resource>Fields` enum with semantic groups in the resource module
2. Fetch from the API
3. Call `shaping.project_and_prune(resp, include=[...], taxonomy=<Resource>_TAXONOMY)`
4. Return the shaped response
5. Add integration test hitting the real API

Example: see `wellness.py` (the proof-of-concept) or `activities.py` (the big taxonomy).
