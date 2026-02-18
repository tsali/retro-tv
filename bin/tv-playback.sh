#!/usr/bin/env bash

###############################################################################
# PLAYBACK (epoch pick + special channels)
###############################################################################

index_file() {
  echo "$MEDIA/channels/$1/index.tsv"
}

###############################################################################
# EPG
###############################################################################
EPG_LAUNCHER="$BASE/start-epg-channel.sh"
EPG_FRAME="$STATE/epg/current.png"
EPG_PID_FILE="$STATE/epg/epg.pid"
EPG_REFRESH_PID=""
EPG_MUSIC_PID=""
EPG_STAMP="$BASE/bin/epg-stamp-time.py"
EPG_DISPLAY="$STATE/epg/display.png"
EPG_DISPLAY_TMP="$STATE/epg/display.tmp.png"
EPG_MUSIC_DIR="$MEDIA/mp3"

play_epg() {
  log "EPG → starting channel"

  # Start the generator daemon if not running
  bash "$EPG_LAUNCHER" start >/dev/null 2>&1

  # Wait briefly for first frame to be generated
  local wait=0
  while [[ ! -f "$EPG_FRAME" ]] && (( wait < 10 )); do
    sleep 1
    wait=$((wait + 1))
  done

  if [[ ! -f "$EPG_FRAME" ]]; then
    log "EPG: no frame available, showing placeholder"
    mpv_cmd '{ "command": ["loadfile", "'"$MEDIA/images/WEATHER.png"'", "replace"] }' || true
    return 1
  fi

  # Stamp time onto first frame and load it
  python3 "$EPG_STAMP" "$EPG_FRAME" "$EPG_DISPLAY_TMP" 2>/dev/null \
    && mv "$EPG_DISPLAY_TMP" "$EPG_DISPLAY" \
    && mpv_cmd '{ "command": ["loadfile", "'"$EPG_DISPLAY"'", "replace"] }' || \
    mpv_cmd '{ "command": ["loadfile", "'"$EPG_FRAME"'", "replace"] }' || true
  mpv_cmd '{ "command": ["set_property", "pause", false] }' || true

  # Start page cycling + time stamp loop (every 10s)
  stop_epg_refresh
  (
    local page=0
    while sleep 10; do
      local cur_station
      cur_station="$(current_station 2>/dev/null)" || true
      [[ "$cur_station" == "EPG" ]] || break

      # Read page count
      local page_count=1
      [[ -f "$STATE/epg/page_count" ]] && page_count="$(cat "$STATE/epg/page_count" 2>/dev/null)" || true
      [[ "$page_count" =~ ^[0-9]+$ ]] || page_count=1

      # Cycle to next page
      page=$(( (page + 1) % page_count ))
      local page_file="$STATE/epg/page_${page}.png"
      [[ -f "$page_file" ]] || page_file="$EPG_FRAME"

      # Stamp current time onto page and load
      if python3 "$EPG_STAMP" "$page_file" "$EPG_DISPLAY_TMP" 2>/dev/null \
          && mv "$EPG_DISPLAY_TMP" "$EPG_DISPLAY"; then
        mpv_cmd '{ "command": ["loadfile", "'"$EPG_DISPLAY"'", "replace"] }' || true
      else
        mpv_cmd '{ "command": ["loadfile", "'"$page_file"'", "replace"] }' || true
      fi
    done
  ) &
  EPG_REFRESH_PID=$!

  # Release main mpv audio device so music mpv can use HDMI
  mpv_cmd '{ "command": ["set_property", "audio-device", "null"] }' || true
  sleep 0.3

  # Start background music (separate mpv instance, shuffled mp3s)
  start_epg_music

  return 0
}

EPG_MUSIC_PIDFILE="$STATE/epg/music.pid"

start_epg_music() {
  stop_epg_music
  if [[ -d "$EPG_MUSIC_DIR" ]]; then
    mpv --no-video --shuffle --loop-playlist \
        --audio-device=alsa/hdmi:CARD=vc4hdmi0,DEV=0 \
        --audio-channels=stereo \
        --audio-samplerate=48000 \
        "--af=lavfi=[pan=stereo|c0=c0|c1=c0]" \
        "$EPG_MUSIC_DIR" >/dev/null 2>&1 &
    EPG_MUSIC_PID=$!
    echo "$EPG_MUSIC_PID" > "$EPG_MUSIC_PIDFILE"
    log "EPG: background music started (PID $EPG_MUSIC_PID)"
  fi
}

