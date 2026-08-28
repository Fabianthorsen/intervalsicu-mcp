"""Set up and deploy the remote (HTTP + GitHub OAuth) server on Fly.io.

Run with: uv run python scripts/deploy_fly.py

Pass --dry-run to walk the whole flow and see every value and command without
creating, changing or deploying anything. Read-only flyctl calls still run, so
what it reports about the app is real.

Safe to re-run: it skips anything that already exists and re-prompts only for
what is missing. Nothing is created or deployed until you confirm.

This is the Python port of deploy_fly.sh, so Windows works without WSL or Git
Bash. Keep the two in sync, or delete one — a setup script that prints values
the server does not actually use is worse than no script at all.
"""

import getpass
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# fly.toml is generated from the template and gitignored, so a fork never carries
# a one-line app-name diff that conflicts on every upstream sync. The template
# holds the shared config; the app name is the one per-user value in it.
FLY_TOML = REPO_ROOT / "fly.toml"
FLY_TEMPLATE = REPO_ROOT / "fly.toml.template"

# The maintainer's own app. Everyone else needs a different name, because Fly
# app names are unique across all of Fly, not per account.
UPSTREAM_APP = "intervalsicu-mcp"


def bold(text: str) -> None:
    print(f"\033[1m{text}\033[0m")


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def scrub(value: str) -> str:
    """Strip control characters and surrounding whitespace.

    Pasting a client ID or secret into a terminal can smuggle in invisible bytes
    (a literal Ctrl-V arrives as \\x16); Fly stores them happily and GitHub then
    404s on an authorize URL whose client_id looks correct in every log and
    settings page.
    """
    return "".join(ch for ch in value if ch.isprintable()).strip()


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    """Prompt until a non-empty value survives scrubbing."""
    while True:
        label = f"{prompt} [{default}]: " if default else f"{prompt}: "
        reply = getpass.getpass(label) if secret else input(label)
        if not reply and default:
            reply = default
        cleaned = scrub(reply)
        if cleaned:
            if cleaned != reply:
                print("note  stripped stray whitespace or control characters from the input")
            return cleaned


def confirm(question: str) -> bool:
    return input(f"{question} [y/N]: ").strip().lower() == "y"


DRY_RUN = "--dry-run" in sys.argv


def redact(arg: str) -> str:
    """Hide secret values when echoing a command."""
    for name in ("INTERVALS_API_KEY", "GITHUB_CLIENT_SECRET", "JWT_SIGNING_KEY"):
        if arg.startswith(f"{name}="):
            return f"{name}=***"
    return arg


def fly(*args: str, capture: bool = False, mutating: bool = True) -> subprocess.CompletedProcess:
    """Run flyctl. Errors are the caller's to interpret, so never raise here.

    Under --dry-run, commands that change something are printed instead of run.
    Read-only ones still execute, so the dry run reports the real state of the
    app rather than a guess about it.
    """
    if DRY_RUN and mutating:
        print("dry   would run: flyctl " + " ".join(redact(a) for a in args))
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.run(
        ["flyctl", *args],
        capture_output=capture,
        text=True,
        check=False,
    )


def fly_value(*args: str) -> str:
    result = fly(*args, capture=True, mutating=False)
    return result.stdout if result.returncode == 0 else ""


def toml_value(pattern: str, path: Path = FLY_TEMPLATE) -> str:
    """Read one value out of a fly config without a TOML parser (3.11+ has one,
    but the file is three keys deep and this keeps the port line-for-line
    honest). Missing file reads as empty, which is the fresh-clone case."""
    if not path.exists():
        return ""
    match = re.search(pattern, path.read_text(), re.MULTILINE)
    return match.group(1) if match else ""


def apply_app_name(app: str) -> str:
    """Render fly.toml from the template for `app` and return its base URL.

    Setting the two together is what keeps fly.toml, the OAuth callback URL and
    PUBLIC_BASE_URL from drifting apart across a rename. No confirmation:
    fly.toml is a generated artifact here, not a file anyone hand-edits.
    """
    if DRY_RUN:
        print(f"dry   would render fly.toml from the template, targeting {app}")
    else:
        FLY_TOML.write_text(
            re.sub(r'^app *= *".*"', f'app = "{app}"', FLY_TEMPLATE.read_text(), count=1, flags=re.MULTILINE)
        )
        print(f"ok    fly.toml rendered from the template, targeting {app}")
    return f"https://{app}.fly.dev"


def gh(*args: str, capture: bool = False, mutating: bool = True, stdin: str = "") -> subprocess.CompletedProcess:
    """Run the gh CLI. Same dry-run contract as fly()."""
    if DRY_RUN and mutating:
        print("dry   would run: gh " + " ".join(redact(a) for a in args))
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.run(
        ["gh", *args],
        input=stdin if stdin else None,
        capture_output=capture,
        text=True,
        check=False,
    )


