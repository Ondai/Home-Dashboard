# Home-Dashboard
Home Dashboard - Weather, Countdown Timer, etc.

Google Apps Script URL (used to retrieve current day's Google Calendar events)
https://script.google.com/home/projects/YOUR_PROJECT_ID/edit

## Running on the Pi

`server.py` serves the dashboard on port 8000 and stores countdowns and the background in
`data/state.json` (not in git). `start_dashboard.sh` shows it in Chromium kiosk mode and relaunches
it if it closes. To set both up (or apply changes after a pull):

```bash
deploy/install.sh
```

- **Leave the kiosk:** Settings (gear icon) → Exit to Desktop
- **Come back:** double-tap Home Dashboard on the desktop (also in the Pi menu under Accessories)
- **From a phone or PC on the same network:** http://raspberrypi.local:8000
- **Server logs:** `journalctl --user -u home-dashboard -f`
- **Remove it all:** `deploy/install.sh --uninstall`
