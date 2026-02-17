#!/usr/bin/env python3
"""
tv-helper.py — Single-process helper for common TV lookups.

Replaces 10+ inline python3 -c calls in bash scripts.
Usage: tv-helper.py <command> [args...]

Commands:
  is_locked <ch_num>          Exit 0 if locked, 1 if not
  is_always_mute <ch_num>     Exit 0 if always-mute, 1 if not
  is_youtube <station>        Exit 0 if YouTube channel, 1 if not
  is_eas_exempt <station>     Exit 0 if EAS-exempt, 1 if not
  schedule_is_active <ch_num> Exit 0 if schedule block active, 1 if not
  offair_type <ch_num>        Print SIGNOFF/SIGNON or empty
  scheduled_show <ch_num>     Print show_id\tshow_path (tab-separated)
  re_lock_auto                Re-lock auto-lock channels
  mtv_metadata <file>         Print artist\ttitle\talbum\tyear
  mtv_overlay_json <text>     Print JSON-escaped string
"""

import json
import os
import re
import sys

BASE = "/home/retro"
CONFIG_DIR = f"{BASE}/config"
STATE_DIR = f"{BASE}/state"
PARENTAL_CONFIG = f"{CONFIG_DIR}/parental_lock.json"
YOUTUBE_CONFIG = f"{CONFIG_DIR}/youtube_channels.json"
EAS_CONFIG = f"{CONFIG_DIR}/eas_config.json"

# Lazy-loaded caches
_parental_cfg = None
_youtube_cfg = None
_eas_cfg = None


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def parental_cfg():
    global _parental_cfg
    if _parental_cfg is None:
        _parental_cfg = _load_json(PARENTAL_CONFIG)
    return _parental_cfg


def youtube_cfg():
    global _youtube_cfg
    if _youtube_cfg is None:
        _youtube_cfg = _load_json(YOUTUBE_CONFIG)
    return _youtube_cfg


def eas_cfg():
    global _eas_cfg
    if _eas_cfg is None:
        _eas_cfg = _load_json(EAS_CONFIG)
    return _eas_cfg


def cmd_is_locked(ch_num):
    locked = [str(x) for x in parental_cfg().get("locked_channels", [])]
    sys.exit(0 if ch_num in locked else 1)


def cmd_is_always_mute(ch_num):
    muted = [str(x) for x in parental_cfg().get("always_mute_channels", [])]
    sys.exit(0 if ch_num in muted else 1)


def cmd_is_youtube(station):
    sys.exit(0 if station in youtube_cfg() else 1)


def cmd_is_eas_exempt(station):
    exempt = eas_cfg().get("exempt_channels", [])
    sys.exit(0 if station in exempt else 1)


def cmd_schedule_is_active(ch_num):
    sys.path.insert(0, f"{BASE}/bin")
    import schedule_manager as sm
    cfg = sm.load_config()
    state = sm.load_state()
    result = sm.resolve_now(cfg, state, ch_num)
    sys.exit(0 if result and result.get("show_id") else 1)


def cmd_offair_type(ch_num):
    sys.path.insert(0, f"{BASE}/bin")
    import schedule_manager as sm
    cfg = sm.load_config()
    state = sm.load_state()
    result = sm.resolve_now(cfg, state, ch_num)
    if result and result.get("show_id") in ("SIGNOFF", "SIGNON"):
        print(result["show_id"])


def cmd_scheduled_show(ch_num):
    sys.path.insert(0, f"{BASE}/bin")
    import schedule_manager as sm
    cfg = sm.load_config()
    state = sm.load_state()
    result = sm.resolve_now(cfg, state, ch_num)
    if result and result.get("show_id"):
        show_id = result["show_id"]
        show_path = result.get("show", {}).get("path", "")
        print(f"{show_id}\t{show_path}")


def cmd_re_lock_auto():
    cfg = parental_cfg()
    auto = [str(x) for x in cfg.get("auto_lock_channels", [])]
    locked = [str(x) for x in cfg.get("locked_channels", [])]
    changed = False
    for ch in auto:
        if ch not in locked:
            locked.append(ch)
            changed = True
    if changed:
        cfg["locked_channels"] = locked
        with open(PARENTAL_CONFIG, "w") as f:
            json.dump(cfg, f, indent=2)


def cmd_mtv_metadata(filepath):
    artist = title = album = year = ""

    # Try .info.json first
    json_file = os.path.splitext(filepath)[0] + ".info.json"
    if os.path.exists(json_file):
        d = _load_json(json_file)
        title = d.get("title", "")
        artist = d.get("artist", "") or d.get("uploader", "") or d.get("channel", "")
        album = d.get("album", "")

        if " - " in title and not artist:
            parts = title.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        elif " - " in title:
            parts = title.split(" - ", 1)
            if not artist or artist == parts[0].strip():
                artist, title = parts[0].strip(), parts[1].strip()

        title = re.sub(
            r'\s*[\(\[](?:Official|Music|HD|4K|Remaster|Video|Lyric|Audio|Full).*?[\)\]]',
            '', title, flags=re.IGNORECASE
        ).strip()

        parent = os.path.basename(os.path.dirname(filepath))
        if parent.isdigit() and len(parent) == 4:
            year = parent
        elif d.get("upload_date", ""):
            year = d["upload_date"][:4]

        print(f"{artist}\t{title}\t{album}\t{year}")
        return

    # Fallback: ffprobe
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", filepath],
            capture_output=True, text=True, timeout=5
        )
        d = json.loads(result.stdout).get("format", {}).get("tags", {})
        title = d.get("title", "")
        artist = d.get("artist", "")
        album = d.get("album", "")

        if " - " in title and not artist:
            parts = title.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        elif " - " in title:
            parts = title.split(" - ", 1)
            if not artist or artist == parts[0].strip():
                artist, title = parts[0].strip(), parts[1].strip()

        title = re.sub(
            r'\s*[\(\[](?:Official|Music|HD|4K|Remaster|Video|Lyric|Audio|Full).*?[\)\]]',
            '', title, flags=re.IGNORECASE
        ).strip()

        parent = os.path.basename(os.path.dirname(filepath))
        if parent.isdigit() and len(parent) == 4:
            year = parent
        elif d.get("date", ""):
            year = d["date"][:4]

        print(f"{artist}\t{title}\t{album}\t{year}")
    except Exception:
        print(f"\t\t\t")


def cmd_mtv_overlay_json(text):
    print(json.dumps(text.replace("\\n", "\n")))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: tv-helper.py <command> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "is_locked": lambda: cmd_is_locked(args[0]),
        "is_always_mute": lambda: cmd_is_always_mute(args[0]),
        "is_youtube": lambda: cmd_is_youtube(args[0]),
        "is_eas_exempt": lambda: cmd_is_eas_exempt(args[0]),
        "schedule_is_active": lambda: cmd_schedule_is_active(args[0]),
        "offair_type": lambda: cmd_offair_type(args[0]),
        "scheduled_show": lambda: cmd_scheduled_show(args[0]),
        "re_lock_auto": lambda: cmd_re_lock_auto(),
        "mtv_metadata": lambda: cmd_mtv_metadata(args[0]),
        "mtv_overlay_json": lambda: cmd_mtv_overlay_json(args[0]),
    }

    fn = commands.get(cmd)
    if fn:
        try:
            fn()
        except (IndexError, Exception) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
