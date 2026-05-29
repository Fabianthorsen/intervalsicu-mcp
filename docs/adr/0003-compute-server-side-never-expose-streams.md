# Compute server-side and sample; never expose raw data streams

An Activity's underlying data is a per-second stream — a 5-hour ride is ~18,000 power
samples, plus parallel HR/cadence/altitude streams. Two tempting designs both fail the
token goal catastrophically: exposing the raw `/streams` endpoint as a tool, or having
the AI derive metrics (e.g. a power curve) from raw samples it pulled into context. Both
flood the context window with thousands of numbers, and the second also forces the model
into unreliable, expensive arithmetic over them.

intervals.icu already computes derived analytics server-side — mean-max curves, zone
times, best efforts, interval summaries. So:

- Tools surface **server-computed summaries sampled to canonical points**, never the
  underlying stream. The curve tools (`get_power_curve`, `get_activity_curve`) return
  values at a fixed set of durations (`5s, 15s, 30s, 1m, 2m, 5m, 8m, 20m, 60m`), not the
  per-second array the server derived them from.
- The `/streams` endpoint is **deliberately not exposed** as a tool.
- Trivial client-side math over already-summarised values is fine — e.g. computing W/kg
  as watts/weight across nine curve points. The line is: arithmetic over a handful of
  summary values is acceptable; crunching raw streams is not.

Consequence: when a new metric is needed, prefer an existing server-side endpoint that
returns it pre-computed over fetching streams and deriving it. If intervals.icu doesn't
compute it, that is a strong signal to reconsider exposing it at all rather than to reach
for the stream. This is the data-volume companion to ADR-0002's field-group shaping:
0002 trims *which fields* of an object ship; 0003 governs *whether raw time-series data*
ships at all.
