# intervals.icu MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes [intervals.icu](https://intervals.icu) training data to Claude, enabling AI-assisted coaching and training analysis.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An intervals.icu account with an API key

## Local setup (stdio)

1. Clone the repo and install dependencies:
   ```bash
   git clone https://github.com/your-username/intervalsicu-mcp
   cd intervalsicu-mcp
   uv sync
   ```

2. Create a `.env` file in the project root:
   ```
   INTERVALS_API_KEY=your_api_key_here
   ```
   Your API key is found in intervals.icu under **Settings → API**.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Restart Claude Desktop after saving.

### Claude Code

```bash
claude mcp add intervals-icu -- uv --directory /path/to/intervalsicu-mcp run python src/server.py
```

## Remote deployment (Fly.io + GitHub OAuth)

The server supports a remote HTTP deployment with GitHub OAuth so you can restrict access to specific GitHub users.

### 1. Create a GitHub OAuth App

Go to GitHub → Settings → Developer settings → OAuth Apps → New OAuth App:
- **Homepage URL:** `https://your-app-name.fly.dev`
- **Authorization callback URL:** `https://your-app-name.fly.dev/auth/github/callback`

### 2. Generate a JWT signing key

```bash
openssl rand -hex 32
```

### 3. Create the Fly.io app

```bash
brew install flyctl   # or see https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly apps create your-app-name
```

Update the `app` field in `fly.toml` if you changed the name.

### 4. Set secrets

```bash
fly secrets set \
  INTERVALS_API_KEY=your_intervals_api_key \
  GITHUB_CLIENT_ID=your_github_client_id \
  GITHUB_CLIENT_SECRET=your_github_client_secret \
  JWT_SIGNING_KEY=your_generated_key \
  ALLOWED_GITHUB_USERS=yourgithubusername,otherusername
```

`ALLOWED_GITHUB_USERS` is a comma-separated list of GitHub usernames that are allowed to connect.

### 5. Deploy

```bash
fly deploy
```

### 6. Connect to the remote server

Use `https://your-app-name.fly.dev` as the MCP server URL in your client.

### Automated deployment via GitHub Actions

Pushing to `main` triggers automatic deployment. Add your Fly.io token as a repository secret:

- Secret name: `FLY_API_TOKEN`
- Get the token: `fly tokens create deploy`

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

## Running Tests

```bash
uv run pytest tests/ -v
```

Unit tests for the pure modules (`shaping`, `curves`, `windows`, taxonomies) run offline with no
credentials. Integration tests hit the real API and need `INTERVALS_API_KEY` in `.env`; write tests
clean up after themselves.

`tests/test_taxonomy_fields.py` checks every field group against `openapi-spec.json`. Field groups are
hand-written, and a name that does not exist on the schema prunes to nothing at runtime — the tool
looks sparse rather than broken. Run it after editing any taxonomy.

If requests fail TLS verification behind a corporate proxy, `conftest.py` injects `truststore` so
Python uses the OS trust store instead of certifi's bundle.
