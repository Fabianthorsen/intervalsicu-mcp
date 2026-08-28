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

# Strip control characters and surrounding whitespace. Pasting a client ID or
# secret into a terminal can smuggle in invisible bytes (a literal Ctrl-V shows
# up as \x16); Fly stores them happily and GitHub then 404s on an authorize URL
# whose client_id looks correct in every log and settings page.
scrub() {
  local __clean
  __clean=$(printf '%s' "$1" | tr -d '[:cntrl:]')
  __clean="${__clean#"${__clean%%[![:space:]]*}"}"
  __clean="${__clean%"${__clean##*[![:space:]]}"}"
  printf '%s' "$__clean"
}

ask() { # ask VAR "prompt" [default]
  local __var=$1 __prompt=$2 __default=${3:-} __reply __scrubbed
  while :; do
    if [[ -n $__default ]]; then
      read -r -p "$__prompt [$__default]: " __reply
      __reply=${__reply:-$__default}
    else
      read -r -p "$__prompt: " __reply
    fi
    __scrubbed=$(scrub "$__reply")
    [[ -n $__scrubbed ]] && break
  done
  if [[ $__scrubbed != "$__reply" ]]; then
    echo "note  stripped stray whitespace or control characters from the input"
  fi
  printf -v "$__var" '%s' "$__scrubbed"
}

confirm() {
  local reply
  read -r -p "$1 [y/N]: " reply
  [[ $reply == [yY] ]]
}

rand_hex() { # rand_hex NBYTES
  if command -v openssl >/dev/null; then
    openssl rand -hex "$1"
  else
    python3 -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))" "$1"
  fi
}

# --- prerequisites -----------------------------------------------------------

command -v flyctl >/dev/null || fail "flyctl not found. Install it: https://fly.io/docs/flyctl/install/"
flyctl auth whoami >/dev/null 2>&1 || fail "Not logged in to Fly. Run: fly auth login"
bold "Fly account: $(flyctl auth whoami)"

# fly.toml is generated from fly.toml.template and gitignored, so a fork never
# carries a one-line app-name diff that conflicts on every upstream sync.
[[ -f fly.toml.template ]] || fail "fly.toml.template is missing — this script renders fly.toml from it."

# The app name is per-user, so it lives in the rendered fly.toml (empty on a
# fresh clone). Everything else is shared config and comes from the template.
# `|| true` because sed exits non-zero on a missing fly.toml, which is simply
# the fresh-clone case — and `set -e` would take that as a fatal error.
CURRENT_APP=$(sed -n 's/^app *= *"\(.*\)"/\1/p' fly.toml 2>/dev/null || true)
[[ $CURRENT_APP == "APP_NAME" ]] && CURRENT_APP=""
REGION=$(sed -n 's/^primary_region *= *"\(.*\)"/\1/p' fly.toml.template)
VOLUME=$(sed -n 's/^ *source *= *"\(.*\)"/\1/p' fly.toml.template)

# --- app name ----------------------------------------------------------------

# The maintainer's own app. Everyone else needs a different name, because Fly
# app names are unique across all of Fly, not per account.
UPSTREAM_APP="intervalsicu-mcp"

# `apps list` shows only your own apps, so this answers "do I own it", never
# "is it free" — the latter is only knowable by trying to create it.
MY_APPS=$(flyctl apps list 2>/dev/null | awk '{print $1}')
owns_app() { printf '%s\n' "$MY_APPS" | grep -qx "$1"; }

# Set APP and BASE_URL together and render fly.toml to match, so a rename can
# never leave the three out of step. No confirmation: fly.toml is a generated
# artifact here, not a file anyone hand-edits.
apply_app_name() {
  APP=$1
  BASE_URL="https://${APP}.fly.dev"
  sed "s/^app *= *\".*\"/app = \"$APP\"/" fly.toml.template > fly.toml
  echo "ok    fly.toml rendered from the template, targeting $APP"
}

echo
echo "The app name becomes your URL and must match in fly.toml, the GitHub OAuth"
echo "callback URL, and PUBLIC_BASE_URL. This script keeps all three in sync."

# A previous run's name wins, so re-running never silently renames your app.
# Otherwise: the upstream name if you are the one who owns it, and a suffixed
# name for everyone else.
DEFAULT_APP=$CURRENT_APP
if [[ -z $DEFAULT_APP ]]; then
  if owns_app "$UPSTREAM_APP"; then
    DEFAULT_APP=$UPSTREAM_APP
  else
    DEFAULT_APP="${UPSTREAM_APP}-$(rand_hex 3)"
    echo
    echo "Fly app names are global, so '$UPSTREAM_APP' is taken. Here is a free-looking"
    echo "one — press enter to take it, or type your own."
  fi