stop_epg_music() {
  # Kill any EPG background music mpv instances
  pkill -f 'mpv --no-video --shuffle --loop-playlist' 2>/dev/null && \
    log "EPG: background music stopped" || true
  rm -f "$EPG_MUSIC_PIDFILE"
  EPG_MUSIC_PID=""
  # Reclaim HDMI audio for main mpv
  mpv_cmd '{ "command": ["set_property", "audio-device", "alsa/hdmi:CARD=vc4hdmi0,DEV=0"] }' || true
}

stop_epg_refresh() {
  if [[ -n "$EPG_REFRESH_PID" ]]; then
    kill "$EPG_REFRESH_PID" 2>/dev/null
    EPG_REFRESH_PID=""
  fi
  stop_epg_music
}

###############################################################################
# WEATHER
###############################################################################
play_weather() {
  log "WEATHER → live stream"
  mpv_cmd '{ "command": ["loadfile", "'"$WEATHER_STREAM"'", "replace"] }' || true
  mpv_cmd '{ "command": ["set_property", "pause", false] }' || true
  return 0
}

###############################################################################
# NORMAL EPOCH PLAY
###############################################################################
pick_now() {
  local station="$1"
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

  while IFS=$'\t' read -r path len; do
    [[ -n "$path" && "$len" =~ ^[0-9]+$ ]] || continue
    if (( pos < acc + len )); then
      echo -e "$path\t$((pos - acc))"
      return 0
    fi
    acc=$((acc + len))
  done < "$idx"
}

###############################################################################
# SCHEDULE-AWARE PICK
###############################################################################
OFFAIR_VIDEO="$MEDIA/OFFAIR.mp4"
TESTPATTERN="$MEDIA/images/RAITEST.png"
TV_HELPER="$BASE/bin/tv-helper.py"

# Returns "show_id\tshow_path" in one call (replaces two separate Python calls)
get_scheduled_show() {
  local ch_num
  ch_num="$(cat "$CHANNEL_FILE" 2>/dev/null)" || return 1
  python3 "$TV_HELPER" scheduled_show "$ch_num" 2>/dev/null
}

get_scheduled_show_id() {
  local result
  result="$(get_scheduled_show)" || return 1
  cut -f1 <<<"$result"
}

get_scheduled_show_path() {
  local result
  result="$(get_scheduled_show)" || return 1
  cut -f2 <<<"$result"
}

