#!/bin/bash
# Sets up the dashboard on the Pi: server.py as a user service, the kiosk at login, and a
# "Home Dashboard" launcher in the menu (Accessories) and on the desktop. Everything lives in
# the home folder; safe to re-run.
#
#   deploy/install.sh              install, or update after pulling changes
#   deploy/install.sh --uninstall  remove all of it (saved countdowns in data/ are kept)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$HOME/.config/systemd/user/home-dashboard.service"
AUTOSTART="$HOME/.config/autostart/dashboard.desktop"
MENU_ENTRY="$HOME/.local/share/applications/home-dashboard.desktop"
# For getting back after "Exit to Desktop" without digging through the menu
DESKTOP_ICON="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")/home-dashboard.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now home-dashboard.service 2>/dev/null || true
    rm -f "$UNIT" "$AUTOSTART" "$MENU_ENTRY" "$DESKTOP_ICON"
    systemctl --user daemon-reload
    echo "Uninstalled. Saved countdowns are still in $REPO/data/"
    exit 0
fi

mkdir -p "$(dirname "$UNIT")" "$(dirname "$AUTOSTART")" "$(dirname "$MENU_ENTRY")" \
    "$(dirname "$DESKTOP_ICON")" "$REPO/data"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.service" > "$UNIT"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.desktop" > "$AUTOSTART"
cp "$AUTOSTART" "$MENU_ENTRY"
cp "$AUTOSTART" "$DESKTOP_ICON"
chmod +x "$DESKTOP_ICON" "$REPO/start_dashboard.sh"  # the desktop only runs launchers marked executable

systemctl --user daemon-reload
systemctl --user enable home-dashboard.service
systemctl --user restart home-dashboard.service

echo "Installed. Server: $(systemctl --user is-active home-dashboard.service) on http://localhost:8000"
echo "The kiosk starts at next login, or now via 'Home Dashboard' on the desktop or in Accessories."
