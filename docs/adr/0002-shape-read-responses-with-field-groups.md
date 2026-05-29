# Shape read responses with semantic field groups and emptiness pruning

intervals.icu returns very large objects (an `Activity` has 173 fields, an `Athlete`
152, a `Wellness` record 46), and most are null for any given record because the API
returns the full shape regardless of sport. Read tools were raw passthrough
(`return resp.json()`) everywhere except `wellness`, which alone projected a fixed
field whitelist. The result was both pains at once: passthrough reads flooded the
context window, while the one shaped tool risked dropping fields the AI needed.

We shape read responses with a single convention:

1. **Semantic field groups, not raw fields.** Single-resource `get_*` tools take an
   `include=[...]` parameter typed as a per-resource enum of *concept* groups
   (`POWER`, `HR`, `PACE`, `ZONES`, `ELEVATION`, `WEATHER`, `FUELING`, `COMPLIANCE`,
   `COACHING`, …). Groups are short (~10 members), so the enum is cheap in the tool
   schema, legible to the AI (it asks for concepts), and stable against API field
   renames. An `ALL` member returns the raw object as a last-resort escape hatch so no
   field is ever unreachable; its docstring steers callers to named groups first.
2. **Core + headline default.** Omitting `include` returns a small `core`
   (`id`, `name`, `start_date_local`, `type`) — always present on every response — plus
   a `headline` group (duration, distance, load: enough to judge a session at a glance).
3. **Lists stay fixed-lean.** List tools (`list_activities_between_dates`, `list_events`,
   …) return core + headline with **no** selector. This matches the intended workflow —
   list to find the id, then `get_*` to drill in — and avoids a groups×N re-bloat.
4. **Emptiness pruning.** A universal post-filter drops `null`, `[]`, `''`, and `{}` from
   every response. Numeric `0` and `false` are kept — they are real measurements (0 W
   average, `has_heartrate: false`) and dropping them would hide diagnostic data. Pruning
   runs *after* group selection, which is what makes `ALL` cheap (a Run's ~60 null power
   fields never ship) and lets group definitions be generous supersets.

Considered and rejected:
- **Free-form `fields=['name']`** — the AI can't discover field names, the list is
  brittle against renames, and ~150 names tax every session's schema.
- **`detail='summary'|'full'` toggle** — too coarse; can't ask for HR-without-power.
- **`include` on list tools** — re-creates the bulky-read pain (groups × many items)
  to save round-trips, which were not a felt pain.
- **Aggressive pruning of `0`/`false`** — leanest, but makes a genuine zero
  indistinguishable from an absent field in a tool where zeros are diagnostic.

Consequence: the per-resource group taxonomies (which raw fields map to which group)
live in code as enums beside each tool, not in this ADR.
