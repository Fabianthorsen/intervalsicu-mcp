# Intervals.icu API reference

Quick reference for the upstream API this server wraps. For the tools *this server*
exposes, see the tables in the [README](../README.md).

## API

- **Base:** `https://intervals.icu/api/v1/`
- **Spec:** OpenAPI 3.0.1 @ `https://intervals.icu/api/v1/docs` (fetchable live)
- **115 paths / 146 operations**

## Auth

- **APIKey** (HTTP Basic): username = `API_KEY`, password = your key from `/settings`. Personal/script use.
- **AccessToken** (Bearer): OAuth token. Multi-athlete use.

## Endpoint groups (by operation count)

| # | Tag | What |
|---|-----|------|
| 52 | Activities | CRUD activities, streams, intervals, power/HR curves, maps, FIT, photos |
| 19 | Library | Workouts and folders (CRUD) |
| 16 | Events | Calendar — workouts, notes, races, targets |
| 10 | Chats | Athlete-coach messages |
| 10 | Sports | Zones, FTP, per-sport settings |
| 9 | Gear | Bikes, shoes, components |
| 8 | Athletes | Profile, settings |
| 7 | Custom Items | Custom fields |
| 6 | Wellness | HRV, weight, sleep, CTL/ATL |
| 4 | Routes | Saved routes |
| 3 | Weather | Forecast data |
| 1 | Shared Events | Shared calendar |
| 1 | OAuth | Token endpoint |

## Notes

- REST conventions: GET list, POST create, PUT/GET by id, DELETE.
- The calendar (`Events`) and library (`Workouts`) PUT/POST bodies share the `EventEx`
  schema (64 fields) — most update tools take a subset of it.
