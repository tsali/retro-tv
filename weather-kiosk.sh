#!/usr/bin/env bash
set -e

DISPLAY_NUM=":1"
RES="1920x1080x24"
WIDTH="1920"
HEIGHT="1080"

URL="https://weatherstar.netbymatt.com/?hazards-checkbox=true&current-weather-checkbox=true&latest-observations-checkbox=true&hourly-checkbox=false&hourly-graph-checkbox=true&travel-checkbox=false&regional-forecast-checkbox=true&local-forecast-checkbox=true&extended-forecast-checkbox=true&almanac-checkbox=true&spc-outlook-checkbox=true&radar-checkbox=true&settings-wide-checkbox=true&settings-kiosk-checkbox=true&settings-stickyKiosk-checkbox=false&settings-scanLines-checkbox=false&settings-customFeedEnable-checkbox=false&settings-speed-select=1.00&settings-scanLineMode-select=thick&settings-units-select=us&settings-mediaVolume-select=0.75&txtLocation=Pensacola+Beach%2C+FL%2C+USA&latLon={%22lat%22%3A30.3316%2C%22lon%22%3A-87.1434}"

# Start virtual X server (memory-only)
Xvfb "$DISPLAY_NUM" -screen 0 "$RES" &
XVFB_PID=$!

sleep 1
export DISPLAY="$DISPLAY_NUM"

exec chromium \
  --kiosk \
  --window-size=${WIDTH},${HEIGHT} \
  --force-device-scale-factor=1 \
  --mute-audio \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-component-update \
  --disable-features=TranslateUI \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --disable-background-networking \
  --disable-sync \
  --disable-default-apps \
  --disable-extensions \
  --disable-breakpad \
  --disable-client-side-phishing-detection \
  --disable-gpu \
  --autoplay-policy=no-user-gesture-required \
  "$URL"
