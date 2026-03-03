# intervals.icu MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes [intervals.icu](https://intervals.icu) training data to Claude, enabling AI-assisted coaching and training analysis.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An intervals.icu account with an API key

## Setup

1. Clone the repo and install dependencies:
   ```bash
   uv sync
   ```

2. Create a `.env` file in the project root:
   ```
   INTERVALS_API_KEY=your_api_key_here
   INTERVALS_ATHLETE_ID=i123456
   ```
   Your API key is found in intervals.icu under **Settings → API**.

## Claude Desktop

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

## Running Tests

```bash
uv run pytest tests/ -v
```

Tests hit the real API and require valid credentials in `.env`. Write tests clean up after themselves.
