# Intervals.icu MCP

An MCP server exposing Intervals.icu training data and coaching actions to an LLM. The language below is the shared vocabulary for the domain it models.

## Language

**Athlete**:
A person with an Intervals.icu account, identified by an athlete id. The id `"0"` always means the currently authenticated user. A person you coach is simply an Athlete with a non-`"0"` id — *not* a distinct kind of thing.
_Avoid_: "Coached athlete" as a separate concept, "user", "client".

**Activity**:
A recorded, completed training session with measured data (power, HR, pace, TSS), identified by an id like `i129230824`. The past.
_Avoid_: "workout" when you mean a completed session.

**Event**:
An item on an Athlete's calendar, identified by an event id. It is *planned*, not recorded. Every Event has a category — the two that matter here are `WORKOUT` (a planned session) and `NOTE`. The future.
_Avoid_: "activity" for a planned item.

**Workout**:
A reusable, structured training template stored in the library (organised in folders). Scheduling a Workout *copies* it onto the calendar as a `WORKOUT` Event — the template and the resulting Event are distinct things.
_Avoid_: conflating the library template with the calendar Event it produces.

**Note**:
An Event with category `NOTE` — non-training calendar context such as a rest day, travel, or illness.