pick_scheduled() {
  local station="$1"
  local show_path
  show_path="$(get_scheduled_show_path)" || return 1
  [[ -n "$show_path" && -d "$show_path" ]] || return 1

  local idx
  idx="$(index_file "$station")"
  [[ -s "$idx" ]] || return 1

  # Filter index to only entries from the scheduled show's directory
  local total=0 now pos acc=0
  local -a paths=() lengths=()

  while IFS=$'\t' read -r path len; do
    [[ -n "$path" && "$len" =~ ^[0-9]+$ ]] || continue
    [[ "$path" == "$show_path"/* ]] || continue
    paths+=("$path")
    lengths+=("$len")
    total=$((total + len))
  done < "$idx"

  (( total > 0 )) || return 1

  now=$(date +%s)
  pos=$(( now % total ))
  acc=0

  for i in "${!paths[@]}"; do
    if (( pos < acc + lengths[i] )); then
      echo -e "${paths[$i]}\t$((pos - acc))"
      return 0
    fi
    acc=$((acc + lengths[i]))
  done

  return 1
}

pick_next_scheduled() {
  local station="$1"
  local show_path
  show_path="$(get_scheduled_show_path)" || return 1
  [[ -n "$show_path" && -d "$show_path" ]] || return 1

  local idx
  idx="$(index_file "$station")"
  [[ -s "$idx" ]] || return 1

  local total=0 now pos acc=0
  local -a paths=() lengths=()

  while IFS=$'\t' read -r path len; do
    [[ -n "$path" && "$len" =~ ^[0-9]+$ ]] || continue
    [[ "$path" == "$show_path"/* ]] || continue
    paths+=("$path")
    lengths+=("$len")
    total=$((total + len))
  done < "$idx"

  (( total > 0 )) || return 1

  now=$(date +%s)
  pos=$(( now % total ))
  acc=0

  local found_current=0
  for i in "${!paths[@]}"; do
    if (( found_current == 1 )); then
      echo -e "${paths[$i]}\t0"
      return 0
    fi
    if (( pos < acc + lengths[i] )); then
      found_current=1
    fi
    acc=$((acc + lengths[i]))
  done

  # Wrap to first episode
  if (( ${#paths[@]} > 0 )); then
    echo -e "${paths[0]}\t0"
    return 0
  fi
  return 1
}

###############################################################################
# PARENTAL LOCK / SCRAMBLE
###############################################################################
PARENTAL_CONFIG="$BASE/config/parental_lock.json"
PARENTAL_UNLOCKED="$STATE/parental_unlocked"

is_channel_locked() {
  local ch_num="$1"
  [[ -f "$PARENTAL_CONFIG" ]] || return 1
  python3 "$TV_HELPER" is_locked "$ch_num" 2>/dev/null
}

re_lock_auto_channels() {
  [[ -f "$PARENTAL_CONFIG" ]] || return 0
  python3 "$TV_HELPER" re_lock_auto 2>/dev/null
}

is_always_mute_channel() {
  local ch_num="$1"
  [[ -f "$PARENTAL_CONFIG" ]] || return 1
  python3 "$TV_HELPER" is_always_mute "$ch_num" 2>/dev/null
}

apply_scramble() {
  log "SCRAMBLE: applying scramble effect"
  # Classic 90s scramble: horizontal displacement + color distortion + noise (labeled filter)
  mpv_cmd '{ "command": ["vf", "add", "@scramble:lavfi=[hue=H=t*90:s=3,noise=alls=80:allf=t,rgbashift=rh=30:bh=-30:gv=20]"] }' || true
  mpv_cmd '{ "command": ["set_property", "mute", true] }' || true
}

remove_scramble() {
  log "SCRAMBLE: removing scramble effect"
  mpv_cmd '{ "command": ["vf", "remove", "@scramble"] }' || true
  mpv_cmd '{ "command": ["set_property", "mute", false] }' || true
}

###############################################################################
# YOUTUBE LIVE STREAMS
###############################################################################
YOUTUBE_CONFIG="$BASE/config/youtube_channels.json"

play_youtube() {
  local station="$1"
  log "YOUTUBE → $station: extracting stream URL..."

  local url
  url="$(python3 -c "
import json
with open('$YOUTUBE_CONFIG') as f:
    cfg = json.load(f)
entry = cfg.get('$station', {})
print(entry.get('url', ''))
" 2>/dev/null)"

  if [[ -z "$url" ]]; then
    log "YOUTUBE → $station: no URL configured"
    return 1
  fi

  local stream_url
  stream_url="$(yt-dlp --get-url -f 'bestvideo[height<=720]' --no-warnings "$url" 2>/dev/null)" || {
    log "YOUTUBE → $station: yt-dlp failed, trying fallback quality..."
    stream_url="$(yt-dlp --get-url -f best --no-warnings "$url" 2>/dev/null)" || {
      log "YOUTUBE → $station: yt-dlp failed completely"
      mpv_loadfile "$MEDIA/snow.mp4" 0 || true
      return 1
    }
  }

  log "YOUTUBE → $station: stream acquired, loading..."
  mpv_cmd '{ "command": ["loadfile", "'"$stream_url"'", "replace"] }' || return 1
  sleep 1
  # Mute audio (video-only stream)
  mpv_cmd '{ "command": ["set_property", "mute", true] }' || true
  mpv_cmd '{ "command": ["set_property", "pause", false] }' || true
  return 0
}

is_youtube_channel() {
  local station="$1"
  [[ -f "$YOUTUBE_CONFIG" ]] || return 1
  python3 "$TV_HELPER" is_youtube "$station" 2>/dev/null
}

###############################################################################
# MAIN ENTRY
###############################################################################
play_station() {
  local station="$1"
  local sel file seek

  # Clear any existing scramble/unlock state on channel change
  rm -f "$PARENTAL_UNLOCKED"
  remove_scramble 2>/dev/null || true
  # Reset OSD positioning if leaving MTV channel
  mtv_reset_osd 2>/dev/null || true
  mtv_hide_overlay 2>/dev/null || true
  rm -f "$STATE/mtv_meta" 2>/dev/null
  # Re-lock auto-lock channels (e.g. 999) when tuning away
  re_lock_auto_channels 2>/dev/null || true

  # --- SPECIAL CHANNELS ---
  if [[ "$station" == "EPG" ]]; then
    play_epg
    return 0
  fi

  # Stop EPG refresh if leaving EPG channel
  stop_epg_refresh 2>/dev/null || true

  if [[ "$station" == "WEATHER" ]]; then
    play_weather
    return 0
  fi

  # --- MTV CHANNELS ---
  if is_mtv_channel "$station"; then
    play_mtv "$station"
    return 0
  fi

  # --- YOUTUBE LIVE STREAMS ---
  if is_youtube_channel "$station"; then
    play_youtube "$station"
    return $?
  fi

  # --- SIGNOFF / SIGNON ---
  local sched_id
  sched_id="$(get_scheduled_show_id 2>/dev/null)" || true
  if [[ "$sched_id" == "SIGNOFF" ]]; then
    # Check if this channel already went off-air (flag file per channel)
    local ch_num offair_flag
    ch_num="$(cat "$CHANNEL_FILE" 2>/dev/null)" || true
    offair_flag="$STATE/offair_ch${ch_num}"
    if [[ -f "$offair_flag" ]]; then
      # Already went off-air — show test pattern directly
      log "SIGNOFF (already off-air) → RAITEST.png"
      mpv_cmd '{ "command": ["loadfile", "'"$TESTPATTERN"'", "replace"] }' || true
      mpv_cmd '{ "command": ["set_property", "pause", false] }' || true
    else
      # First time going off-air — play OFFAIR.mp4, set flag
      log "SIGNOFF → OFFAIR.mp4"
      touch "$offair_flag"
      mpv_loadfile "$OFFAIR_VIDEO" 0
    fi
    return 0
  fi
  if [[ "$sched_id" == "SIGNON" ]]; then
    # SIGNON clears the offair flag — station is coming back on
    local ch_num_so offair_flag_so
    ch_num_so="$(cat "$CHANNEL_FILE" 2>/dev/null)" || true
    offair_flag_so="$STATE/offair_ch${ch_num_so}"
    rm -f "$offair_flag_so"
    log "SIGNON → OFFAIR.mp4"
    mpv_loadfile "$OFFAIR_VIDEO" 0
    return 0
  fi

  # Clear offair flag — normal content is playing
  local ch_num_clr
  ch_num_clr="$(cat "$CHANNEL_FILE" 2>/dev/null)" || true
  rm -f "$STATE/offair_ch${ch_num_clr}" 2>/dev/null

  # --- SCHEDULED CONTENT (try first) ---
  if sel="$(pick_scheduled "$station" 2>/dev/null)" && [[ -n "$sel" ]]; then
    file="$(cut -f1 <<<"$sel")"
    seek="$(cut -f2 <<<"$sel")"
    log "PLAY $station → $(basename "$file") @ ${seek}s [scheduled]"
    mpv_loadfile "$file" "$seek"
    # Apply scramble if channel is locked
    local ch_num
    ch_num="$(cat "$CHANNEL_FILE" 2>/dev/null)" || true
    if is_channel_locked "$ch_num" 2>/dev/null; then
      sleep 0.3
      apply_scramble
    fi
    return 0
  fi

  # --- FALLBACK: EPOCH CONTENT ---
  sel="$(pick_now "$station")" || {
    log "WARN: No valid content for $station — snow"
    mpv_loadfile "$MEDIA/snow.mp4" 0 || true
    return 1
  }

  file="$(cut -f1 <<<"$sel")"
  seek="$(cut -f2 <<<"$sel")"

  log "PLAY $station → $(basename "$file") @ ${seek}s"
  mpv_loadfile "$file" "$seek"

  # Apply scramble if channel is locked
  local ch_num
  ch_num="$(cat "$CHANNEL_FILE" 2>/dev/null)" || true
  if is_channel_locked "$ch_num" 2>/dev/null; then
    sleep 0.3
    apply_scramble
  fi
}