fi
ask APP "Fly app name" "$DEFAULT_APP"
apply_app_name "$APP"

if owns_app "$APP"; then
  echo "ok    app $APP already exists"
else
  # Creating is the only real uniqueness check, so treat a failure as "taken"
  # and offer another name rather than pressing on against an app that is not
  # ours — every later step would target someone else's deployment.
  while :; do
    confirm "Create Fly app '$APP'?" || fail "Aborted."
    flyctl apps create "$APP" && break
    echo "warn  could not create '$APP'. If the name is taken, try another."
    ask NEXT_APP "Fly app name" "${APP}-$(rand_hex 2)"
    apply_app_name "$NEXT_APP"
  done
fi

# fly.toml mounts a volume; without it the first deploy fails to start.
if [[ -n $VOLUME ]]; then
  if flyctl volumes list -a "$APP" 2>/dev/null | grep -q "$VOLUME"; then
    echo "ok    volume $VOLUME already exists"
  else
    confirm "Create 1GB volume '$VOLUME' in $REGION (required by fly.toml.template)?" || fail "Aborted."
    flyctl volumes create "$VOLUME" -a "$APP" -r "$REGION" -s 1 -y
  fi
fi

# --- GitHub OAuth app --------------------------------------------------------

echo
bold "GitHub OAuth app"
echo "Create one at https://github.com/settings/developers -> New OAuth App:"
echo "  Homepage URL:              $BASE_URL"
echo "  Authorization callback URL: $BASE_URL/auth/callback"
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

# .env values are commonly quoted, and python-dotenv strips those for a local
# run. Fly does not, so an unstripped key ships to the server as
# INTERVALS_API_KEY="abc" — quotes included — and intervals.icu returns 401.
INTERVALS_API_KEY=$(sed -n 's/^INTERVALS_API_KEY=\(.*\)/\1/p' .env 2>/dev/null | tail -1)
INTERVALS_API_KEY=$(scrub "$INTERVALS_API_KEY")
INTERVALS_API_KEY=${INTERVALS_API_KEY%\"}; INTERVALS_API_KEY=${INTERVALS_API_KEY#\"}
INTERVALS_API_KEY=${INTERVALS_API_KEY%\'}; INTERVALS_API_KEY=${INTERVALS_API_KEY#\'}
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

# --- automatic deploys -------------------------------------------------------

# Everything below only wires up CI. The server is already deployed, so a
# failure here is never fatal.

manual_actions_help() {
  echo "  1. fly tokens create deploy -a $APP"
  echo "  2. Save it as the repository secret FLY_API_TOKEN"
  echo "  3. Set the repository variable FLY_APP to '$APP'"
  echo "     (CI renders fly.toml from fly.toml.template using it)"
}

echo
bold "Automatic deploys on push to main"

if ! command -v gh >/dev/null; then
  echo "gh CLI not found (https://cli.github.com). To wire this up by hand:"
  manual_actions_help
elif ! gh auth status >/dev/null 2>&1; then
  echo "gh is installed but not logged in — run 'gh auth login', or by hand:"
  manual_actions_help
else
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
  if [[ -z $REPO ]]; then
    echo "Could not tell which GitHub repository this is. By hand:"
    manual_actions_help
  elif ! confirm "Set FLY_API_TOKEN and FLY_APP on $REPO so pushes to main deploy to $APP?"; then
    echo "Skipped. To do it later:"
    manual_actions_help
  else
    # A deploy token is scoped to this one app, which is what we want in a repo
    # secret — a personal auth token would let CI touch every app on the account.
    DEPLOY_TOKEN=$(scrub "$(flyctl tokens create deploy -a "$APP" 2>/dev/null | grep -v '^$' | tail -1)")
    if [[ -z $DEPLOY_TOKEN ]]; then
      echo "warn  could not create a deploy token. By hand:"
      manual_actions_help
    elif printf '%s' "$DEPLOY_TOKEN" | gh secret set FLY_API_TOKEN --repo "$REPO" \
      && gh variable set FLY_APP --repo "$REPO" --body "$APP"; then
      echo "ok    FLY_API_TOKEN and FLY_APP set on $REPO"
      echo
      echo "One step is left that only you can do: GitHub disables Actions on new"
      echo "forks. Open https://github.com/$REPO/actions and click"
      echo "'I understand my workflows, go ahead and enable them'."
      echo "After that, every push to main deploys to $APP."
      echo "Syncing your fork from the GitHub web button does not always raise a"
      echo "push event; the workflow also has a Run workflow button for that."
    else
      echo "warn  gh could not set them (needs repo admin rights). By hand:"
      manual_actions_help
    fi
  fi
fi
