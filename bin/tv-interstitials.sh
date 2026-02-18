#!/usr/bin/env bash
# tv-interstitials.sh — interstitial helpers (bumper + commercial)

get_offair_type() {
  local ch_num
  ch_num="$(cat "$CHANNEL_FILE" 2>/dev/null)" || return 1
  python3 "$BASE/bin/tv-helper.py" offair_type "$ch_num" 2>/dev/null
}

is_offair() {
  local t
  t="$(get_offair_type 2>/dev/null)"
  [[ -n "$t" ]]
}

should_allow_interstitials() {
  local station
  station="$(current_station)"
  # No interstitials during EAS
  [[ -f "$STATE/eas_active_flag" ]] && return 1
  # No interstitials on special channels, MTV, or during off-air
  [[ "$station" != "$WEATHER_CHANNEL" && "$station" != "EPG" && "$station" != "bumpers" && "$station" != "commercials" ]] || return 1
  is_mtv_channel "$station" && return 1
  # No interstitials during SIGNOFF/SIGNON
  is_offair 2>/dev/null && return 1
  return 0
}

play_bumper() {
  local sel file
  sel="$(pick_now "bumpers")" || {
    log "Bumper: no valid content"
    return 1
  }
  file="$(cut -f1 <<<"$sel")"
  log "BUMPER $(basename "$file") @ 0s"
  mpv_loadfile "$file" 0
}

play_regular_commercial() {
  local sel file
  sel="$(pick_now "commercials")" || {
    log "Commercial: no valid content"
    return 1
  }
  file="$(cut -f1 <<<"$sel")"
  log "COMMERCIAL $(basename "$file") @ 0s"
  mpv_loadfile "$file" 0
}

pick_next_show() {
  local station="$1"

  # Try schedule-aware pick first (starts at episode beginning)
  if sel="$(pick_next_scheduled "$station" 2>/dev/null)" && [[ -n "$sel" ]]; then
    echo "$sel"
    return 0
  fi

  # Fallback: epoch-based next from full station index
  local idx total=0 now pos acc=0

  idx="$(index_file "$station")"
  [[ -s "$idx" ]] || return 1

  now=$(date +%s)

  while IFS=$'\t' read -r _ len; do
    [[ "$len" =~ ^[0-9]+$ ]] || continue
    total=$((total + len))
  done < "$idx"

  (( total > 0 )) || return 1
  pos=$(( now % total ))

  local found_current=0
  local first_file=""

  while IFS=$'\t' read -r path len; do
    [[ -n "$path" && "$len" =~ ^[0-9]+$ ]] || continue

    if [[ -z "$first_file" ]]; then
      first_file="$path"
    fi

    if (( found_current == 1 )); then
      echo -e "$path\t0"
      return 0
    fi

    if (( pos < acc + len )); then
      found_current=1
    fi

    acc=$((acc + len))
  done < "$idx"

  if [[ -n "$first_file" ]]; then
    echo -e "$first_file\t0"
    return 0
  fi

  return 1
}

###############################################################################
# HALF-HOUR PADDING HELPERS
###############################################################################
COUNTDOWN_VIDEO="$MEDIA/countdown.mp4"

seconds_until_next_half_hour() {
  local min sec half_sec
  min=$(date +%-M)
  sec=$(date +%-S)
  half_sec=$(( (min % 30) * 60 + sec ))
  echo $(( 1800 - half_sec ))
}

play_countdown() {
  local remaining="$1"
  # 61-second video counting 61→0; seek so the displayed number matches seconds left
  local seek=$(( 61 - remaining ))
  (( seek < 0 )) && seek=0
  (( seek > 60 )) && seek=60
  log "COUNTDOWN ${remaining}s (seek to ${seek}s in countdown.mp4)"
  mpv_loadfile "$COUNTDOWN_VIDEO" "$seek"
}

schedule_is_active() {
  local ch_num
  ch_num="$(cat "$CHANNEL_FILE" 2>/dev/null)" || return 1
  python3 "$BASE/bin/tv-helper.py" schedule_is_active "$ch_num" 2>/dev/null
}

play_next_content() {
  local station sel file seek
  station="$(current_station)"
  sel="$(pick_next_show "$station")" || {
    play_station "$station" || true
    return
  }
  file="$(cut -f1 <<<"$sel")"
  seek="$(cut -f2 <<<"$sel")"
  log "PLAY $station → $(basename "$file") @ ${seek}s"
  mpv_loadfile "$file" "$seek"
}

