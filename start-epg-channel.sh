#!/usr/bin/env bash
# Start EPG Channel - generates live video stream

BASE="/home/retro"
EPG_SCRIPT="$BASE/epg-generator.py"
COMMERCIALS="$BASE/media/channels/commercials"

# Install dependencies if needed
install_deps() {
    pip3 install pillow requests --break-system-packages 2>/dev/null
}

# Generate EPG video stream
python3 "$EPG_SCRIPT" | \
ffmpeg -f rawvideo -pixel_format rgb24 -video_size 1920x1080 -framerate 30 -i pipe:0 \
       -f mpegts -codec:v mpeg2video -b:v 3M -maxrate 3M -bufsize 1M \
       pipe:1

# Note: This outputs to stdout, which can be piped to mpv
# Usage in your system: mpv --input-ipc-server=... pipe:///path/to/this/script
