#!/usr/bin/env bash
###############################################################################
# play_channel_scheduled.sh — Query the schedule manager for what to play now
#
# Usage: play_channel_scheduled.sh [channel_number]
#
# Queries schedule_manager.py for the current show on the given channel,
# then outputs the show's media path. Does NOT touch mpv or existing playback.
# Designed to be called by external scripts that want schedule-aware content.
###############################################################################

set -euo pipefail

BASE="/home/retro"
MANAGER="$BASE/bin/schedule_manager.py"
CONFIG="$BASE/config/schedule_config.json"

CHANNEL="${1:-}"

if [[ -z "$CHANNEL" ]]; then
    # Default: read current channel from existing state
    if [[ -f "$BASE/state/current_channel_number" ]]; then
        CHANNEL="$(cat "$BASE/state/current_channel_number")"
    else
        echo "Usage: play_channel_scheduled.sh CHANNEL_NUMBER" >&2
        exit 1
    fi
fi

# Query schedule manager
result="$(python3 "$MANAGER" now "$CHANNEL" 2>/dev/null)" || {
    echo "ERROR: schedule_manager.py failed" >&2
    exit 1
}

# Extract show_id from JSON
show_id="$(echo "$result" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ch = list(data.keys())[0] if data else None
if ch and data[ch].get('show_id'):
    print(data[ch]['show_id'])
else:
    print('')
" 2>/dev/null)"

if [[ -z "$show_id" ]]; then
    echo "NO_SHOW"
    exit 0
fi

# Look up show path from config
show_path="$(python3 -c "
import json
with open('$CONFIG') as f:
    cfg = json.load(f)
shows = {s['id']: s for s in cfg.get('shows', [])}
s = shows.get('$show_id', {})
print(s.get('path', ''))
" 2>/dev/null)"

if [[ -n "$show_path" && -d "$show_path" ]]; then
    echo "SHOW_ID=$show_id"
    echo "SHOW_PATH=$show_path"
    # Also output a random file from the show directory for convenience
    file="$(find "$show_path" -maxdepth 1 -type f \( -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' \) | shuf -n1)"
    if [[ -n "$file" ]]; then
        echo "SHOW_FILE=$file"
    fi
elif [[ -n "$show_path" ]]; then
    echo "SHOW_ID=$show_id"
    echo "SHOW_PATH=$show_path"
    echo "WARN: path does not exist" >&2
else
    echo "SHOW_ID=$show_id"
    echo "SHOW_PATH=UNKNOWN"
fi
