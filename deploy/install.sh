#!/bin/bash
# Sets up the dashboard on the Pi: server.py as a user service, the kiosk at login, and a
# "Home Dashboard" menu entry. Everything lives under ~/.config and ~/.local; safe to re-run.
#
#   deploy/install.sh              install, or update after pulling changes
#   deploy/install.sh --uninstall  remove all of it (saved countdowns in data/ are kept)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$HOME/.config/systemd/user/home-dashboard.service"
AUTOSTART="$HOME/.config/autostart/dashboard.desktop"
MENU_ENTRY="$HOME/.local/share/applications/home-dashboard.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now home-dashboard.service 2>/dev/null || true
    rm -f "$UNIT" "$AUTOSTART" "$MENU_ENTRY"
    systemctl --user daemon-reload
    echo "Uninstalled. Saved countdowns are still in $REPO/data/"
    exit 0
fi

mkdir -p "$(dirname "$UNIT")" "$(dirname "$AUTOSTART")" "$(dirname "$MENU_ENTRY")" "$REPO/data"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.service" > "$UNIT"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.desktop" > "$AUTOSTART"
cp "$AUTOSTART" "$MENU_ENTRY"
chmod +x "$REPO/start_dashboard.sh"

systemctl --user daemon-reload
systemctl --user enable home-dashboard.service
systemctl --user restart home-dashboard.service

echo "Installed. Server: $(systemctl --user is-active home-dashboard.service) on http://localhost:8000"
echo "The kiosk starts at next login, or now via 'Home Dashboard' in the menu."
