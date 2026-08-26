#!/usr/bin/env bash
#
# Set up and deploy the remote (HTTP + GitHub OAuth) server on Fly.io.
#
#   ./scripts/deploy_fly.sh
#
# Safe to re-run: it skips anything that already exists and re-prompts only for
# what is missing. Nothing is created or deployed until you confirm.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }

ask() { # ask VAR "prompt" [default]
  local __var=$1 __prompt=$2 __default=${3:-} __reply
  if [[ -n $__default ]]; then
    read -r -p "$__prompt [$__default]: " __reply
    __reply=${__reply:-$__default}
  else
    while [[ -z ${__reply:-} ]]; do read -r -p "$__prompt: " __reply; done
  fi
  printf -v "$__var" '%s' "$__reply"
}

confirm() {
  local reply
  read -r -p "$1 [y/N]: " reply
  [[ $reply == [yY] ]]
}

# --- prerequisites -----------------------------------------------------------

command -v flyctl >/dev/null || fail "flyctl not found. Install it: https://fly.io/docs/flyctl/install/"
flyctl auth whoami >/dev/null 2>&1 || fail "Not logged in to Fly. Run: fly auth login"
bold "Fly account: $(flyctl auth whoami)"

CURRENT_APP=$(sed -n 's/^app *= *"\(.*\)"/\1/p' fly.toml)
REGION=$(sed -n 's/^primary_region *= *"\(.*\)"/\1/p' fly.toml)
VOLUME=$(sed -n 's/^ *source *= *"\(.*\)"/\1/p' fly.toml)

# --- app name ----------------------------------------------------------------

echo
echo "The app name becomes your URL and must match in fly.toml, the GitHub OAuth"
echo "callback URL, and PUBLIC_BASE_URL. This script keeps all three in sync."
ask APP "Fly app name" "$CURRENT_APP"
BASE_URL="https://${APP}.fly.dev"

if [[ $APP != "$CURRENT_APP" ]]; then
  confirm "Rewrite fly.toml app name from '$CURRENT_APP' to '$APP'?" \
    || fail "fly.toml must name the app you are deploying to."
  sed -i.bak "s/^app *= *\".*\"/app = \"$APP\"/" fly.toml && rm -f fly.toml.bak
  echo "ok    fly.toml now targets $APP"
fi

if flyctl apps list 2>/dev/null | awk '{print $1}' | grep -qx "$APP"; then
  echo "ok    app $APP already exists"
else
  confirm "Create Fly app '$APP'?" || fail "Aborted."
  flyctl apps create "$APP"
fi

# fly.toml mounts a volume; without it the first deploy fails to start.
if [[ -n $VOLUME ]]; then
  if flyctl volumes list -a "$APP" 2>/dev/null | grep -q "$VOLUME"; then
    echo "ok    volume $VOLUME already exists"
  else
    confirm "Create 1GB volume '$VOLUME' in $REGION (required by fly.toml)?" || fail "Aborted."
    flyctl volumes create "$VOLUME" -a "$APP" -r "$REGION" -s 1 -y
  fi
fi

# --- GitHub OAuth app --------------------------------------------------------

echo
bold "GitHub OAuth app"
echo "Create one at https://github.com/settings/developers -> New OAuth App:"
echo "  Homepage URL:              $BASE_URL"
echo "  Authorization callback URL: $BASE_URL/auth/github/callback"
echo "Then generate a client secret and paste both below."
echo
ask GITHUB_CLIENT_ID "GitHub client ID"
ask GITHUB_CLIENT_SECRET "GitHub client secret"
ask ALLOWED_GITHUB_USERS "Allowed GitHub usernames (comma-separated)"

# Rotating this key invalidates every issued token, so reuse it when it is set.
if flyctl secrets list -a "$APP" 2>/dev/null | grep -q JWT_SIGNING_KEY; then
  echo "ok    JWT_SIGNING_KEY already set — keeping it (rotating would log everyone out)"
  JWT_ARG=()
  JWT_STATUS="unchanged"
else
  if command -v openssl >/dev/null; then
    JWT_SIGNING_KEY=$(openssl rand -hex 32)
  else
    JWT_SIGNING_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  fi
  echo "ok    generated a new JWT_SIGNING_KEY"
  JWT_ARG=("JWT_SIGNING_KEY=$JWT_SIGNING_KEY")
  JWT_STATUS="newly generated"
fi

# --- API key -----------------------------------------------------------------

INTERVALS_API_KEY=$(sed -n 's/^INTERVALS_API_KEY=\(.*\)/\1/p' .env 2>/dev/null | tail -1)
if [[ -n $INTERVALS_API_KEY ]]; then
  echo "ok    INTERVALS_API_KEY read from .env"
else
  ask INTERVALS_API_KEY "intervals.icu API key (Settings -> Developer Settings)"
fi

# --- set secrets and deploy --------------------------------------------------

echo
bold "About to set these secrets on $APP:"
echo "  INTERVALS_API_KEY     (hidden)"
echo "  GITHUB_CLIENT_ID      $GITHUB_CLIENT_ID"
echo "  GITHUB_CLIENT_SECRET  (hidden)"
echo "  JWT_SIGNING_KEY       $JWT_STATUS"
echo "  ALLOWED_GITHUB_USERS  $ALLOWED_GITHUB_USERS"
echo "  PUBLIC_BASE_URL       $BASE_URL"
confirm "Set them?" || fail "Aborted."

flyctl secrets set -a "$APP" --stage \
  "INTERVALS_API_KEY=$INTERVALS_API_KEY" \
  "GITHUB_CLIENT_ID=$GITHUB_CLIENT_ID" \
  "GITHUB_CLIENT_SECRET=$GITHUB_CLIENT_SECRET" \
  "ALLOWED_GITHUB_USERS=$ALLOWED_GITHUB_USERS" \
  "PUBLIC_BASE_URL=$BASE_URL" \
  ${JWT_ARG[@]+"${JWT_ARG[@]}"}

echo
if confirm "Deploy now?"; then
  flyctl deploy -a "$APP"
  echo
  bold "Deployed. MCP server URL: $BASE_URL/mcp"
  echo "Only these GitHub users can connect: $ALLOWED_GITHUB_USERS"
else
  echo "Secrets staged. Deploy when ready with: fly deploy -a $APP"
fi

echo
echo "For automatic deploys on push to main, add a repo secret FLY_API_TOKEN"
echo "with the output of: fly tokens create deploy -a $APP"
