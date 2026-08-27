# intervals.icu MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes [intervals.icu](https://intervals.icu) training data to Claude, enabling AI-assisted coaching and training analysis.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An intervals.icu account with an API key

Runs on macOS, Linux and Windows. The deployment script (`scripts/deploy_fly.sh`) needs
a bash shell, so on Windows run it under WSL or Git Bash — or follow the secrets table
in that section by hand.

## Quick start

```bash
git clone git@github.com:Fabianthorsen/intervalsicu-mcp.git
cd intervalsicu-mcp
uv sync                                    # creates .venv, installs everything
uv run python scripts/check_setup.py       # creates .env, then tells you what is missing
```

The first run creates `.env` and stops, because the API key is blank. Paste your key —
it is at intervals.icu under **Settings → Developer Settings** — and run the check again.

`check_setup.py` verifies the key is set, that intervals.icu accepts it, and that the
server imports with every tool mounted. It then prints the config for the two clients
below **with your absolute paths already filled in**, ready to paste.

No GitHub OAuth credentials are needed for a local run — auth only switches on for the
remote deployment, when those variables are present.

### Claude Code

Run the command `check_setup.py` prints, which is this with real paths:

```bash
claude mcp add intervals-icu -- /path/to/uv --directory /path/to/intervalsicu-mcp run python src/server.py
```

Note that the checked-in `.mcp.json` points at the maintainer's hosted server on Fly.io,
which is restricted to an allowlist of GitHub users. Use the command above to run your
own local copy instead.

### Claude Desktop

Merge the JSON `check_setup.py` prints into your `claude_desktop_config.json`, then
restart Claude Desktop. The script prints the path for your OS; it is
`~/Library/Application Support/Claude/` on macOS, `%APPDATA%\Claude\` on Windows, and
`~/.config/Claude/` on Linux. The JSON looks like this:

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "/path/to/uv",
      "args": [
        "--directory", "/path/to/intervalsicu-mcp",
        "run", "python", "src/server.py"
      ]
    }
  }
}
```

Both paths must be absolute — Claude Desktop does not inherit your shell PATH, so a bare
`uv` fails with `command not found`. That is why the script resolves them for you (on
Windows that means the full `...\uv.exe` path, correctly escaped for JSON).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `KeyError: 'INTERVALS_API_KEY'` or every test skips | No `.env` in the project root, or the key line is empty. |
| `401`/`403` from intervals.icu | Key is wrong or revoked — generate a new one under Settings → Developer Settings. |
| Redirect to `blocked.*` / `CERTIFICATE_VERIFY_FAILED` | A corporate proxy is blocking or TLS-intercepting intervals.icu. Try another network; the test suite already uses `truststore` so the OS keychain supplies intercepting root CAs. |
| `uv: command not found` in Claude Desktop | Use the absolute path (`which uv`, or `where uv` on Windows) — `check_setup.py` prints it for you. |
| `deploy_fly.sh: command not found` on Windows | It is a bash script — run it under WSL or Git Bash, or set the secrets by hand. |

## Remote deployment (Fly.io + GitHub OAuth)

The server can also run as a remote HTTP deployment behind GitHub OAuth, so only an
allowlist of GitHub users can connect.

```bash
brew install flyctl   # macOS; other platforms: https://fly.io/docs/flyctl/install/
fly auth login
./scripts/deploy_fly.sh
```

On Windows, or anywhere without bash, run the Python port instead — it does the same
thing:

```powershell
uv run python scripts/deploy_fly.py
```

Add `--dry-run` to walk the whole flow and see every value and command without
creating, changing or deploying anything.

The script creates the app and its volume, prints the exact Homepage and callback URLs
to paste into a new GitHub OAuth App, generates a `JWT_SIGNING_KEY`, sets every secret,
and deploys. It keeps the app name consistent across `fly.toml`, the callback URL and
`PUBLIC_BASE_URL` — a mismatch there is the usual cause of a failing OAuth round-trip.

It is safe to re-run: existing apps, volumes and signing keys are left alone (rotating
the signing key would invalidate every issued token), and nothing is created or deployed
until you confirm. Re-run it to change the allowlist.

Once deployed, use `https://your-app-name.fly.dev/mcp` as the MCP server URL in your
client.

### What it sets, if you prefer doing it by hand

| Secret | Purpose |
| --- | --- |
| `INTERVALS_API_KEY` | intervals.icu API access |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | From the GitHub OAuth App |
| `JWT_SIGNING_KEY` | `openssl rand -hex 32` |
| `ALLOWED_GITHUB_USERS` | Comma-separated GitHub usernames allowed to connect |
| `PUBLIC_BASE_URL` | `https://your-app-name.fly.dev` — must match the OAuth callback host |
| Callback URL | Not a secret — set `https://your-app-name.fly.dev/auth/callback` as the OAuth App's Authorization callback URL |

