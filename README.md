# intervals.icu MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes [intervals.icu](https://intervals.icu) training data to Claude, enabling AI-assisted coaching and training analysis.

## Which setup do you want?

There are two ways to run this, and they solve different problems. Pick one and follow
that walkthrough end to end — each is self-contained.

| | **Local** | **Remote** |
| --- | --- | --- |
| Runs on | Your machine, started by your MCP client | A Fly.io app, always on |
| Good for | One person, one computer | Using it from phone/web, or sharing with a few people |
| Auth | None needed — it is already your machine and your key | GitHub OAuth, restricted to an allowlist you control |
| Works with | Claude Code, Claude Desktop | Claude Code, Claude Desktop, claude.ai |
| Costs | Nothing | A Fly.io account (a 256MB machine, which is cheap but not free) |
| Setup time | ~5 minutes | ~20 minutes, mostly the GitHub OAuth app |

Both need an intervals.icu API key. Get it now, from intervals.icu →
**Settings → Developer Settings**; every path below asks for it.

- [Zero to hero: local](#zero-to-hero-local)
- [Zero to hero: remote on Fly.io](#zero-to-hero-remote-on-flyio)

---

## Zero to hero: local

Runs the server on your own machine over stdio. Your MCP client starts and stops it for
you; nothing listens on a network port and no auth is involved.

**You need:** Python 3.12+, [uv](https://docs.astral.sh/uv/), and your intervals.icu API
key. Works on macOS, Linux and Windows.

### 1. Clone and install

```bash
git clone git@github.com:Fabianthorsen/intervalsicu-mcp.git
cd intervalsicu-mcp
uv sync
```

`uv sync` creates `.venv` and installs every dependency. You never need to activate it —
`uv run` handles that.

### 2. Run the setup check

```bash
uv run python scripts/check_setup.py
```

The first run creates a `.env` file and stops, because the API key is blank. This is
expected.

### 3. Paste your API key

Open `.env` and fill in the one line that matters:

```
INTERVALS_API_KEY=your-key-here
```

Leave everything else commented out — those are only for the remote deployment.

### 4. Run the check again

```bash
uv run python scripts/check_setup.py
```

This time it verifies three things in order: the key is set, intervals.icu actually
accepts it, and the server imports with every tool mounted. If all three pass, it prints
ready-to-paste client config **with your absolute paths already filled in**. Keep that
output on screen for the next step.

If it fails, jump to [Troubleshooting](#troubleshooting) — the message names which of the
three checks broke.

### 5. Connect your client

**Claude Code** — run the command `check_setup.py` printed. It looks like this, but with
real paths:

```bash
claude mcp add intervals-icu -- /path/to/uv --directory /path/to/intervalsicu-mcp run python src/server.py
```

**Claude Desktop** — merge the JSON `check_setup.py` printed into
`claude_desktop_config.json`, then restart Claude Desktop. The script prints the path for
your OS; it is `~/Library/Application Support/Claude/` on macOS, `%APPDATA%\Claude\` on
Windows, and `~/.config/Claude/` on Linux.

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

Both paths must be absolute. Claude Desktop does not inherit your shell PATH, so a bare
`uv` fails with `command not found` — which is exactly why the script resolves them for
you (on Windows, the full `...\uv.exe` path, escaped for JSON).

### 6. Verify

Restart the client and ask it something only this server can answer:

> What was my training load last week?

If it calls `get_wellness` or `list_activities_between_dates` and comes back with your
own numbers, you are done.

> **On `.mcp.json`:** Claude Code reads a project-scoped MCP config from this file. It is
> gitignored rather than checked in, because the right contents are different for every
> person — a stdio command with your absolute paths for a local run, your own Fly URL for
> a remote one. The commands above create it for you; there is nothing to copy.

---

## Zero to hero: remote on Fly.io

Runs the server as an always-on HTTP deployment behind GitHub OAuth, so you (and anyone
you allowlist) can reach it from any client, including claude.ai on a phone.

**You need:** a [Fly.io](https://fly.io) account with billing set up, a GitHub account,
your intervals.icu API key, and `uv` for the setup script.

**Read this first.** The setup script is a single interactive run that pauses in the
middle to ask for GitHub OAuth credentials — a client ID and secret you get by
registering a GitHub OAuth App, which in turn needs your Fly app's URL. So the order
below is: pick your app name (step 4), start the script, and when it pauses and prints
the two URLs, leave it waiting while you register the OAuth App in another tab (step 6).
The script is happy to sit there. If you would rather do it up front, you can register
the OAuth App right after step 4 — the URLs are just `https://<your-app>.fly.dev` and
`https://<your-app>.fly.dev/auth/callback`.

### 1. Fork the repo

Fork it on GitHub, then clone **your fork** — the automatic-deploy step later needs a
repo you own.

```bash
git clone git@github.com:<your-username>/intervalsicu-mcp.git
cd intervalsicu-mcp
uv sync
```

### 2. Put your API key in `.env`

```bash
uv run python scripts/check_setup.py   # creates .env
```

Fill in `INTERVALS_API_KEY`. The deploy script reads it from here so you do not have to
paste it again; without it, the script just prompts you for it.

### 3. Install flyctl and log in

```bash
brew install flyctl          # macOS; others: https://fly.io/docs/flyctl/install/
fly auth login
```

### 4. Your app name (you can just accept the suggestion)

Fly app names are **globally unique** across all of Fly, so `intervalsicu-mcp` is taken —
by this project. You do not have to invent one. On a first run the script suggests
`intervalsicu-mcp-<random>` and you press enter to take it; type your own if you would
rather have something memorable. Later runs default to the name you already chose, so
re-running never renames your app.

The name becomes your URL (`https://<name>.fly.dev`) and has to match in three places;
the script keeps all three in sync. If the name turns out to be taken anyway — only
`fly apps create` can really tell — the script says so and offers another rather than
failing the run.

### 5. Run the deploy script

```bash
./scripts/deploy_fly.sh
```

On Windows, or anywhere without bash, run the Python port — it does the same thing:

```powershell
uv run python scripts/deploy_fly.py
```

Add `--dry-run` (Python version) to walk the entire flow and see every value and command
without creating, changing or deploying anything. Worth doing once if you want to see
what is coming.

The script then walks you through, in this order:

1. **App name** — suggests one, and renders `fly.toml` from `fly.toml.template` to
   match. A later run defaults to the name you already chose.
2. **Create the app** on Fly. If the name turns out to be taken, it offers another
   instead of failing the run.
3. **Create a 1GB volume**, which `fly.toml.template` mounts. Without it the first deploy
   starts and immediately dies.
4. **GitHub OAuth app** — it stops here and prints your exact Homepage and callback URLs.
   Go do step 6 now, in another tab.
5. **Secrets** — it generates a `JWT_SIGNING_KEY`, reads your API key from `.env`, shows
   you everything it is about to set, and waits for you to confirm.
6. **Deploy** — after another confirmation.
7. **Automatic deploys** — see step 8 below.

### 6. Create the GitHub OAuth App (while the script waits)

Open <https://github.com/settings/developers> → **New OAuth App** and copy the two URLs
the script just printed:

| Field | Value |
| --- | --- |
| Application name | Anything — `intervals-icu-mcp` is fine |
| Homepage URL | `https://<your-app>.fly.dev` |
| Authorization callback URL | `https://<your-app>.fly.dev/auth/callback` |

Register it, then **Generate a new client secret**. Copy the secret immediately — GitHub
shows it exactly once.

Back in the script, paste:

- the **Client ID**
- the **Client secret**
- **Allowed GitHub usernames**, comma-separated. This is your allowlist: anyone else who
  finds your URL and authenticates with GitHub is refused. Put your own username here,
  plus anyone you are sharing with.

The callback URL must match `https://<your-app>.fly.dev/auth/callback` character for
character. A mismatch here is the single most common cause of a failing OAuth round-trip,
which is why the script prints it rather than letting you reconstruct it.

### 7. Connect your client

Once the deploy finishes, your MCP server URL is `https://<your-app>.fly.dev/mcp`.

**Claude Code:**

```bash
claude mcp add --transport http intervals-icu https://<your-app>.fly.dev/mcp
```

Then run `/mcp` in Claude Code and authenticate. A browser opens, GitHub asks you to
authorize, and you land back on the callback URL.

**Claude Desktop or claude.ai:** add it as a custom connector using the same
`https://<your-app>.fly.dev/mcp` URL, and authenticate the same way.

The first connection from each user runs the OAuth flow once; after that the client holds
a token.

### 8. Turn on automatic deploys (optional)

At the end of its run, the script offers to wire up GitHub Actions so future changes
deploy themselves. Say yes and it creates a Fly deploy token scoped to just your app,
then uses the `gh` CLI to save it as the repository secret `FLY_API_TOKEN` and set the
repository variable `FLY_APP` to your app name.

One step is left that only you can do: **GitHub disables Actions on new forks.** Open
your fork's **Actions** tab and click *I understand my workflows, go ahead and enable
them*.

See [Automated deployment](#automated-deployment-via-github-actions) for the details.

### 9. Verify

Ask your client for something from your account. If it answers with your own training
data, you are done.

To check the server itself, `fly logs -a <your-app>` shows the request as it arrives, and
`fly status -a <your-app>` shows the machine running.

### Where each value lives

Nothing user-specific is committed. Each value sits in the one place that can actually
read it:

| Value | Lives in | Why there |
| --- | --- | --- |
| `INTERVALS_API_KEY`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `JWT_SIGNING_KEY`, `ALLOWED_GITHUB_USERS`, `PUBLIC_BASE_URL` | **Fly secrets**, set with `fly secrets set` | The running server reads them from its own environment. Keeping them out of GitHub means CI never handles them and a redeploy cannot clobber a value you changed with `fly secrets set`. |
| `FLY_API_TOKEN` | **GitHub repository secret** | Only CI needs it, and it is scoped to your one app. |
| `FLY_APP` (your app name) | **GitHub repository variable** | Per-fork, and not a secret. CI renders `fly.toml` from it. |
| Everything else in `fly.toml` — region, VM size, ports, mounts | **`fly.toml.template`**, committed | Shared config, identical for everyone. |

`fly.toml` itself is generated from the template and gitignored, so your fork carries no
diff against upstream and syncing never conflicts.

The one thing a GitHub variable cannot do is configure your laptop: `flyctl` needs a real
`fly.toml` on disk to read the region, VM size and mounts. That is why the app name is
rendered into a local file as well as stored as `FLY_APP` — same value, two places that
need it, one template they both come from. A fresh clone has no `fly.toml` until you run
the deploy script.

### Upgrading a fork you already deployed

Only applies if you forked **before** `fly.toml` became a generated file. Your fork has
its own committed `fly.toml`, so the first sync after this change stops on one conflict:

```
CONFLICT (modify/delete): fly.toml deleted in upstream and modified in HEAD.
```

Resolve it by untracking the file while keeping it on disk. It already names your app,
and it is byte-identical to what the template renders — so there is nothing to redo:

```bash
git rm --cached fly.toml
git commit
```

Your local `fly deploy` carries on unchanged. One step is left, and it is for CI only:
set the `FLY_APP` repository variable, since the workflow no longer has a tracked
`fly.toml` to read your app name from.

```bash
gh variable set FLY_APP --body "<your-app>"
```

Until you do, a deploy run fails with an explicit message rather than deploying somewhere
unexpected. This is a one-time migration — later syncs touch neither file, which is the
whole point of the change.

### Re-running the script

It is safe to run again, any time. Existing apps, volumes and signing keys are left alone
— rotating the signing key would invalidate every token already issued and log everyone
out — and nothing is created or deployed until you confirm. **Re-run it to change the
allowlist**, which is the usual reason to come back to it.

### What it sets, if you prefer doing it by hand

| Secret | Purpose |
| --- | --- |
| `INTERVALS_API_KEY` | intervals.icu API access |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | From the GitHub OAuth App |
| `JWT_SIGNING_KEY` | `openssl rand -hex 32` |
| `ALLOWED_GITHUB_USERS` | Comma-separated GitHub usernames allowed to connect |
| `PUBLIC_BASE_URL` | `https://your-app-name.fly.dev` — must match the OAuth callback host |
| Callback URL | Not a secret — set `https://your-app-name.fly.dev/auth/callback` as the OAuth App's Authorization callback URL |

Set them with `fly secrets set -a <your-app> KEY=value ...`, then `fly deploy -a
<your-app>`.

GitHub auth switches on only when `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and
`JWT_SIGNING_KEY` are all set. To keep a missing secret from quietly exposing the server,
it refuses to start on a network transport unless all three are present.

### Automated deployment via GitHub Actions

Pushing to `main` deploys automatically. The deploy script offers to set this up for you
(step 8 above). By hand, that is `fly tokens create deploy -a <your-app>`, saved as the
repository secret `FLY_API_TOKEN`.

Nothing user-specific is tracked in git. Your app name lives in the `FLY_APP` repository
variable and your Fly credentials in the `FLY_API_TOKEN` repository secret — both are
per-fork, both set for you by the deploy script. The workflow renders `fly.toml` from
`fly.toml.template` using `FLY_APP`, exactly as the script does locally, so a fork stays
identical to upstream and syncing never conflicts.

`FLY_APP` is therefore required in CI: with `fly.toml` untracked there is no app name to
fall back on. A run with `FLY_API_TOKEN` set but `FLY_APP` missing fails with an explicit
message rather than guessing.

**If you forked this repo**, three things are worth knowing:

- GitHub disables Actions on new forks. Open your fork's **Actions** tab once and click
  *I understand my workflows, go ahead and enable them*. Nobody can do this for you.
- Without `FLY_API_TOKEN`, the workflow exits cleanly instead of failing, so a fork you
  never deployed does not collect red Xs.
- Syncing your fork with the GitHub web button does not always raise a `push` event, so
  the deploy may not fire. Use the sync workflow below instead, or the deploy workflow's
  **Run workflow** button; syncing from a local clone triggers it normally.

### Keeping your fork up to date

`Sync fork with upstream` picks up new upstream commits and deploys them in one go. Open
your fork's **Actions** tab, choose that workflow, and click **Run workflow**. That is the
whole update: it syncs and deploys, and you see both in one run.

It is deliberately manual. Syncing pulls in upstream code and puts it straight on your
server, so it happens when you decide it does rather than on a timer. If you would rather
it were periodic, add a `schedule:` block to `.github/workflows/sync-fork.yml`.

It fast-forwards `main` only. If you have your own commits on `main` it stops, says so,
and changes nothing — it will never overwrite your work. It also deploys only when the
sync actually moved `main`, so an already-current fork does not redeploy for nothing.

The sync and the deploy happen in the same run on purpose. A fast-forward pushed by a
workflow does not raise a `push` event — GitHub suppresses that so workflows cannot
retrigger themselves — so a separate deploy run would never see it.

Like every workflow in a new fork, it does not appear until you enable Actions — the same
click as above.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `KeyError: 'INTERVALS_API_KEY'` or every test skips | No `.env` in the project root, or the key line is empty. |
| `401`/`403` from intervals.icu | Key is wrong or revoked — generate a new one under Settings → Developer Settings. |
| Redirect to `blocked.*` / `CERTIFICATE_VERIFY_FAILED` | A corporate proxy is blocking or TLS-intercepting intervals.icu. Try another network; the test suite already uses `truststore` so the OS keychain supplies intercepting root CAs. |
| `uv: command not found` in Claude Desktop | Use the absolute path (`which uv`, or `where uv` on Windows) — `check_setup.py` prints it for you. |
| `deploy_fly.sh: command not found` on Windows | It is a bash script — run it under WSL or Git Bash, or use `uv run python scripts/deploy_fly.py`. |
| Fly: "name is already taken" | App names are global across Fly. Pick a more specific one and re-run the script. |
| GitHub 404s on the authorize URL | The client ID is wrong, or has stray characters. Re-run the deploy script and paste it again — it strips invisible bytes that a terminal paste can smuggle in. |
| OAuth returns "redirect_uri mismatch" | The OAuth App's callback URL does not exactly match `https://<your-app>.fly.dev/auth/callback`. Fix it on GitHub, no redeploy needed. |
| Remote server refuses to start | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and `JWT_SIGNING_KEY` must all be set on a network transport. `fly logs -a <your-app>` names the missing one. |
| Authenticated, but every call is denied | Your GitHub username is not in `ALLOWED_GITHUB_USERS`. Re-run the deploy script to update the allowlist. |
| `fly deploy` says it cannot find `fly.toml` | It is generated and gitignored. Run the deploy script once to render it from `fly.toml.template`, or render it yourself with `sed 's/APP_NAME/<your-app>/' fly.toml.template > fly.toml`. |
| CI fails with "FLY_API_TOKEN is set but the FLY_APP repository variable is not" | Set `FLY_APP` to your app name under Settings → Secrets and variables → Actions → Variables, or re-run the deploy script and let it do it. |

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