def manual_actions_help(app: str) -> None:
    print(f"  1. fly tokens create deploy -a {app}")
    print("  2. Save it as the repository secret FLY_API_TOKEN")
    print(f"  3. Set the repository variable FLY_APP to '{app}'")
    print("     (CI renders fly.toml from fly.toml.template using it)")


def wire_up_actions(app: str) -> None:
    """Point this repo's deploy workflow at the app we just deployed to."""
    if not shutil.which("gh"):
        print("gh CLI not found (https://cli.github.com). To wire this up by hand:")
        return manual_actions_help(app)
    if gh("auth", "status", capture=True, mutating=False).returncode != 0:
        print("gh is installed but not logged in — run 'gh auth login', or by hand:")
        return manual_actions_help(app)

    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner", capture=True, mutating=False)
    slug = repo.stdout.strip() if repo.returncode == 0 else ""
    if not slug:
        print("Could not tell which GitHub repository this is. By hand:")
        return manual_actions_help(app)
    if not confirm(f"Set FLY_API_TOKEN and FLY_APP on {slug} so pushes to main deploy to {app}?"):
        print("Skipped. To do it later:")
        return manual_actions_help(app)

    # A deploy token is scoped to this one app, which is what we want in a repo
    # secret — a personal auth token would let CI touch every app on the account.
    result = fly("tokens", "create", "deploy", "-a", app, capture=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    token = scrub(lines[-1]) if lines else ""
    if not token and not DRY_RUN:
        print("warn  could not create a deploy token. By hand:")
        return manual_actions_help(app)

    set_secret = gh("secret", "set", "FLY_API_TOKEN", "--repo", slug, stdin=token)
    set_var = gh("variable", "set", "FLY_APP", "--repo", slug, "--body", app)
    if set_secret.returncode != 0 or set_var.returncode != 0:
        print("warn  gh could not set them (needs repo admin rights). By hand:")
        return manual_actions_help(app)

    verb = "would be set" if DRY_RUN else "set"
    print(f"ok    FLY_API_TOKEN and FLY_APP {verb} on {slug}")
    print()
    print("One step is left that only you can do: GitHub disables Actions on new")
    print(f"forks. Open https://github.com/{slug}/actions and click")
    print("'I understand my workflows, go ahead and enable them'.")
    print(f"After that, every push to main deploys to {app}.")
    print("Syncing your fork from the GitHub web button does not always raise a")
    print("push event; the workflow also has a Run workflow button for that.")


def main() -> int:
    if not shutil.which("flyctl"):
        fail("flyctl not found. Install it: https://fly.io/docs/flyctl/install/")
    whoami = fly_value("auth", "whoami").strip()
    if not whoami:
        fail("Not logged in to Fly. Run: fly auth login")
    bold(f"Fly account: {whoami}")
    if DRY_RUN:
        bold("Dry run: nothing will be created, changed or deployed.")

    if not FLY_TEMPLATE.exists():
        fail("fly.toml.template is missing — this script renders fly.toml from it.")

    # The app name is per-user, so it lives in the rendered fly.toml (absent on
    # a fresh clone). Everything else is shared config, from the template.
    current_app = toml_value(r'^app *= *"(.*)"', FLY_TOML)
    if current_app == "APP_NAME":
        current_app = ""
    region = toml_value(r'^primary_region *= *"(.*)"')
    volume = toml_value(r'^ *source *= *"(.*)"')

    # --- app name ------------------------------------------------------------

    print()
    print("The app name becomes your URL and must match in fly.toml, the GitHub OAuth")
    print("callback URL, and PUBLIC_BASE_URL. This script keeps all three in sync.")

    # Match the first column only: an app name can otherwise collide with an
    # org or region printed further along the same row. This lists your own apps,
    # so it answers "do I own it", never "is it free".
    my_apps = [line.split()[0] for line in fly_value("apps", "list").splitlines() if line.split()]

    # A previous run's name wins, so re-running never silently renames your app.
    # Otherwise: the upstream name if you are the one who owns it, and a
    # suffixed name for everyone else.
    default_app = current_app
    if not default_app:
        if UPSTREAM_APP in my_apps:
            default_app = UPSTREAM_APP
        else:
            default_app = f"{UPSTREAM_APP}-{secrets.token_hex(3)}"
            print()
            print(f"Fly app names are global, so '{UPSTREAM_APP}' is taken. Here is a free-looking")
            print("one — press enter to take it, or type your own.")
    app = ask("Fly app name", default_app)
    base_url = apply_app_name(app)

    if app in my_apps:
        print(f"ok    app {app} already exists")
    else:
        # Creating is the only real uniqueness check, so treat a failure as
        # "taken" and offer another name rather than pressing on against an app
        # that is not ours — every later step would target someone else's
        # deployment.
        while True:
            if not confirm(f"Create Fly app '{app}'?"):
                fail("Aborted.")
            if fly("apps", "create", app).returncode == 0:
                break
            print(f"warn  could not create '{app}'. If the name is taken, try another.")
            app = ask("Fly app name", f"{app}-{secrets.token_hex(2)}")
            base_url = apply_app_name(app)

    # fly.toml mounts a volume; without it the first deploy fails to start.
    if volume:
        if volume in fly_value("volumes", "list", "-a", app):
            print(f"ok    volume {volume} already exists")
        elif confirm(f"Create 1GB volume '{volume}' in {region} (required by fly.toml.template)?"):
            fly("volumes", "create", volume, "-a", app, "-r", region, "-s", "1", "-y")
        else:
            fail("Aborted.")

    # --- GitHub OAuth app ----------------------------------------------------

    print()
    bold("GitHub OAuth app")
    print("Create one at https://github.com/settings/developers -> New OAuth App:")
    print(f"  Homepage URL:              {base_url}")
    print(f"  Authorization callback URL: {base_url}/auth/callback")
    print("Then generate a client secret and paste both below.")
    print()
    client_id = ask("GitHub client ID")
    client_secret = ask("GitHub client secret", secret=True)
    allowed_users = ask("Allowed GitHub usernames (comma-separated)")

    # Rotating this key invalidates every issued token, so reuse it when it is set.
    jwt_arg: list[str] = []
    if "JWT_SIGNING_KEY" in fly_value("secrets", "list", "-a", app):
        print("ok    JWT_SIGNING_KEY already set — keeping it (rotating would log everyone out)")
        jwt_status = "unchanged"
    else:
        jwt_arg = [f"JWT_SIGNING_KEY={secrets.token_hex(32)}"]
        jwt_status = "newly generated"
        print("ok    generated a new JWT_SIGNING_KEY")

    # --- API key -------------------------------------------------------------

    # .env values are commonly quoted, and python-dotenv strips those for a local
    # run. Fly does not, so an unstripped key ships to the server as
    # INTERVALS_API_KEY="abc" — quotes included — and intervals.icu returns 401.
    api_key = ""
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        match = re.search(r"^INTERVALS_API_KEY=(.+)$", env_file.read_text(), re.MULTILINE)
        if match:
            api_key = scrub(match.group(1))
            if len(api_key) >= 2 and api_key[0] == api_key[-1] and api_key[0] in "\"'":
                api_key = api_key[1:-1]
    if api_key:
        print("ok    INTERVALS_API_KEY read from .env")
    else:
        api_key = ask("intervals.icu API key (Settings -> Developer Settings)", secret=True)

    # --- set secrets and deploy ----------------------------------------------

    print()
    bold(f"About to set these secrets on {app}:")
    print("  INTERVALS_API_KEY     (hidden)")
    print(f"  GITHUB_CLIENT_ID      {client_id}")
    print("  GITHUB_CLIENT_SECRET  (hidden)")
    print(f"  JWT_SIGNING_KEY       {jwt_status}")
    print(f"  ALLOWED_GITHUB_USERS  {allowed_users}")
    print(f"  PUBLIC_BASE_URL       {base_url}")
    if not confirm("Set them?"):
        fail("Aborted.")

    # --stage keeps the secrets off the running machine until the next deploy,
    # so a half-finished run never leaves the server on mismatched credentials.
    fly(
        "secrets",
        "set",
        "-a",
        app,
        "--stage",
        f"INTERVALS_API_KEY={api_key}",
        f"GITHUB_CLIENT_ID={client_id}",
        f"GITHUB_CLIENT_SECRET={client_secret}",
        f"ALLOWED_GITHUB_USERS={allowed_users}",
        f"PUBLIC_BASE_URL={base_url}",
        *jwt_arg,
    )

    print()
    if confirm("Deploy now?"):
        fly("deploy", "-a", app)
        print()
        bold(f"{'Would deploy' if DRY_RUN else 'Deployed'}. MCP server URL: {base_url}/mcp")
        print(f"Only these GitHub users can connect: {allowed_users}")
    else:
        print(f"Secrets staged. Deploy when ready with: fly deploy -a {app}")

    # --- automatic deploys ---------------------------------------------------

    # Everything below only wires up CI. The server is already deployed, so a
    # failure here is never fatal.
    print()
    bold("Automatic deploys on push to main")
    wire_up_actions(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
