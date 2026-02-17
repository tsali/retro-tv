#!/usr/bin/env bash
# tv-eas.sh — Emergency Alert System module

EAS_CONFIG="$BASE/config/eas_config.json"
EAS_PENDING="$STATE/eas_pending"
EAS_ACTIVE_DIR="$STATE/eas_active"
EAS_ACTIVE_FLAG="$STATE/eas_active_flag"
EAS_RESUME_CHANNEL="$STATE/eas_resume_channel"

# Crawl state files
EAS_CRAWL_FLAG="$STATE/eas_crawl_active"
EAS_CRAWL_TEXT="$STATE/eas_crawl_text.txt"
EAS_CRAWL_EXPIRES="$STATE/eas_crawl_expires"

mkdir -p "$EAS_PENDING" "$EAS_ACTIVE_DIR"

is_eas_active() {
  [[ -f "$EAS_ACTIVE_FLAG" ]]
}

is_eas_exempt() {
  local station
  station="$(current_station 2>/dev/null)" || return 1
  python3 "$BASE/bin/tv-helper.py" is_eas_exempt "$station" 2>/dev/null
}

###############################################################################
# EAS CRAWL (scrolling ticker overlay)
###############################################################################
apply_eas_crawl() {
  log "EAS CRAWL: applying scrolling ticker"
  mpv_cmd '{ "command": ["vf", "add", "@eas_crawl:lavfi=[drawbox=x=0:y=0:w=iw:h=40:color=0x800000@0.9:t=fill,drawtext=textfile=/home/retro/state/eas_crawl_text.txt:fontcolor=white:fontsize=24:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf:y=8:x=w-mod(t*80\\,w+tw)]"] }' || true
}

remove_eas_crawl() {
  log "EAS CRAWL: removing scrolling ticker"
  mpv_cmd '{ "command": ["vf", "remove", "@eas_crawl"] }' || true
  rm -f "$EAS_CRAWL_FLAG" "$EAS_CRAWL_TEXT" "$EAS_CRAWL_EXPIRES"
}

build_crawl_text() {
  # Build crawl text from alert JSON: "EVENT for AREAS until EXPIRES. HEADLINE"
  local alert_file="$1"
  python3 -c "
import json, sys
from datetime import datetime
with open('$alert_file') as f:
    a = json.load(f)
event = a.get('event', 'ALERT')
areas = a.get('areas', 'your area')
headline = a.get('headline', '')
expires = a.get('expires', '')
exp_str = ''
if expires:
    try:
        dt = datetime.fromisoformat(expires)
        exp_str = dt.strftime('%I:%M %p')
    except Exception:
        exp_str = expires
parts = [event.upper()]
if areas:
    parts.append('for ' + areas)
if exp_str:
    parts.append('until ' + exp_str)
line = ' '.join(parts) + '.'
if headline:
    line += '  ' + headline
print(line)
" 2>/dev/null
}

get_crawl_expiry() {
  # Return expiry as unix timestamp; test alerts expire 2 min from now
  local alert_file="$1"
  python3 -c "
import json, time
from datetime import datetime
with open('$alert_file') as f:
    a = json.load(f)
expires = a.get('expires', '')
if expires:
    try:
        dt = datetime.fromisoformat(expires)
        print(int(dt.timestamp()))
    except Exception:
        print(int(time.time()) + 120)
else:
    print(int(time.time()) + 120)
" 2>/dev/null
}

###############################################################################
# EAS CRAWL WATCHER (background — re-applies crawl, checks expiry)
###############################################################################
start_eas_crawl_watcher() {
  (
    log "EAS crawl watcher started"

    while sleep 3; do
      # Skip if no crawl is active
      [[ -f "$EAS_CRAWL_FLAG" ]] || continue

      # Check expiry
      if [[ -f "$EAS_CRAWL_EXPIRES" ]]; then
        local exp_ts now_ts
        exp_ts="$(cat "$EAS_CRAWL_EXPIRES" 2>/dev/null)" || exp_ts=0
        now_ts="$(date +%s)"
        if (( now_ts >= exp_ts )); then
          log "EAS CRAWL: expired — removing"
          remove_eas_crawl
          continue
        fi
      else
        # No expiry file but flag exists — clean up
        remove_eas_crawl
        continue
      fi

      # Re-apply crawl filter (idempotent — if already present, mpv errors
      # silently and mpv_cmd swallows errors)
      apply_eas_crawl 2>/dev/null
    done
  ) &
}

