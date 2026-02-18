#!/usr/bin/env bash
# start-epg-channel.sh — Start EPG generator daemon
# Called by play_epg() in tv-playback.sh
#
# Starts epg-generator.py as a background process if not already running.
# The generator renders PNG frames to /home/retro/state/epg/current.png

BASE="/home/retro"
EPG_SCRIPT="$BASE/bin/epg-generator.py"
EPG_PID_FILE="$BASE/state/epg/epg.pid"
EPG_DIR="$BASE/state/epg"

mkdir -p "$EPG_DIR"

is_epg_running() {
    [[ -f "$EPG_PID_FILE" ]] || return 1
    local pid
    pid="$(cat "$EPG_PID_FILE" 2>/dev/null)"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_epg() {
    if is_epg_running; then
        return 0
    fi

    python3 "$EPG_SCRIPT" >> "$BASE/epg.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$EPG_PID_FILE"
    echo "EPG generator started (PID $pid)"
}

stop_epg() {
    if [[ -f "$EPG_PID_FILE" ]]; then
        local pid
        pid="$(cat "$EPG_PID_FILE" 2>/dev/null)"
        if [[ -n "$pid" ]]; then
            kill "$pid" 2>/dev/null
            rm -f "$EPG_PID_FILE"
            echo "EPG generator stopped"
        fi
    fi
}

case "${1:-start}" in
    start) start_epg ;;
    stop)  stop_epg ;;
    restart) stop_epg; sleep 1; start_epg ;;
    status)
        if is_epg_running; then
            echo "EPG running (PID $(cat "$EPG_PID_FILE"))"
        else
            echo "EPG not running"
        fi
        ;;
    *) echo "Usage: $0 {start|stop|restart|status}" ;;
esac
