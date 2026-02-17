# Retro TV

A retro broadcast TV simulator that turns a Raspberry Pi into a fully functioning fake TV station. It plays scheduled programming across multiple channels with commercial breaks, bumpers, sign-on/sign-off sequences, an Emergency Alert System, MTV-style music video channels, a weather channel, parental controls, and web-based schedule management — all driven by a single mpv instance.

Built and tested on a **Raspberry Pi 4 Model B**. Other Pi models (or any Linux box with HDMI out) may work but are untested.

## How It Works

The system runs a single **mpv** media player instance in fullscreen, controlled entirely through a Unix IPC socket (`/tmp/mpv-socket`). A collection of bash and Python scripts orchestrate what plays and when:

- **Epoch-based playback** — When no schedule is set, content plays in a deterministic loop. The system calculates `current_time % total_channel_duration` to pick a file and seek position, so switching away and back resumes exactly where you'd expect on a "live" broadcast.
- **Scheduled programming** — Time-slot blocks assign specific shows to channels at specific hours. A web UI (port 8081) lets you drag-and-drop a weekly schedule.
- **Channel switching** — 22+ channels defined in a TSV file. Switching is done via a state file that the control watcher picks up, or through the web remote (port 8080).
- **Interstitials** — Between shows, the system plays bumpers and commercials from dedicated directories, with a countdown timer synced to the next half-hour boundary.
- **Everything is file-driven** — Channel commands, volume changes, mute toggles, and EAS alerts all flow through small state files in `/home/retro/state/`. This makes it easy to integrate any input method (IR remote, web UI, GPIO buttons, etc.).

### System Architecture

```
┌─────────────────────────────────────────────────┐
│                   start_tv.sh                    │
│  Sources all modules, launches mpv + watchers    │
├──────────┬──────────┬──────────┬────────────────┤
│ EOF      │ Channel  │ Volume   │ EAS            │
│ Watcher  │ Watcher  │ Watcher  │ Poller         │
│ (bumpers,│ (up/down,│ (mute,   │ (NWS API,      │
│  filler) │  direct) │  level)  │  alerts)       │
└────┬─────┴────┬─────┴────┬─────┴───────┬────────┘
     │          │          │             │
     └──────────┴──────────┴─────────────┘
                     │
              socat → /tmp/mpv-socket
                     │
                 ┌───┴───┐
                 │  mpv  │ → HDMI out
                 └───────┘
```

## Features

**Scheduled Programming** — Define weekly schedules per channel with a web-based editor. Shows play at their scheduled times with automatic seek to the correct position.

**Channel Switching** — Navigate channels with up/down commands or direct channel numbers. On-screen display shows channel info in retro green monospace text.

**Commercial Breaks & Bumpers** — Between shows, the system plays bumpers and commercials from dedicated media directories, capped at 4 per half-hour block.

**Countdown Timer** — A generated countdown video plays in the final 60 seconds before a half-hour boundary, synced to real time.

**Sign-On / Sign-Off** — Schedule SIGNOFF blocks to play an off-air animation followed by a classic test pattern (RAITEST.png). SIGNON reverses the process.

**Emergency Alert System (EAS)** — Polls the National Weather Service API for real-time alerts. Generates authentic SAME header tones, attention signals, and text-to-speech announcements as a video that interrupts all channels. A scrolling red ticker crawl persists after the alert.

**MTV Mode** — Dedicated music video channels (MTV, MTV1975–MTV1995) with epoch-shuffled playback and metadata overlays showing artist, title, album, and year in classic MTV lower-third style.

**Weather Channel** — Dedicated weather channel rendering via Chromium screenshots with background music.

**Parental Controls** — Lock channels behind a PIN code. Locked channels display scrambled video (hue rotation, noise, RGB shift) with muted audio. Enter the PIN via the remote to unlock.

**Web Remote Control** — Browser-based remote (port 8080) for channel switching, volume, and system status.

**Schedule Editor** — Browser-based schedule grid (port 8081) with drag-and-drop time blocks, multi-day copy, and midnight wrap-around support.

## Prerequisites

### Hardware

- **Raspberry Pi 4 Model B** (recommended; other models/Linux systems may work)
- HDMI display
- Storage for media content (external drive or large SD card recommended)
- Network connection (required for EAS alerts; optional otherwise)

### System Packages

```bash
sudo apt update
sudo apt install -y \
  mpv \
  ffmpeg \
  socat \
  python3 \
  python3-pip \
  python3-flask \
  python3-pil \
  pulseaudio \
  alsa-utils \
  jq
```

**Optional** (for weather channel rendering):
```bash
sudo apt install -y chromium-browser scrot
```

### Python Packages

If `python3-flask` and `python3-pil` aren't available as system packages:

```bash
pip3 install flask Pillow
```

All other Python dependencies use the standard library (`json`, `subprocess`, `datetime`, `urllib`, `wave`, `struct`, `math`, `os`, `pathlib`).

## Installation

1. **Clone the repo:**
   ```bash
   cd /home/retro
   git clone https://github.com/tsali/retro-tv.git
   # Or copy the repo contents to /home/retro/
   ```

