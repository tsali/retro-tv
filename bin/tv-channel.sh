#!/usr/bin/env bash

# Channel number file + command file come from tv-env.sh
# CHANNEL_FILE = /home/retro/state/current_channel_number
# CHANNEL_CMD  = /home/retro/state/channel_cmd
# CHANNELS_TSV  = /home/retro/state/channels.tsv  (defined below)

CHANNELS_TSV="${STATE}/channels.tsv"

current_channel_number() {
  [[ -f "$CHANNEL_FILE" ]] && cat "$CHANNEL_FILE" || echo "2"
}

set_channel_number() {
  echo "$1" > "$CHANNEL_FILE"
}

# returns list of enabled channel numbers (sorted)
enabled_channels() {
  awk '
    $0 ~ /^#/ {next}
    NF < 3 {next}
    $3 == 1 {print $1}
  ' "$CHANNELS_TSV" | sort -n
}

# resolve station name for a given channel number
resolve_station_for_channel() {
  local ch="$1"
  awk -v C="$ch" '
    $0 ~ /^#/ {next}
    NF < 3 {next}
    $1 == C {print $2; exit}
  ' "$CHANNELS_TSV"
}

# current station (ALWAYS UPPERCASE)
current_station() {
  local st
  st="$(resolve_station_for_channel "$(current_channel_number)")"
  echo "${st^^}"
}

is_weather_channel() {
  [[ "$(current_station)" == "WEATHER" ]]
}

# wrap helpers
channel_up() {
  local cur next
  cur="$(current_channel_number)"

  next="$(enabled_channels | awk -v C="$cur" '$1 > C {print $1; exit}')"
  if [[ -z "${next:-}" ]]; then
    next="$(enabled_channels | head -n 1)"
  fi

  set_channel_number "$next"
}

channel_down() {
  local cur prev
  cur="$(current_channel_number)"

  prev="$(enabled_channels | awk -v C="$cur" '$1 < C {p=$1} END{print p}')"
  if [[ -z "${prev:-}" ]]; then
    prev="$(enabled_channels | tail -n 1)"
  fi

  set_channel_number "$prev"
}
