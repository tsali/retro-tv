#!/usr/bin/env bash

BASE="/home/retro"
MEDIA="$BASE/media"
STATE="$BASE/state"
LOG="$BASE/tv.log"
MPV_SOCKET="/tmp/mpv-socket"

CHANNEL_FILE="$STATE/current_channel_number"
CHANNEL_CMD="$STATE/channel_cmd"

WEATHER_CHANNEL="WEATHER"
WEATHER_STREAM="udp://127.0.0.1:5600"
WEATHER_PLACEHOLDER="$MEDIA/images/WEATHER.png"

BUMPERS_CHANNEL="bumpers"
COMMERCIALS_CHANNEL="commercials"

EAS_CONFIG="$BASE/config/eas_config.json"
EAS_PENDING="$STATE/eas_pending"
EAS_ACTIVE_DIR="$STATE/eas_active"
EAS_ACTIVE_FLAG="$STATE/eas_active_flag"

mkdir -p "$STATE" "$EAS_PENDING" "$EAS_ACTIVE_DIR"
