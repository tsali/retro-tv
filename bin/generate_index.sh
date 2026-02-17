#!/usr/bin/env bash
set -euo pipefail

BASE="/home/retro"
MEDIA="$BASE/media"
CHANNELS="$MEDIA/channels"
STATIONS="$BASE/state/stations.tsv"

mkdir -p "$CHANNELS"

while read -r station path enabled; do
  [[ "$station" =~ ^#|^$ ]] && continue
  [[ "$enabled" != "1" ]] && continue

  STATION="$(echo "$station" | tr '[:lower:]' '[:upper:]')"

  [[ "$path" =~ ^udp:// ]] && {
    echo "INDEX: Skipping live station $STATION"
    continue
  }

  OUT="$CHANNELS/$STATION/index.tsv"
  mkdir -p "$(dirname "$OUT")"
  : > "$OUT"

  find "$path" -type f \( -iname '*.mp4' -o -iname '*.mkv' \) | sort | while read -r f; do
    dur="$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$f" 2>/dev/null)"
    dur="${dur%.*}"
    [[ "$dur" =~ ^[0-9]+$ ]] && echo -e "$f\t$dur" >> "$OUT"
  done

  [[ -s "$OUT" ]] || echo "INDEX: No playable content in $STATION"
done < "$STATIONS"
