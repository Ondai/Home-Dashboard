#!/bin/bash
# Shows the dashboard full screen in Chromium kiosk mode, relaunching it if it closes or crashes.
#
# Started at login by ~/.config/autostart/dashboard.desktop, and by the "Home Dashboard" menu entry
# to come back after "Exit to Desktop". "Exit to Desktop" (server.py /kiosk/exit) creates
# PAUSE_FILE and closes Chromium, which ends the loop below. Keep the paths in sync with server.py.

URL="http://localhost:8000/"
STATE_DIR="$HOME/.cache/home-dashboard"
PAUSE_FILE="$STATE_DIR/kiosk-paused"
PROFILE_DIR="$HOME/.local/share/home-dashboard/chromium"

mkdir -p "$STATE_DIR" "$PROFILE_DIR"
rm -f "$PAUSE_FILE"

# Only one launcher at a time (e.g. autostart plus a tap on the menu entry).
exec 9>"$STATE_DIR/kiosk.lock"
flock -n 9 || exit 0

# The server starts alongside the desktop; don't show Chromium's error page while it comes up.
for _ in $(seq 1 60); do
    curl -fs -o /dev/null "$URL" && break
    sleep 1
done

while [ ! -e "$PAUSE_FILE" ]; do
    # --ozone-platform=wayland: fresh profiles default to X11, which fails under Wayfire.
    # A dedicated profile keeps the kiosk separate from normal browsing on the Pi.
    chromium \
        --ozone-platform=wayland \
        --kiosk \
        --user-data-dir="$PROFILE_DIR" \
        --no-first-run \
        --password-store=basic \
        --noerrdialogs \
        --hide-crash-restore-bubble \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        --disable-features=Translate,OverscrollHistoryNavigation,TouchpadOverscrollHistoryNavigation \
        "$URL" 9>&-
    sleep 2
done
