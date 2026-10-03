#!/bin/bash
# One-line install for a new Pi (Raspberry Pi OS with desktop, Bookworm or Trixie):
#
#   curl -fsSL https://raw.githubusercontent.com/Ondai/Home-Dashboard/main/deploy/bootstrap.sh | bash
#
# Downloads the dashboard to ~/Home-Dashboard (or updates it if it's already there), then runs
# deploy/install.sh. Set HOME_DASHBOARD_DIR or HOME_DASHBOARD_REPO to change where from/to.
set -euo pipefail

REPO_URL="${HOME_DASHBOARD_REPO:-https://github.com/Ondai/Home-Dashboard.git}"
DIR="${HOME_DASHBOARD_DIR:-$HOME/Home-Dashboard}"

if ! command -v git >/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq git
fi
if [ -d "$DIR/.git" ]; then
    git -C "$DIR" pull --ff-only
else
    git clone --depth 1 "$REPO_URL" "$DIR"
fi
exec "$DIR/deploy/install.sh" "$@"
