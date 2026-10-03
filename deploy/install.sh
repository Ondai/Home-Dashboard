#!/bin/bash
# Sets up (or updates) Home Dashboard on a Raspberry Pi running Raspberry Pi OS with desktop:
#   - system: the packages it needs, boot straight to the desktop, no screen blanking
#   - the dashboard server as a user service, with its Python packages in .venv
#   - the full-screen kiosk at login, a nightly fresh start for its browser, and a
#     "Home Dashboard" launcher on the taskbar and in the menu (Accessories)
# Everything except the system step lives in the home folder. Safe to re-run.
#
#   deploy/install.sh                     install, or update after pulling changes
#   deploy/install.sh --skip-system       leave packages, autologin and screen blanking alone
#   deploy/install.sh --uninstall         remove it (saved countdowns and settings in data/ are kept)
#
# Supported: Raspberry Pi OS Bookworm (Debian 12) and Trixie (Debian 13), with the Wayfire,
# labwc or X11 desktop. Bullseye and older can't run the calendar code (Python 3.10+ needed).
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

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now home-dashboard.service home-dashboard-refresh.timer 2>/dev/null || true
    rm -f "$UNIT" "${REFRESH_UNITS[@]/#/$UNIT_DIR/}" "$AUTOSTART" "$MENU_ENTRY" "$OLD_DESKTOP_ICON"
    [ -f "$PANEL_INI" ] && sed -i '/^launcher_[0-9]*=home-dashboard\.desktop$/d' "$PANEL_INI"
    systemctl --user daemon-reload
    echo "Uninstalled. Saved countdowns and settings are still in $REPO/data/"
    exit 0
fi

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user (not with sudo); it asks for sudo itself where needed." >&2
    exit 1
fi

# --- What are we running on? ---
. /etc/os-release
case "${VERSION_CODENAME:-}" in
    bookworm | trixie) ;;
    *)
        echo "This needs Raspberry Pi OS Bookworm or Trixie; found ${PRETTY_NAME:-an unknown system}." >&2
        exit 1
        ;;
esac
if pgrep -x wayfire >/dev/null; then DESKTOP=Wayfire
elif pgrep -x labwc >/dev/null; then DESKTOP=labwc
elif pgrep -x Xorg >/dev/null || pgrep -x lxpanel >/dev/null; then DESKTOP=X11
else DESKTOP="not running (fine if installing over SSH; the kiosk checks again at login)"
fi
say "Installing Home Dashboard on $PRETTY_NAME, desktop: $DESKTOP"

# --- System: packages, boot to desktop, no screen blanking ---
if [ "${1:-}" != "--skip-system" ]; then
    say "System setup (asks for your password if sudo needs it)"
    missing=()
    for pkg in python3-venv git curl; do
        dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
        missing+=(chromium)
    fi
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Installing: ${missing[*]}"
        sudo apt-get update -qq
        # Bookworm images from before late 2024 only know the browser as chromium-browser
        sudo apt-get install -y -qq "${missing[@]}" ||
            sudo apt-get install -y -qq "${missing[@]/chromium/chromium-browser}"
    fi
    if command -v raspi-config >/dev/null; then
        # raspi-config knows how each desktop (Wayfire, labwc, X11) does these
        sudo raspi-config nonint do_boot_behaviour B4 # boot to the desktop, logged in
        sudo raspi-config nonint do_blanking 1        # 1 = never blank the screen
        echo "Boot straight to the desktop: on. Screen blanking: off."
    else
        warn "raspi-config not found: set the Pi to log in to the desktop automatically, and turn off screen blanking, yourself."
    fi
fi

# --- Python packages for reading calendars ---
say "Python packages"
[ -x "$REPO/.venv/bin/python" ] || python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install -q --disable-pip-version-check -r "$REPO/requirements.txt"
echo "Ready in $REPO/.venv"

# --- Dashboard service, kiosk, launchers ---
say "Dashboard"
mkdir -p "$UNIT_DIR" "$(dirname "$AUTOSTART")" "$(dirname "$MENU_ENTRY")" "$REPO/data"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.service" >"$UNIT"
for unit in "${REFRESH_UNITS[@]}"; do cp "$REPO/deploy/$unit" "$UNIT_DIR/$unit"; done
sed "s|@REPO@|$REPO|g" "$REPO/deploy/home-dashboard.desktop" >"$AUTOSTART"
cp "$AUTOSTART" "$MENU_ENTRY"
rm -f "$OLD_DESKTOP_ICON"
chmod +x "$REPO/start_dashboard.sh"

# Taskbar button: appended after the existing launchers, once. Wayfire and labwc share this
# taskbar (wf-panel-pi); the X11 desktop's taskbar isn't handled, but the menu entry still works.
if [ -f "$PANEL_INI" ] && ! grep -q '^launcher_[0-9]*=home-dashboard\.desktop$' "$PANEL_INI"; then
    last=$(grep -oE '^launcher_[0-9]+' "$PANEL_INI" | sort | tail -1 || true)
    if [ -n "$last" ]; then
        next=$(printf 'launcher_%06d' $((10#${last#launcher_} + 1)))
        sed -i "/^${last}=/a ${next}=home-dashboard.desktop" "$PANEL_INI"
    else
        sed -i '/^\[panel\]$/a launcher_000001=home-dashboard.desktop' "$PANEL_INI"
    fi
elif [ ! -f "$PANEL_INI" ]; then
    warn "No wf-panel-pi taskbar found, so no taskbar button; use Home Dashboard in the menu (Accessories)."
fi

systemctl --user daemon-reload
systemctl --user enable home-dashboard.service
systemctl --user restart home-dashboard.service
systemctl --user enable --now home-dashboard-refresh.timer

say "Done"
echo "Server: $(systemctl --user is-active home-dashboard.service)"
echo "Nightly browser refresh: $(systemctl --user show -p NextElapseUSecRealtime --value home-dashboard-refresh.timer)"
echo "The dashboard starts at the next login (or reboot), or now from the Home Dashboard taskbar button."
echo "Set it up from a phone on the same Wi-Fi: http://$(hostname).local:8000"
