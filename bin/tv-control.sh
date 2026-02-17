#!/usr/bin/env bash

(
  log "Control watcher started"
  while true; do
    [[ -f "$STATE/channel_cmd" ]] || { sleep 0.1; continue; }

    cmd="$(cat "$STATE/channel_cmd")"
    rm -f "$STATE/channel_cmd"

    case "$cmd" in
      up)
        channel_up
        ;;
      down)
        channel_down
        ;;
      [0-9]*)
        echo "$cmd" > "$CURRENT_CHAN_NUM"
        ;;
      *)
        log "Invalid channel_cmd: $cmd"
        ;;
    esac

    station="$(resolve_current_station)"
    log_channel "$(cat "$CURRENT_CHAN_NUM")" "$station"
    play_now

  done
) &
