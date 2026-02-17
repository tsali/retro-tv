#!/usr/bin/env bash
set -euo pipefail

# Capture the WeatherStar renderer running in Xvfb :1 and stream it locally.
# Output is a low-latency MPEG-TS over UDP for mpv to tune instantly.

DISPLAY_NUM=":1"
SIZE="1920x1080"
FPS="30"
OUT_URL="udp://127.0.0.1:5600?pkt_size=1316&overrun_nonfatal=1"

# Give renderer/Xvfb a moment (systemd already orders services, but this helps)
sleep 1

# ffmpeg x11grab:
# - no audio
# - low latency
# - ultrafast encode to keep CPU reasonable on Pi 4
exec ffmpeg -hide_banner -loglevel warning -nostdin \
  -f x11grab -video_size "$SIZE" -framerate "$FPS" -i "${DISPLAY_NUM}.0" \
  -an \
  -vf "format=yuv420p" \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -g $((FPS*2)) -keyint_min $((FPS*2)) -sc_threshold 0 \
  -f mpegts "$OUT_URL"
