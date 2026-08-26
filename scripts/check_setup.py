"""Verify a fresh checkout is configured correctly, and print the client config.

Run with: uv run python scripts/check_setup.py

Creates .env from .env.example if it is missing, then checks that the API key is
present, that intervals.icu accepts it, and that the MCP server imports with
every tool mounted. Each failure prints what to fix. On success it prints the
Claude Desktop / Claude Code config with absolute paths already filled in.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import httpx
from dotenv import load_dotenv

try:  # Behind a TLS-intercepting proxy the root CA lives in the OS keychain only.
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass


def ensure_env_file() -> None:
    """Create .env from the template so the next failure is 'key is blank', not 'no file'."""
    env = REPO_ROOT / ".env"
    example = REPO_ROOT / ".env.example"
    if env.exists() or not example.exists():
        return
    shutil.copy(example, env)
    print(f"ok    created {env.name} from .env.example")


def print_client_config() -> None:
    """Print config with absolute paths resolved.

    Claude Desktop does not inherit the shell PATH, so a bare `uv` in its config
    fails with 'command not found'. Resolving it here is the whole point.
    """
    uv = shutil.which("uv") or "uv"
    print("\nClaude Code — run this once:\n")
    print(f"  claude mcp add intervals-icu -- {uv} --directory {REPO_ROOT} run python src/server.py")

    config = {
        "mcpServers": {
            "intervals-icu": {
                "command": uv,
                "args": ["--directory", str(REPO_ROOT), "run", "python", "src/server.py"],
            }
        }
    }
    print("\nClaude Desktop — merge into claude_desktop_config.json, then restart it:\n")
    print("\n".join("  " + line for line in json.dumps(config, indent=2).splitlines()))
    print(f"\n  ({desktop_config_path()})")


def desktop_config_path() -> str:
    """Where Claude Desktop keeps its config on this OS."""
    if sys.platform == "darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        return r"%APPDATA%\Claude\claude_desktop_config.json"
    return "~/.config/Claude/claude_desktop_config.json"


async def main() -> int:
    ensure_env_file()
    load_dotenv()

    api_key = os.environ.get("INTERVALS_API_KEY")
    if not api_key:
        print("FAIL  INTERVALS_API_KEY is not set.")
        print("      Paste your key into .env — find it at intervals.icu under")
        print("      Settings -> Developer Settings.")
        return 1
    print("ok    INTERVALS_API_KEY is set")

    try:
        async with httpx.AsyncClient(
            base_url="https://intervals.icu/api/v1",
            auth=("API_KEY", api_key),
            timeout=15,
        ) as client:
            resp = await client.get("/athlete/0")
            if resp.is_redirect:
                # A redirect off intervals.icu means something in between answered
                # for it — typically a corporate web gateway serving a block page.
                host = httpx.URL(resp.headers.get("location", "")).host or "elsewhere"
                print(f"FAIL  Request was redirected to {host}")
                print("      Your network is intercepting intervals.icu. Try another network.")
                return 1
            resp.raise_for_status()
            athlete = resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"FAIL  intervals.icu rejected the key ({exc.response.status_code}).")
        print("      Generate a fresh key under Settings -> Developer Settings.")
        return 1
    except httpx.HTTPError as exc:
        print(f"FAIL  Could not reach intervals.icu: {exc!r}")
        print("      Some corporate networks block or TLS-intercept intervals.icu —")
        print("      try another network, and see the README's troubleshooting section.")
        return 1
    print(f"ok    authenticated as {athlete.get('name', 'unknown')} ({athlete.get('id')})")

    import server

    tools = await server.mcp.get_tools()
    print(f"ok    MCP server imports with {len(tools)} tools mounted")

    print("\nSetup looks good.")
    print_client_config()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