###############################################################################
# MAIN EAS WATCHER
###############################################################################
start_eas_watcher() {
  (
    log "EAS watcher started"

    while sleep 1; do
      # Skip if EAS is already playing
      is_eas_active && continue

      # Check for pending alerts
      local pending_files
      pending_files=("$EAS_PENDING"/*.json)
      [[ -f "${pending_files[0]}" ]] || continue

      # Skip if on an exempt channel
      if is_eas_exempt 2>/dev/null; then
        # Clean up pending files silently on exempt channels
        for pf in "${pending_files[@]}"; do
          [[ -f "$pf" ]] && rm -f "$pf"
        done
        continue
      fi

      log "EAS: Alert(s) detected — interrupting programming"

      # Save current channel for resume
      current_station_number > "$EAS_RESUME_CHANNEL" 2>/dev/null || true

      # Set active flag (blocks EOF watcher)
      touch "$EAS_ACTIVE_FLAG"

      # Track start time for 60s minimum enforcement
      local eas_start_time
      eas_start_time="$(date +%s)"

      # Save last alert file for crawl text
      local last_alert_file=""

      # Process all pending alerts
      for alert_file in "${pending_files[@]}"; do
        [[ -f "$alert_file" ]] || continue

        log "EAS: Generating video for $(basename "$alert_file")"
        last_alert_file="$alert_file"

        # Write crawl text + expiry before processing (in case we need it later)
        local crawl_text crawl_expiry
        crawl_text="$(build_crawl_text "$alert_file")"
        crawl_expiry="$(get_crawl_expiry "$alert_file")"
        if [[ -n "$crawl_text" ]]; then
          printf '%s' "$crawl_text" > "$EAS_CRAWL_TEXT"
        fi
        if [[ -n "$crawl_expiry" ]]; then
          printf '%s' "$crawl_expiry" > "$EAS_CRAWL_EXPIRES"
        fi

        # Generate the EAS video
        local video_path
        video_path="$(python3 "$BASE/bin/eas_generate.py" "$alert_file" 2>/dev/null)"

        if [[ -z "$video_path" || ! -f "$video_path" ]]; then
          log "EAS: Failed to generate video for $(basename "$alert_file")"
          rm -f "$alert_file"
          continue
        fi

        # Remove processed pending file
        rm -f "$alert_file"

        # Play the EAS video
        log "EAS: Playing $video_path"
        mpv_loadfile "$video_path" 0

        # Wait for playback to finish (or user changes channel)
        sleep 2  # Let mpv load
        while true; do
          sleep 1
          local eof path
          eof="$(mpv_get_prop eof-reached 2>/dev/null || echo "false")"
          path="$(mpv_get_prop path 2>/dev/null || echo "")"

          # If user changed channel (path no longer matches), dismiss
          if [[ -n "$path" && "$path" != "$video_path" ]]; then
            log "EAS: User changed channel during alert — dismissing"
            # Clean up remaining pending alerts
            rm -f "$EAS_PENDING"/*.json 2>/dev/null
            break 2  # Break out of both loops
          fi

          # If EOF reached, move to next alert
          if [[ "$eof" == "true" ]]; then
            log "EAS: Alert playback complete"
            break
          fi
        done
      done

      # Enforce 60-second minimum display time
      local eas_elapsed eas_remaining
      eas_elapsed=$(( $(date +%s) - eas_start_time ))
      if (( eas_elapsed < 60 )); then
        eas_remaining=$(( 60 - eas_elapsed ))
        log "EAS: Enforcing 60s minimum — sleeping ${eas_remaining}s"
        sleep "$eas_remaining"
      fi

      # Clear active flag
      rm -f "$EAS_ACTIVE_FLAG"

      # Resume previous channel
      if [[ -f "$EAS_RESUME_CHANNEL" ]]; then
        local resume_ch
        resume_ch="$(cat "$EAS_RESUME_CHANNEL" 2>/dev/null)"
        rm -f "$EAS_RESUME_CHANNEL"
        if [[ -n "$resume_ch" ]]; then
          local station
          station="$(resolve_station_for_channel "$resume_ch" 2>/dev/null)"
          if [[ -n "$station" ]]; then
            log "EAS: Resuming channel $resume_ch ($station)"
            play_station "$station" || true
          fi
        fi
      fi

      # Activate the crawl overlay (if not on exempt channel and crawl text exists)
      if [[ -f "$EAS_CRAWL_TEXT" && -f "$EAS_CRAWL_EXPIRES" ]]; then
        if ! is_eas_exempt 2>/dev/null; then
          touch "$EAS_CRAWL_FLAG"
          sleep 0.5
          apply_eas_crawl
          log "EAS CRAWL: activated — will persist until expiry"
        fi
      fi

      # Clean up old generated videos (keep last 5)
      local old_videos
      old_videos=($(ls -t "$EAS_ACTIVE_DIR"/eas_*.mp4 2>/dev/null))
      if (( ${#old_videos[@]} > 5 )); then
        for ((i=5; i<${#old_videos[@]}; i++)); do
          rm -f "${old_videos[$i]}"
        done
      fi

    done
  ) &
}
