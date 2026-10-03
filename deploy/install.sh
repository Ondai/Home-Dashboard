#!/bin/bash
# Sets up the dashboard on the Pi: server.py as a user service, the kiosk at login, a nightly
# fresh start for its browser, and a "Home Dashboard" launcher on the taskbar and in the menu
# (Accessories). Everything lives in the home folder; safe to re-run.
#
#   deploy/install.sh              install, or update after pulling changes
#   deploy/install.sh --uninstall  remove all of it (saved countdowns in data/ are kept)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/home-dashboard.service"
REFRESH_UNITS=(home-dashboard-refresh.service home-dashboard-refresh.timer)
AUTOSTART="$HOME/.config/autostart/dashboard.desktop"
MENU_ENTRY="$HOME/.local/share/applications/home-dashboard.desktop"
PANEL_INI="$HOME/.config/wf-panel-pi.ini"
# Earlier installs put a launcher on the desktop, but the Pi's desktop asks "Execute File?"
# before opening any launcher there; the taskbar button opens with one tap instead.
OLD_DESKTOP_ICON="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")/home-dashboard.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now home-dashboard.service home-dashboard-refresh.timer 2>/dev/null || true
    rm -f "$UNIT" "${REFRESH_UNITS[@]/#/$UNIT_DIR/}" "$AUTOSTART" "$MENU_ENTRY" "$OLD_DESKTOP_ICON"
    [ -f "$PANEL_INI" ] && sed -i '/^launcher_[0-9]*=home-dashboard\.desktop$/d' "$PANEL_INI"
    systemctl --user daemon-reload
    echo "Uninstalled. Saved countdowns are still in $REPO/data/"
    exit 0
fi

mkdir -p "$(dirname "$UNIT")" "$(dirname "$AUTOSTART")" "$(dirname "$MENU_ENTRY")" "$REPO/data"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.service" > "$UNIT"
for unit in "${REFRESH_UNITS[@]}"; do cp "$REPO/deploy/$unit" "$UNIT_DIR/$unit"; done
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.desktop" > "$AUTOSTART"
cp "$AUTOSTART" "$MENU_ENTRY"
rm -f "$OLD_DESKTOP_ICON"
chmod +x "$REPO/start_dashboard.sh"

# Taskbar button: appended after the existing launchers, once. The panel finds it by the
# menu entry's file name.
if [ -f "$PANEL_INI" ] && ! grep -q '^launcher_[0-9]*=home-dashboard\.desktop$' "$PANEL_INI"; then
    last=$(grep -oE '^launcher_[0-9]+' "$PANEL_INI" | sort | tail -1 || true)
    if [ -n "$last" ]; then
        next=$(printf 'launcher_%06d' $((10#${last#launcher_} + 1)))
        sed -i "/^${last}=/a ${next}=home-dashboard.desktop" "$PANEL_INI"
    else
        sed -i '/^\[panel\]$/a launcher_000001=home-dashboard.desktop' "$PANEL_INI"
    fi
fi

systemctl --user daemon-reload
systemctl --user enable home-dashboard.service
systemctl --user restart home-dashboard.service
systemctl --user enable --now home-dashboard-refresh.timer

echo "Installed. Server: $(systemctl --user is-active home-dashboard.service) on http://localhost:8000"
echo "Nightly browser refresh: $(systemctl --user show -p NextElapseUSecRealtime --value home-dashboard-refresh.timer)"
echo "The kiosk starts at next login, or now via the Home Dashboard button on the taskbar."
