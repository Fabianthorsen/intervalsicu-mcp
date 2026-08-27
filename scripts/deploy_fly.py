"""Set up and deploy the remote (HTTP + GitHub OAuth) server on Fly.io.

Run with: uv run python scripts/deploy_fly.py

Safe to re-run: it skips anything that already exists and re-prompts only for
what is missing. Nothing is created or deployed until you confirm.

This is the Python port of deploy_fly.sh, so Windows works without WSL or Git
Bash. Keep the two in sync, or delete one — a setup script that prints values
the server does not actually use is worse than no script at all.
"""

import getpass
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLY_TOML = REPO_ROOT / "fly.toml"


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


def fly(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    """Run flyctl. Errors are the caller's to interpret, so never raise here."""
    return subprocess.run(
        ["flyctl", *args],
        capture_output=capture,
        text=True,
        check=False,
    )


def fly_value(*args: str) -> str:
    result = fly(*args, capture=True)
    return result.stdout if result.returncode == 0 else ""


def toml_value(pattern: str) -> str:
    """Read one value out of fly.toml without a TOML parser (3.11+ has one, but
    the file is three keys deep and this keeps the port line-for-line honest)."""
    match = re.search(pattern, FLY_TOML.read_text(), re.MULTILINE)
    return match.group(1) if match else ""


def main() -> int:
    if not shutil.which("flyctl"):
        fail("flyctl not found. Install it: https://fly.io/docs/flyctl/install/")
    whoami = fly_value("auth", "whoami").strip()
    if not whoami:
        fail("Not logged in to Fly. Run: fly auth login")
    bold(f"Fly account: {whoami}")

    current_app = toml_value(r'^app *= *"(.*)"')
    region = toml_value(r'^primary_region *= *"(.*)"')
    volume = toml_value(r'^ *source *= *"(.*)"')

    # --- app name ------------------------------------------------------------

    print()
    print("The app name becomes your URL and must match in fly.toml, the GitHub OAuth")
    print("callback URL, and PUBLIC_BASE_URL. This script keeps all three in sync.")
    app = ask("Fly app name", current_app)
    base_url = f"https://{app}.fly.dev"

    if app != current_app:
        if not confirm(f"Rewrite fly.toml app name from '{current_app}' to '{app}'?"):
            fail("fly.toml must name the app you are deploying to.")
        FLY_TOML.write_text(
            re.sub(r'^app *= *".*"', f'app = "{app}"', FLY_TOML.read_text(), count=1, flags=re.MULTILINE)
        )
        print(f"ok    fly.toml now targets {app}")

    # Match the first column only: an app name can otherwise collide with an
    # org or region printed further along the same row.
    existing = [line.split()[0] for line in fly_value("apps", "list").splitlines() if line.split()]
    if app in existing:
        print(f"ok    app {app} already exists")
    else:
        if not confirm(f"Create Fly app '{app}'?"):
            fail("Aborted.")
        fly("apps", "create", app)

    # fly.toml mounts a volume; without it the first deploy fails to start.
    if volume:
        if volume in fly_value("volumes", "list", "-a", app):
            print(f"ok    volume {volume} already exists")
        elif confirm(f"Create 1GB volume '{volume}' in {region} (required by fly.toml)?"):
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
        import secrets

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
        bold(f"Deployed. MCP server URL: {base_url}/mcp")
        print(f"Only these GitHub users can connect: {allowed_users}")
    else:
        print(f"Secrets staged. Deploy when ready with: fly deploy -a {app}")

    print()
    print("For automatic deploys on push to main, add a repo secret FLY_API_TOKEN")
    print(f"with the output of: fly tokens create deploy -a {app}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