2. **Set up media directories:**

   The system expects media content in `/home/retro/media/`. See [`media/README.md`](media/README.md) for the full expected structure. At minimum you need:
   ```
   media/
   ├── snow.mp4            # Static/snow fallback video
   ├── OFFAIR.mp4          # Sign-off animation
   ├── images/
   │   ├── RAITEST.png     # Test pattern (included)
   │   └── WEATHER.png     # Weather placeholder (included)
   ├── commercials/        # Commercial break clips
   ├── bumpers/            # Station bumper clips
   └── channels/
       └── <STATION_NAME>/ # One directory per station with video files
   ```

3. **Build content indexes:**
   ```bash
   bin/rebuild_indexes.sh
   ```
   This scans each channel directory and creates `index.tsv` files with file paths and durations.

4. **Configure PulseAudio for HDMI:**
   ```bash
   bin/setup-pulseaudio.sh
   ```

5. **Install systemd services:**
   ```bash
   sudo cp services/*.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable tv.service tv-web.service tv-schedule.service
   ```

6. **Start it up:**
   ```bash
   sudo systemctl start tv.service
   ```

   Or run directly:
   ```bash
   ./start_tv.sh
   ```

## Configuration

### Channels (`state/channels.tsv`)

Tab-separated file defining available channels:
```
2	CARTOONS	1
3	WEATHER	1
4	SCIFI	1
5	TRAINING	1
100	MTV	1
999	ADULT	0
```
Format: `channel_number [TAB] station_name [TAB] enabled (1/0)`

### Schedule (`config/schedule_config.json`)

Defines shows and the default weekly schedule:
```json
{
  "shows": [
    {
      "id": "PACMAN",
      "title": "Pac-Man (1982)",
      "path": "/home/retro/media/cartoons/PAC-MAN1982",
      "station": "CARTOONS"
    }
  ],
  "default_schedule": {
    "monday": {
      "CARTOONS": [
        { "start": "06:00", "end": "12:00", "show_id": "PACMAN" }
      ]
    }
  }
}
```

Or use the web schedule editor at `http://<pi-ip>:8081`.

### EAS Alerts (`config/eas_config.json`)

```json
{
  "enabled": true,
  "latitude": 30.4774607,
  "longitude": -87.3138657,
  "poll_interval_seconds": 45,
  "alert_types": {
    "TOR": true,
    "SVR": true,
    "FFW": true
  },
  "exempt_channels": ["WEATHER"]
}
```
Set your coordinates and enable/disable specific alert types (tornado, severe thunderstorm, flash flood, etc.).

### Parental Controls (`config/parental_lock.json`)

```json
{
  "pin": "42069",
  "locked_channels": ["999"],
  "auto_lock_channels": ["999"],
  "always_mute_channels": ["999"]
}
```

## Systemd Services

| Service | Port | Description |
|---------|------|-------------|
| `tv.service` | — | Main TV system (mpv + all watchers) |
| `tv-web.service` | 8080 | Web-based remote control |
| `tv-schedule.service` | 8081 | Schedule editor UI |
| `weather-capture.service` | — | Weather screenshot capture (optional) |
| `weather-renderer.service` | — | Weather data rendering (optional) |

## File Structure

```
retro-tv/
├── start_tv.sh              # Main entry point
├── tv-web-control.py        # Web remote (Flask, port 8080)
├── tv-status.sh             # System status script
├── start-epg-channel.sh     # EPG channel launcher
├── wait_for_audio.sh        # Audio device readiness check
├── weather-kiosk.sh         # Weather renderer
├── weather-capture.sh       # Weather screenshot capture
├── bin/                     # Core modules
│   ├── tv-env.sh            # Environment variables
│   ├── tv-mpv.sh            # MPV IPC helpers
│   ├── tv-channel.sh        # Channel switching
│   ├── tv-playback.sh       # Content selection (epoch + schedule)
│   ├── tv-interstitials.sh  # Bumpers, commercials, countdown, EOF
│   ├── tv-eas.sh            # EAS alert interruption
│   ├── tv-offair.sh         # Sign-on/sign-off state
│   ├── tv-mtv.sh            # MTV metadata + playback
│   ├── tv-volume.sh         # Volume/mute watcher
│   ├── tv-control.sh        # Channel command watcher
│   ├── tv-logging.sh        # Log helpers
│   ├── tv-helper.py         # Python utility commands
│   ├── schedule_manager.py  # Schedule resolution logic
│   ├── schedule_web.py      # Schedule editor (Flask, port 8081)
│   ├── eas_generate.py      # EAS video/audio generator
│   ├── eas_poller.py        # NWS API polling daemon
│   ├── eas_geocode.py       # Location geocoding
│   ├── gen_countdown.py     # Countdown video generator
│   ├── generate_index.sh    # Single-channel index builder
│   ├── rebuild_indexes.sh   # All-channel index builder
│   ├── play_channel_scheduled.sh
│   ├── weather-music.sh     # Weather + music overlay
│   └── setup-pulseaudio.sh  # Audio setup
├── config/                  # Configuration files
├── state/                   # Runtime state (channels.tsv is the base)
├── services/                # Systemd unit files
└── media/                   # Content (see media/README.md)
```

## License

This project is provided as-is for personal/educational use.