start_eof_watcher() {
  (
    log "EOF watcher started"

    local state="content"
    local interstitial_count=0
    local mtv_last_pos=""
    local mtv_stuck_count=0

    while sleep 1; do
      # Back off entirely during EAS playback
      [[ -f "$STATE/eas_active_flag" ]] && continue

      local eof idle
      eof="$(mpv_get_prop eof-reached 2>/dev/null || echo "false")"
      idle="$(mpv_get_prop idle-active 2>/dev/null || echo "false")"

      # MTV: check if we're in the last 7 seconds — show end overlay
      # Also detect stuck playback (position unchanged for 5+ seconds)
      local mtv_station
      mtv_station="$(current_station 2>/dev/null)" || true
      if is_mtv_channel "$mtv_station" 2>/dev/null; then
        local pos dur remaining
        pos="$(mpv_get_prop time-pos 2>/dev/null)" || true
        dur="$(mpv_get_prop duration 2>/dev/null)" || true
        if [[ "$pos" =~ ^[0-9]+(\.[0-9]+)?$ && "$dur" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
          remaining=$(( ${dur%.*} - ${pos%.*} ))
          if (( remaining <= 7 && remaining > 0 )); then
            mtv_show_end_overlay 2>/dev/null
          fi
        fi

        # Stuck detection: if position hasn't changed in 5 checks, force next
        local pos_int="${pos%.*}"
        if [[ "$pos_int" == "$mtv_last_pos" && -n "$pos_int" ]]; then
          mtv_stuck_count=$((mtv_stuck_count + 1))
          if (( mtv_stuck_count >= 5 )); then
            log "MTV STUCK: position unchanged for ${mtv_stuck_count}s — forcing next video"
            mtv_hide_overlay 2>/dev/null
            play_mtv "$mtv_station" || true
            mtv_stuck_count=0
            mtv_last_pos=""
            sleep 0.5
            continue
          fi
        else
          mtv_stuck_count=0
          mtv_last_pos="$pos_int"
        fi
      else
        mtv_stuck_count=0
        mtv_last_pos=""
      fi

      if [[ "$eof" == "true" || "$idle" == "true" ]]; then

        if [[ "$state" == "content" ]]; then
          # EPG/WEATHER manage their own refresh — skip EOF handling
          local cur_station
          cur_station="$(current_station 2>/dev/null)"
          if [[ "$cur_station" == "EPG" || "$cur_station" == "WEATHER" ]]; then
            sleep 1
            continue
          fi

          # MTV channels: just play next random video, no interstitials
          if is_mtv_channel "$cur_station" 2>/dev/null; then
            mtv_hide_overlay 2>/dev/null
            play_mtv "$cur_station" || true
            sleep 0.5
            continue
          fi

          # During off-air, handle SIGNON vs SIGNOFF differently
          local offair_type
          offair_type="$(get_offair_type 2>/dev/null)"
          if [[ "$offair_type" == "SIGNON" ]]; then
            # SIGNON: video played once, now start programming
            log "SIGNON complete — starting next show"
            state="content"
            play_next_content
          elif [[ "$offair_type" == "SIGNOFF" ]]; then
            # SIGNOFF: show test pattern after off-air video
            log "OFF-AIR: showing test pattern RAITEST.png"
            mpv_cmd '{ "command": ["loadfile", "'"$MEDIA/images/RAITEST.png"'", "replace"] }' || true
            mpv_cmd '{ "command": ["set_property", "pause", false] }' || true
          elif should_allow_interstitials; then
            state="interstitial"
            interstitial_count=0
            play_bumper || true
          else
            local station
            station="$(current_station)"
            play_station "$station" || true
          fi

        elif [[ "$state" == "interstitial" ]]; then
          interstitial_count=$((interstitial_count + 1))

          # Check if schedule is driving this channel
          if schedule_is_active 2>/dev/null; then
            # --- SCHEDULED MODE ---
            # Max 4 interstitials (~3-4 min), then check boundary or move on
            local remaining
            remaining="$(seconds_until_next_half_hour)"

            if (( remaining <= 60 )); then
              # Within 60s of a half-hour — play countdown then next show
              state="countdown"
              play_countdown "$remaining"
            elif (( interstitial_count < 4 )); then
              # Still under the cap — alternate bumpers and commercials
              if (( interstitial_count % 2 == 1 )); then
                play_regular_commercial || true
              else
                play_bumper || true
              fi
            else
              # Hit the cap — start next episode
              log "FILLER CAP: ${interstitial_count} interstitials played, starting next episode"
              state="content"
              play_next_content
            fi
          else
            # --- UNSCHEDULED MODE: original 1-2 interstitial behavior ---
            if [[ $interstitial_count -eq 1 ]]; then
              play_regular_commercial || true
            elif [[ $interstitial_count -eq 2 ]]; then
              if (( RANDOM % 2 == 0 )); then
                play_regular_commercial || true
              else
                state="content"
                play_next_content
              fi
            else
              state="content"
              play_next_content
            fi
          fi

        elif [[ "$state" == "countdown" ]]; then
          # Countdown video finished — start next show
          state="content"
          log "COUNTDOWN done — starting next show"
          play_next_content
        fi

        sleep 0.5
      fi
    done
  ) &
}
