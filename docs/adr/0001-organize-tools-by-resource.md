# Organize tools by resource, not by self-vs-coached

Tools are grouped by the **resource** they act on (athletes, activities, events, workout library, wellness, gear), not by whether they target yourself or an athlete you coach.

There is no "coaching" module. Every athlete-keyed endpoint behaves identically whether the athlete id is `"0"` (the authenticated user) or a coached athlete's id, so "coaching" is not a distinct concept — it is just operating on a non-`"0"` `athlete_id` (see CONTEXT.md → Athlete). The old role-oriented split produced genuine duplication: `update_athlete_event` existed twice with conflicting signatures (a real name collision), and `list_events`/`list_athlete_events` were near-identical.

Consequence: tools that read as "coaching actions" live with their resource — e.g. `set_coach_evaluation` and `post_activity_message` live in `activities.py` because they act on an Activity. A reader expecting a coaching module won't find one; this is deliberate.

Considered: keeping the self/coached split (rejected — it duplicates code and invites the same collision again) and a minimal collision-only fix (rejected — leaves the incoherent layout in place).