GitHub auth switches on only when `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and
`JWT_SIGNING_KEY` are all set. To keep a missing secret from quietly exposing the
server, it refuses to start on a network transport unless all three are present.

### Automated deployment via GitHub Actions

Pushing to `main` deploys automatically. Add your Fly token as the repository secret
`FLY_API_TOKEN`, from `fly tokens create deploy`.

## Tools

Read tools take an `include` list of semantic field groups and default to a headline set — see [ADR-0002](docs/adr/0002-shape-read-responses-with-field-groups.md).

### Athletes
| Tool | Description |
|------|-------------|
| `get_athlete` | Profile, weight, resting HR, timezone. `include=['ZONES']` adds per-sport thresholds |
| `list_coached_athletes` | Athletes you coach |
| `get_sport_settings` | Full training zones and thresholds for a sport (FTP, LTHR, max HR, zone boundaries) |
| `update_sport_settings` | Change thresholds or zones for a sport. Affects future analysis only |
| `apply_sport_settings` | Recalculate past activities against current zones — destructive, run only on request |

### Activities
| Tool | Description |
|------|-------------|
| `list_activities_between_dates` | Recent activities in date range, descending order (default: last 14 days) |
| `get_activity` | Full details for a single activity (power, HR, TSS, pace, elevation, load) |
| `get_activity_intervals` | Analysed intervals per activity with power, HR, pace, TSS, targets vs actuals |
| `get_activity_messages` | Comments/feedback on an activity (athlete and coach) |
| `set_coach_evaluation` | Set evaluation tick on activity: 1=WTF 2=POOR 3=SEEN 4=GOOD 5=AMAZING |
| `post_activity_message` | Post coaching feedback comment on activity |
| `search_activities` | Find activities by name, or by tag with a `#` prefix, across all history |
| `get_activity_window_metrics` | NP, IF, TSS, VI, decoupling, avg HR/cadence for any time window in an activity |
| `get_power_curve` | Best-effort power curve for an athlete over a date window |
| `get_activity_curve` | Best-effort power/HR/pace curve within one activity |

### Wellness
| Tool | Description |
|------|-------------|
| `get_wellness` | Daily records: CTL/ATL/TSB, HRV, resting HR, sleep, weight, plus `SUBJECTIVE` and `NUTRITION` groups |
| `update_wellness` | Record weight, HRV, sleep, self-reported fatigue/soreness/mood, calories and macros for a day |

### Gear
| Tool | Description |
|------|-------------|
| `list_gear` | Bikes, shoes, components with total usage, activity count, maintenance reminders |

### Calendar & Events
| Tool | Description |
|------|-------------|
| `list_events` | Planned events (workouts, notes, races) on calendar by date range (default: 7 days ahead) |
| `get_event` | Single event by ID |
| `create_note` | Add a note to calendar (rest day, travel, illness, race trip, etc.) |
| `create_workout` | Create inline workout event directly on calendar |
| `schedule_workout` | Schedule a workout from the library onto calendar |
| `update_event` | Update event (name, date, description, type, targets, visibility, etc.) |
| `delete_event` | Remove event from calendar |
| `get_training_plan` | Current training plan |

### Workout Library
| Tool | Description |
|------|-------------|
| `list_workout_folders` | Folders in the workout library (nested structure with workouts as children) |
| `create_workout_folder` | Create a new folder in the workout library |
| `create_workout_in_folder` | Create a workout inside a folder (text format or file upload: .zwo/.mrc/.erg) |
| `update_workout` | Update a library workout (name, description, targets, duration, type, etc.) |
| `delete_workout` | Delete a workout from the library |

### Chats
| Tool | Description |
|------|-------------|
| `list_chats` | Coach/athlete conversations, most recently active first, with unread counts |
| `get_chat_messages` | Messages in a chat, most recent first |
| `send_chat_message` | Send a message. One-to-one chats only; group chats are refused |

## Tips & Example Workflows

### Review a workout

Paste this prompt into your Claude Project Instructions (or use it directly) to get a structured workout review with an evaluation tick and coaching message:

```
Analyse a workout and post feedback. Follow these steps in order:

1. **Identify the activity** — if I say "latest", call list_activities_between_dates with oldest=14 days ago and newest=today, then pick the most recent. Otherwise use the activity ID I provide.

2. **Fetch the activity** — call get_activity and get_activity_intervals in parallel to get summary stats (TSS, distance, duration, avg HR/power) and interval breakdown (targets vs actuals, power zones, HR drift).

3. **Check existing messages** — call get_activity_messages to inspect any existing comments and avoid duplicating feedback.

4. **Assess the workout** — did the athlete hit targets? Were intervals consistent? Call get_wellness with days=7 if load context (CTL/ATL/TSB) would help.

5. **Choose an evaluation tick** — call set_coach_evaluation:
   - 1 = WTF, 2 = POOR, 3 = SEEN, 4 = GOOD, 5 = AMAZING

6. **Post a feedback message** — call post_activity_message with 2–4 sentences: what went well, one concrete observation or suggestion. Direct, encouraging, specific — not generic praise.

7. **Summarise** — report back the activity ID, tick given, and message posted.
```

**Usage examples:**
- *"Review latest workout"*
- *"Review workout i129230824"*

### Claude Code slash command

If you use Claude Code (CLI), save the prompt above as `~/.claude/commands/review-workout.md` for a `/review-workout latest` slash command available in every project.

## Development

```bash
uv run pytest tests/ -v                                        # full suite
uv run pytest tests/test_shaping.py tests/test_curves.py -v    # pure units, no network
uv run mypy src
```

Unit tests for the pure modules (`shaping`, `curves`, `windows`, taxonomies) run offline with no
credentials. Integration tests hit the real API, skip automatically when `INTERVALS_API_KEY` is
unset, and clean up after themselves.

`tests/test_taxonomy_fields.py` checks every field group against `openapi-spec.json`. Field groups are
hand-written, and a name that does not exist on the schema prunes to nothing at runtime — the tool
looks sparse rather than broken. Run it after editing any taxonomy.

If requests fail TLS verification behind a corporate proxy, `conftest.py` injects `truststore` so
Python uses the OS trust store instead of certifi's bundle.

Further reading: `CLAUDE.md` for commit conventions and how to add a new tool, `CONTEXT.md` for the
domain glossary, and `docs/adr/` for the design decisions behind the tool layout and response shaping.
