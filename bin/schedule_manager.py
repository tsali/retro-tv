#!/usr/bin/env python3
"""
schedule_manager.py — Retro TV Schedule Manager

Manages a weekly TV schedule: which shows air when on which channels.
Reads config from /home/retro/config/schedule_config.json
Writes schedule state to /home/retro/state/schedule_state.json

Does NOT touch existing TV playback scripts or services.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path("/home/retro")
CONFIG_FILE = BASE / "config" / "schedule_config.json"
STATE_FILE = BASE / "state" / "schedule_state.json"
CHANNELS_TSV = BASE / "state" / "channels.tsv"
LOG_FILE = BASE / "scheduler.log"

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except OSError:
        pass


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"schedule": {}, "overrides": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def get_shows(config):
    """Return dict of show_id -> show info."""
    return {s["id"]: s for s in config.get("shows", [])}


def get_channels():
    """Return dict of channel_number -> channel info from channels.tsv."""
    channels = {}
    if CHANNELS_TSV.exists():
        with open(CHANNELS_TSV) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    num = parts[0]
                    name = parts[1]
                    enabled = parts[2] == "1"
                    channels[num] = {
                        "number": int(num),
                        "name": name,
                        "station": name,
                        "enabled": enabled,
                    }
    return channels


def channel_to_station(channel_number):
    """Convert a channel number to its station name via channels.tsv."""
    channels = get_channels()
    ch_info = channels.get(str(channel_number), {})
    return ch_info.get("station", "")


def get_schedule(config, state):
    """Return the merged schedule (config defaults + state overrides)."""
    base = config.get("default_schedule", {})
    overrides = state.get("schedule", {})
    merged = {}
    for day in DAYS:
        merged[day] = overrides.get(day, base.get(day, {}))
    return merged


def resolve_now(config, state, channel_number):
    """Determine what should be playing right now on a given channel.

    Returns: {"show_id": str, "show": dict, "block": dict} or None
    Properly checks end times.  Returns None when no block covers now,
    allowing the caller to fall back to epoch-based playback.
    SIGNOFF/SIGNON only triggers when explicitly scheduled.
    """
    now = datetime.now()
    day = DAYS[now.weekday()]
    current_time = now.strftime("%H:%M")

    schedule = get_schedule(config, state)
    day_schedule = schedule.get(day, {})
    station_key = channel_to_station(channel_number)
    blocks = day_schedule.get(station_key, []) if station_key else []

    if not blocks:
        return None

    shows = get_shows(config)

    # Find the best matching block (latest start that contains current_time)
    best = None
    for block in blocks:
        start = block.get("start", "00:00")
        end = block.get("end", "")
        # Treat empty or "00:00" end as end-of-day
        end_eff = "24:00" if (not end or end == "00:00") else end

        if start <= current_time < end_eff:
            if best is None or start > best.get("start", "00:00"):
                best = block

    if best:
        show_id = best.get("show_id")
        show = shows.get(show_id, {})
        return {"show_id": show_id, "show": show, "block": best}

    # No block covers current time — return None (caller falls back to epoch)
    return None


def what_is_on(channel_number=None):
    """Print what's on now, for all channels or a specific one."""
    config = load_config()
    state = load_state()
    channels = get_channels()

    targets = [channel_number] if channel_number else sorted(channels.keys(), key=int)

    results = {}
    for ch in targets:
        ch_info = channels.get(str(ch), {})
        result = resolve_now(config, state, ch)
        if result and result.get("show_id"):
            results[ch] = {
                "channel": ch_info.get("name", f"CH{ch}"),
                "show_id": result["show_id"],
                "title": result["show"].get("title", result["show_id"]),
                "start": result["block"].get("start"),
                "end": result["block"].get("end"),
            }
        else:
            results[ch] = {
                "channel": ch_info.get("name", f"CH{ch}"),
                "show_id": None,
                "title": "Off Air / Unscheduled",
            }
    return results


def set_block(day, station, start, end, show_id):
    """Add or update a schedule block. Station is the station name key."""
    state = load_state()
    if "schedule" not in state:
        state["schedule"] = {}
    if day not in state["schedule"]:
        config = load_config()
        state["schedule"][day] = config.get("default_schedule", {}).get(day, {})

    if station not in state["schedule"][day]:
        state["schedule"][day][station] = []

    blocks = state["schedule"][day][station]
    # Remove overlapping block at same start time
    blocks = [b for b in blocks if b.get("start") != start]
    blocks.append({"start": start, "end": end, "show_id": show_id})
    blocks.sort(key=lambda b: b.get("start", "00:00"))
    state["schedule"][day][station] = blocks
    save_state(state)
    log(f"SET {day} {station} {start}-{end} → {show_id}")


def remove_block(day, station, start):
    """Remove a schedule block. Station is the station name key."""
    state = load_state()
    if day in state.get("schedule", {}) and station in state["schedule"][day]:
        blocks = state["schedule"][day][station]
        state["schedule"][day][station] = [
            b for b in blocks if b.get("start") != start
        ]
        save_state(state)
        log(f"REMOVE {day} {station} @ {start}")


def reset_schedule():
    """Reset schedule state back to config defaults."""
    state = load_state()
    state["schedule"] = {}
    save_state(state)
    log("RESET schedule to defaults")


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: schedule_manager.py [now|set|remove|reset|shows|channels]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "now":
        ch = sys.argv[2] if len(sys.argv) > 2 else None
        results = what_is_on(ch)
        print(json.dumps(results, indent=2))

    elif cmd == "shows":
        config = load_config()
        for s in config.get("shows", []):
            print(f"  {s['id']:20s} {s.get('title', '')}")

    elif cmd == "channels":
        channels = get_channels()
        for num in sorted(channels.keys(), key=int):
            c = channels[num]
            print(f"  CH{c['number']:>3d}  {c.get('name', '')}")

    elif cmd == "set":
        if len(sys.argv) < 7:
            print("Usage: schedule_manager.py set DAY CHANNEL START END SHOW_ID")
            sys.exit(1)
        set_block(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
        print("OK")

    elif cmd == "remove":
        if len(sys.argv) < 5:
            print("Usage: schedule_manager.py remove DAY CHANNEL START")
            sys.exit(1)
        remove_block(sys.argv[2], sys.argv[3], sys.argv[4])
        print("OK")

    elif cmd == "reset":
        reset_schedule()
        print("Schedule reset to defaults")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
