# Home Dashboard

A wall display for the family: the time, the weather, the next three days of your calendars, and
countdowns to the things you're looking forward to. It runs on a Raspberry Pi with any monitor
(a touchscreen is optional) and is managed from your phone.

## What you need

- A Raspberry Pi 4 or 5 with **Raspberry Pi OS with desktop** (Bookworm or Trixie), set up with
  Wi-Fi and a user account (Raspberry Pi Imager does this)
- A monitor; portrait orientation suits the layout best
- A US ZIP code (the weather comes from the US National Weather Service)

## Install

On the Pi, open a terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/Ondai/Home-Dashboard/main/deploy/bootstrap.sh | bash
```

It downloads the dashboard to `~/Home-Dashboard`, installs what it needs, sets the Pi to start
straight into the desktop without blanking the screen, and starts the dashboard. Then reboot.

## Set it up from your phone

The wall shows a QR code the first time. Scan it (or open `http://<your-pi>.local:8000`) on a phone
on the same Wi-Fi, tap the gear, and add:

- **Your ZIP code**, for the weather
- **Your calendars**: in Google Calendar on a computer, open Settings, pick a calendar under
  "Settings for my calendars", choose "Integrate calendar", and copy the
  **Secret address in iCal format**. Add one link per calendar. Outlook and iCloud calendars work
  too, with their shared `.ics` links.

Countdowns and backgrounds are set from the phone (or the touchscreen) as well. Changes show up on
the wall immediately.

## Day to day

- **Update:** Settings → Update Dashboard
- **Restart the Pi:** Settings → Reboot Dashboard
- **Leave the full-screen dashboard:** Settings → Advanced settings → Exit to Desktop;
  Show Dashboard (or the house button on the Pi's taskbar) brings it back
- **Server logs:** `journalctl --user -u home-dashboard -f`
- **Remove it:** `~/Home-Dashboard/deploy/install.sh --uninstall`

## How it fits together

- `server.py` serves the page on port 8000 and stores countdowns, background and household
  settings in `data/state.json`. `calendar_feed.py` reads the calendars.
- `dashboard.html` is the whole interface: the wall on the Pi itself, the remote on phones.
  Add `?dashboard` to the address to see the wall view on another screen.
- `start_dashboard.sh` runs Chromium full screen and reopens it if it closes.
- `deploy/` holds the installer and the services it sets up.
- `google_calendar_data.gs` is an optional Google Apps Script alternative to iCal links (it shows
  every calendar in an account at once); its web app link goes in Advanced settings.
- `tools/make_backgrounds.py` generates the seasonal, holiday and abstract backgrounds.
