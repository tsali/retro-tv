#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# ENV
###############################################################################
BASE="/home/retro"
export DISPLAY=:0

LOCK="/tmp/retro-tv.lock"
exec 9>"$LOCK"
flock -n 9 || exit 0

###############################################################################
# LOG ROTATION (keep last log, truncate if > 5MB)
###############################################################################
for logfile in "$BASE/tv.log" "$BASE/scheduler.log"; do
  if [[ -f "$logfile" ]] && (( $(stat -c%s "$logfile" 2>/dev/null || echo 0) > 5242880 )); then
    mv -f "$logfile" "${logfile}.old"
  fi
done

###############################################################################
# SOURCE ALL MODULES
###############################################################################
source "$BASE/bin/tv-env.sh"
source "$BASE/bin/tv-logging.sh"
source "$BASE/bin/tv-mpv.sh"
source "$BASE/bin/tv-channel.sh"
source "$BASE/bin/tv-playback.sh"
source "$BASE/bin/tv-volume.sh"
source "$BASE/bin/tv-mtv.sh"
source "$BASE/bin/tv-interstitials.sh"
source "$BASE/bin/tv-eas.sh"

###############################################################################
# START MPV (ONCE)
###############################################################################
rm -f "$MPV_SOCKET"
log "Starting mpv"

mpv \
  --audio-device=alsa/hdmi:CARD=vc4hdmi0,DEV=0 \
  --fullscreen \
  --idle=yes \
  --keep-open=yes \
  --input-ipc-server="$MPV_SOCKET" \
  --no-terminal \
  "$MEDIA/snow.mp4" &

MPV_PID=$!

# Wait for IPC
for _ in {1..40}; do
  [[ -S "$MPV_SOCKET" ]] && break
  sleep 0.25
done

if [[ ! -S "$MPV_SOCKET" ]]; then
  log "FATAL: mpv IPC socket not available"
  exit 1
fi

log "mpv ready"

start_eof_watcher

###############################################################################
# INITIAL TUNE
###############################################################################
set_channel_number "$(current_channel_number)"
ch="$(current_channel_number)"
station="$(resolve_station_for_channel "$ch")"

if [[ -n "$station" ]]; then
  log "Initial playback → channel $ch ($station)"
  play_station "$station" || log "Initial playback failed — snow"
  show_channel_osd "$station"
else
  log "WARN: No station resolved — snow"
fi

###############################################################################
# WATCHERS
###############################################################################
log "Starting watchers"

###############################################################################
# CONTROL WATCHER (channel up/down / direct number)
###############################################################################
(
  log "Control watcher started"
  while true; do
    [[ -f "$CHANNEL_CMD" ]] || { sleep 0.1; continue; }

    cmd="$(cat "$CHANNEL_CMD")"
    rm -f "$CHANNEL_CMD"

    case "$cmd" in
      up)
        channel_up
        ;;
      down)
        channel_down
        ;;
      [0-9]*)
        # Check if on a locked channel and this is a PIN attempt
        if is_channel_locked "$(current_channel_number)" 2>/dev/null && \
           [[ ! -f "$PARENTAL_UNLOCKED" ]]; then
          pin="$(python3 -c "import json; print(json.load(open('$PARENTAL_CONFIG')).get('pin',''))" 2>/dev/null)"
          if [[ "$cmd" == "$pin" ]]; then
            log "PARENTAL: PIN correct — unlocking channel"
            touch "$PARENTAL_UNLOCKED"
            remove_scramble
            continue
          fi
        fi
        set_channel_number "$cmd"
        ;;
      *)
        log "Invalid channel_cmd: $cmd"
        continue
        ;;
    esac

    ch="$(current_channel_number)"
    station="$(resolve_station_for_channel "$ch")"

    log "Channel SET → $ch ($station)"
    play_station "$station" || log "play_station failed for channel $ch"
    show_channel_osd "$station"

  done
) &

###############################################################################
# VOLUME WATCHER
###############################################################################
(
  log "Volume watcher started"
  while true; do
    if [[ -f "$STATE/mute" ]]; then
      mpv_cmd '{ "command": ["cycle", "mute"] }' || true
      rm -f "$STATE/mute"
    fi

    if [[ -f "$STATE/volume" ]]; then
      delta="$(cat "$STATE/volume" 2>/dev/null || true)"
      rm -f "$STATE/volume"

      # TV behavior: volume change always unmutes
      mpv_cmd '{ "command": ["set_property", "mute", false] }' || true
      mpv_cmd '{ "command": ["add", "volume", '"$delta"'] }' || true
    fi

    sleep 0.1
  done
) &

###############################################################################
# EAS (Emergency Alert System)
###############################################################################
python3 "$BASE/bin/eas_poller.py" >> "$LOG" 2>&1 &
start_eas_watcher
start_eas_crawl_watcher

###############################################################################
# WAIT
###############################################################################
wait "$MPV_PID"
