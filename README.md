# Home Dashboard

A wall display for the family: the time, the weather, the next three days of your calendars, and
countdowns to the things you're looking forward to. It runs on a Raspberry Pi with any monitor
(a touchscreen is optional) and is managed from your phone.

## What you need

- A Raspberry Pi (see [Hardware](#hardware)) with **Raspberry Pi OS with desktop** (Bookworm or
  Trixie), set up with Wi-Fi and a user account (Raspberry Pi Imager does this)
- A monitor; portrait orientation suits the layout best
- A US ZIP code (the weather comes from the US National Weather Service)

## Hardware

**Minimum: Raspberry Pi 4 with 2 GB. Recommended for a new purchase: Raspberry Pi 5 with 2 GB or
4 GB.**

Memory is what decides it. Measured on a Pi 5 running the dashboard alone:

| | Memory | Processor |
|---|---|---|
| Kiosk browser (Chromium) | ~450 MB | ~1.5% of one core while showing the dashboard |
| Desktop (window manager, taskbar, audio) | ~320 MB | |
| Dashboard server | ~25 MB | almost nothing |
| **Whole Pi** | **~1.0 GB in use** | a 1-second burst at start-up; the page is up in ~3 seconds |

| Raspberry Pi | Dashboard only |
|---|---|
| Pi 5 (2 GB or more) | Smooth, with lots of room to spare |
| Pi 4 (2 GB or more) | Smooth; start-up and opening Settings take a little longer |
| Pi 4 (1 GB) | Works, but it runs out of memory and slows down; not recommended |
| Pi 3 / 3B+ (1 GB) | Too little memory and too slow for the browser; not recommended |
| Pi Zero 2 W (512 MB) | Won't run the desktop and browser together |

Only the Pi 5 was measured; the other rows are estimates from its memory use and the boards'
relative speed.

Also needed:

- **A microSD card**, 16 GB minimum, 32 GB recommended (A1/A2-rated). The OS takes about 7 GB and the
  dashboard about 130 MB.
- **The official power supply** for the board (Pi 5: 27 W USB-C; Pi 4: 15 W USB-C). Underpowered
  supplies cause slowdowns and random restarts.
- **A micro-HDMI to HDMI cable** (Pi 4 and 5 use micro-HDMI).
- **Cooling** for a Pi 5: the official Active Cooler or a case with a heatsink. It sits around 60 °C
  showing the dashboard; a Pi 4 is fine with a basic heatsink case.
- **A touchscreen is optional**; everything can be done from a phone.

### Using the same Pi for more than the dashboard

The dashboard leaves most of a Pi 4 or 5 free, so it can share. Pick by the heaviest thing you'll
add:

| Also running | Pick | Notes |
|---|---|---|
| Pi-hole (network ad blocker) | Pi 4 or 5, 2 GB+ | Light (~100 MB). Use a wired network connection if you can. Its admin page uses port 80, so it doesn't clash with the dashboard on 8000 |
| Media player (Kodi, VLC) | Pi 5, 4 GB+ | Shares the screen: use Exit to Desktop to watch, then Show Dashboard |
| Retro games (RetroArch, EmulationStation) | Pi 5, 4 GB+ with the Active Cooler | Also takes over the screen; add a game controller |
| Media server (Plex, Jellyfin) or file sharing | Pi 5, 8 GB, with a USB or NVMe SSD | Video transcoding is heavy; keep media off the SD card |
| Home Assistant | A separate Pi (4 or 5, 4 GB+) | It's normally installed as its own operating system |
| Several of the above | Pi 5, 8 GB, Active Cooler, SSD | |

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

### Countdowns and count-ups

A countdown disappears by itself the day after its date, so the list stays current.

To count the days *since* something instead ("We met", "Days sober", "Since we moved in"), add it
with a date **before yesterday**: anything added with a date that far in the past is kept as a
count-up and shows "N Days Ago". If an old countdown was cleaned up and you'd like to keep counting
from it, add it again with its original date.

### Calendar events

Timed events drop off Today once they've ended. Events that span several days show which day it is,
like "(day 2/3)".

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
  every calendar in an account at once); its web app link goes in Advanced settings. Copies of the
  script from before October 2026 still work, but without hiding finished events or "(day 2/3)";
  paste in the current version and redeploy it to get those.
- `tools/make_backgrounds.py` generates the seasonal, holiday and abstract backgrounds.
