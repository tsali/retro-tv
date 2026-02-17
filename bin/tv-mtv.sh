#!/usr/bin/env bash

###############################################################################
# MTV CHANNEL — random music video playback with metadata overlay
###############################################################################

MTV_BASE="$MEDIA/MTV"

is_mtv_channel() {
  local station="$1"
  # Main MTV channel or year-specific sub-channels (MTV1980, MTV1987, etc.)
  [[ "$station" == "MTV" || "$station" =~ ^MTV[0-9]{4}$ ]]
}

# Get the media directory for an MTV station
mtv_media_dir() {
  local station="$1"
  if [[ "$station" == "MTV" ]]; then
    echo "$MTV_BASE"
  else
    # MTV1980 → ~/media/MTV/1980
    local year="${station:3}"
    echo "$MTV_BASE/$year"
  fi
}

# Pick a video using epoch-based selection with shuffled order.
# Uses now % total to seek into a playlist that's randomly shuffled per cycle.
# This means: random song order, but switching away and back lands mid-video.
mtv_pick_epoch() {
  local station="$1"
  local idx
  idx="$(index_file "$station")"
  [[ -s "$idx" ]] || return 1

  python3 -c "
import hashlib, time
entries = []
with open('$idx') as f:
    for line in f:
        parts = line.strip().split('\t')
        if len(parts) >= 2 and parts[1].isdigit():
            entries.append((parts[0], int(parts[1])))
if not entries:
    exit(1)
total = sum(d for _, d in entries)
now = int(time.time())
cycle = now // total
# Shuffle order based on cycle — stable within a cycle, random across cycles
entries.sort(key=lambda e: hashlib.md5(f'{e[0]}:{cycle}'.encode()).hexdigest())
pos = now % total
acc = 0
for path, dur in entries:
    if pos < acc + dur:
        offset = pos - acc
        # If within last 15s of the video, start from the beginning instead
        # Prevents seeking near EOF where mpv can freeze with keep-open
        if dur > 15 and offset > dur - 15:
            offset = 0
        print(f'{path}\t{offset}')
        break
    acc += dur
" || return 1
}

# Extract metadata for a music video file
# Returns: ARTIST\tTITLE\tALBUM\tYEAR
mtv_get_metadata() {
  local file="$1"
  python3 "$BASE/bin/tv-helper.py" mtv_metadata "$file" 2>/dev/null
}

# Configure OSD for bottom-left positioning (MTV style)
mtv_setup_osd() {
  mpv_cmd '{ "command": ["set_property", "osd-align-x", "left"] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-align-y", "bottom"] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-margin-x", 20] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-margin-y", 40] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-font-size", 32] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-bold", true] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-border-size", 2] }' || true
}

# Reset OSD to default centered positioning (for non-MTV channels)
mtv_reset_osd() {
  mpv_cmd '{ "command": ["set_property", "osd-align-x", "center"] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-align-y", "top"] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-margin-x", 25] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-margin-y", 22] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-font-size", 55] }' || true
  mpv_cmd '{ "command": ["set_property", "osd-bold", false] }' || true
}

# Show metadata overlay using show-text (bottom-left via OSD properties)
mtv_show_overlay() {
  local artist="$1" title="$2" album="$3" year="$4"
  local text=""

  # Build display text with newlines
  [[ -n "$artist" ]] && text="$artist"
  if [[ -n "$title" ]]; then
    [[ -n "$text" ]] && text="${text}\n"
    text="${text}${title}"
  fi
  if [[ -n "$album" && -n "$year" ]]; then
    text="${text}\n${album} (${year})"
  elif [[ -n "$year" ]]; then
    text="${text}\n${year}"
  elif [[ -n "$album" ]]; then
    text="${text}\n${album}"
  fi

  [[ -n "$text" ]] || return 0

  mtv_setup_osd

  # Escape for JSON
  local json_text
  json_text="$(python3 "$BASE/bin/tv-helper.py" mtv_overlay_json "$text" 2>/dev/null)" || json_text="\"$text\""

  mpv_cmd '{ "command": ["show-text", '"$json_text"', 7000] }' || true
}

mtv_hide_overlay() {
  # show-text auto-hides after duration, but we can force it
  mpv_cmd '{ "command": ["show-text", "", 1] }' || true
}

# Main MTV playback function
play_mtv() {
  local station="$1"
  local file seek artist title album year

  local sel
  sel="$(mtv_pick_epoch "$station")" || {
    log "MTV: no indexed videos for $station (run rebuild_indexes.sh)"
    mpv_loadfile "$MEDIA/snow.mp4" 0 || true
    return 1
  }

  file="$(cut -f1 <<<"$sel")"
  seek="$(cut -f2 <<<"$sel")"

  # Get metadata
  local meta
  meta="$(mtv_get_metadata "$file")" || true
  IFS=$'\t' read -r artist title album year <<< "$meta"

  log "MTV $station → $(basename "$file") @ ${seek}s | $artist - $title"

  # Load the video at the epoch-calculated position
  mpv_loadfile "$file" "$seek"

  # Show overlay after brief delay for video to start
  sleep 1
  mtv_show_overlay "$artist" "$title" "$album" "$year"

  # Store metadata for the end-of-video overlay trigger
  echo -e "$artist\t$title\t$album\t$year" > "$STATE/mtv_meta"

  # Schedule hide after 7 seconds
  (
    sleep 7
    mtv_hide_overlay
  ) &
}

# MTV end-of-video overlay — called by position watcher
mtv_show_end_overlay() {
  [[ -f "$STATE/mtv_meta" ]] || return 0
  local artist title album year
  IFS=$'\t' read -r artist title album year < "$STATE/mtv_meta"
  mtv_show_overlay "$artist" "$title" "$album" "$year"
}
