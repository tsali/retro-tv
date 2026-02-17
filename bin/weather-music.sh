#!/usr/bin/env bash
MUSIC_DIR="/home/retro/media/mp3"
MUSIC_PID_FILE="/tmp/weather-music.pid"

start_music() {
    stop_music
    local playlist="/tmp/weather-music.m3u"
    find "$MUSIC_DIR" -type f \( -iname "*.mp3" -o -iname "*.m4a" -o -iname "*.flac" \) | shuf > "$playlist"
    nohup mpv --audio-device=pulse --no-video --loop-playlist=inf --no-terminal --playlist="$playlist" >/dev/null 2>&1 &
    echo $! > "$MUSIC_PID_FILE"
}

stop_music() {
    if [[ -f "$MUSIC_PID_FILE" ]]; then
        kill $(cat "$MUSIC_PID_FILE") 2>/dev/null || true
        rm -f "$MUSIC_PID_FILE"
    fi
}

case "${1:-}" in
    start) start_music ;;
    stop) stop_music ;;
    *) echo "Usage: $0 {start|stop}"; exit 1 ;;
esac
