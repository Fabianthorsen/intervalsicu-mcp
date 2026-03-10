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

### Athlete
| Tool | Description |
|------|-------------|
| `get_athlete` | Profile, FTP, resting HR, weight, gear |

### Activities
| Tool | Description |
|------|-------------|
| `list_activities` | Recent activities in descending date order |
| `get_activity_intervals` | Analysed intervals with power, HR, pace, TSS |
| `get_activity_streams` | Raw time-series data (power, HR, speed, cadence) |

### Wellness & Fitness
| Tool | Description |
|------|-------------|
| `get_wellness` | Daily CTL, ATL, TSB, HRV, sleep, resting HR, weight |

### Gear
| Tool | Description |
|------|-------------|
| `list_gear` | Bikes, shoes and components with usage and maintenance reminders |

### Calendar & Planning
| Tool | Description |
|------|-------------|
| `list_events` | Planned workouts, notes and races on the calendar |
| `get_event` | Single event by ID |
| `create_note` | Add a note to the calendar (rest day, travel, illness, race trip) |
| `delete_event` | Remove an event from the calendar |
| `get_training_plan` | Current training plan |
| `list_workouts` | Workout library |

### Coaching
| Tool | Description |
|------|-------------|
| `list_coached_athletes` | Athletes you coach with recent training summaries |
| `list_athlete_events` | Planned events on a coached athlete's calendar |
| `list_athlete_activities` | Recent activities for a coached athlete |
| `update_athlete_event` | Update a planned event on a coached athlete's calendar |
| `set_coach_evaluation` | Set evaluation tick: 1=WTF 2=POOR 3=SEEN 4=GOOD 5=AMAZING |
| `post_activity_message` | Post a feedback comment on an activity |

## Tips & Example Workflows

### Review a workout

Paste this prompt into your Claude Project Instructions (or use it directly) to get a structured workout review with an evaluation tick and coaching message:

```
Analyse a workout and post feedback. Follow these steps in order:

1. **Identify the activity** — if I say "latest", call list_activities_between_dates with oldest=14 days ago and newest=today, then pick the most recent. Otherwise use the activity ID I provide.

2. **Fetch the activity** — call get_activity and get_activity_intervals in parallel to get summary stats (TSS, distance, duration, avg HR/power) and interval breakdown (targets vs actuals, power zones, HR drift).

3. **Check existing messages** — inspect any existing comments to avoid duplicating feedback.

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

Tests hit the real API and require valid credentials in `.env`. Write tests clean up after themselves.
