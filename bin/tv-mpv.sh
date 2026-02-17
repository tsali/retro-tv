#!/usr/bin/env bash

###############################################################################
# MPV IPC HELPERS (robust, no jq)
###############################################################################

mpv_cmd() {
  [[ -S "$MPV_SOCKET" ]] || return 1
  printf '%s\n' "$1" | socat - UNIX-CONNECT:"$MPV_SOCKET" >/dev/null 2>&1
}

mpv_get_prop_raw() {
  # prints the raw JSON reply (or empty on failure)
  local prop="$1"
  [[ -S "$MPV_SOCKET" ]] || return 1
  printf '{ "command": ["get_property", "%s"] }\n' "$prop" \
    | socat - UNIX-CONNECT:"$MPV_SOCKET" 2>/dev/null || true
}

mpv_get_prop() {
  # extracts .data from mpv JSON reply
  # Handles strings and numbers; returns empty if not present.
  local prop="$1" raw data
  raw="$(mpv_get_prop_raw "$prop")"

  # fast path: success reply includes "data":
  # Examples:
  # {"data":123.45,"error":"success"}
  # {"data":"/path/file.mp4","error":"success"}
  data="$(printf '%s' "$raw" | sed -n 's/.*"data":\([^,}]*\).*/\1/p' | head -n1)"

  # strip quotes if present
  data="${data%\"}"
  data="${data#\"}"
  printf '%s' "$data"
}

###############################################################################
# CHANNEL OSD (90s green text)
###############################################################################
show_channel_osd() {
  local name="${1^^}"
  # 90s TV-style green monospace OSD — top-left, 5 seconds
  # ASS tags: \an7=top-left  \pos=offset from edge  \fs=size
  # \1c green text  \3c dark-green outline  \bord=border  \shad0=no shadow
  mpv_cmd '{ "command": ["expand-properties", "show-text", "${osd-ass-cc/0}{\\an7\\pos(48,32)\\fs30\\1c&H00FF00&\\3c&H004400&\\bord2\\shad0\\fnMonospace\\b1\\fsp2}'"$name"'", 5000] }' || true
}

###############################################################################
# LOAD + SEEK (epoch playback)
###############################################################################
mpv_loadfile() {
  local file="$1"
  local seek="${2:-0}"

  # Ask mpv to load immediately
  mpv_cmd '{ "command": ["loadfile", "'"$file"'", "replace"] }' || return 1

  # Wait (briefly) until mpv reports the expected path OR at least has a duration.
  # This is more reliable than watching "file-loaded" events.
  local i path dur
  for i in {1..20}; do
    path="$(mpv_get_prop path)"
    dur="$(mpv_get_prop duration)"

    # If mpv reports it is on our file, we're good.
    if [[ -n "$path" && "$path" == "$file" ]]; then
      break
    fi

    # If duration is a number (>0), file is likely ready enough.
    if [[ "$dur" =~ ^[0-9]+([.][0-9]+)?$ ]] && (( ${dur%.*} > 0 )); then
      break
    fi

    sleep 0.05
  done

  # Seek only if numeric and > 0
  if [[ "$seek" =~ ^[0-9]+$ ]] && (( seek > 0 )); then
    # First attempt
    mpv_cmd '{ "command": ["seek", '"$seek"', "absolute", "exact"] }' || true

    # If mpv wasn't ready, the seek can be ignored; retry once shortly after.
    sleep 0.15
    mpv_cmd '{ "command": ["seek", '"$seek"', "absolute", "exact"] }' || true
  fi

  # Ensure playback
  mpv_cmd '{ "command": ["set_property", "pause", false] }' || true
  return 0
}
