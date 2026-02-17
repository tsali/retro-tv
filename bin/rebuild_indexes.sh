#!/usr/bin/env bash
set -euo pipefail

BASE="/home/retro"
MEDIA="$BASE/media"
OUT="$MEDIA/channels"
LOG="$BASE/tv.log"
CHANNELS_TSV="$BASE/state/channels.tsv"
SCHEDULE_CONFIG="$BASE/config/schedule_config.json"

mkdir -p "$OUT"

log() {
  echo "[$(date '+%F %T')] INDEX: $*" >> "$LOG"
}

is_video() {
  case "${1,,}" in
    *.mp4|*.mkv|*.avi|*.mov|*.wmv|*.mpg|*.mpeg) return 0 ;;
    *) return 1 ;;
  esac
}

# Directories that are NOT TV channels (infrastructure content)
SKIP_DIRS="channels|images|bumpers|commercials|mtvads|offair|weather|MP3|MTV"

# Track which stations have content (for channel registration)
declare -a NEW_STATIONS=()

for dir in "$MEDIA"/*; do
  [[ -d "$dir" ]] || continue

  raw="$(basename "$dir")"
  # Skip non-channel directories (case-insensitive check)
  if echo "$raw" | grep -qiE "^($SKIP_DIRS)$"; then
    continue
  fi

  station="$(echo "$raw" | tr '[:lower:]' '[:upper:]')"
  index_dir="$OUT/$station"
  index="$index_dir/index.tsv"
  tmp="$index.tmp"

  # Handle symlinks (e.g. adult -> channels/adult)
  if [[ -L "$OUT/$station" ]]; then
    index="$dir/index.tsv"
    tmp="$dir/index.tsv.tmp"
  else
    mkdir -p "$index_dir"
  fi
  : > "$tmp"

  # Load existing index into cache for incremental indexing
  declare -A CACHE=()
  if [[ -f "$index" ]]; then
    while IFS=$'\t' read -r cached_path cached_dur; do
      [[ -n "$cached_path" && "$cached_dur" =~ ^[0-9]+$ ]] || continue
      CACHE["$cached_path"]="$cached_dur"
    done < "$index"
  fi

  found=0
  cache_hits=0

  while IFS= read -r -d '' f; do
    is_video "$f" || continue

    # Check cache: skip ffprobe for stable files (>48h old, already indexed)
    cached_dur="${CACHE[$f]:-}"
    if [[ -n "$cached_dur" ]]; then
      file_age=$(( $(date +%s) - $(stat -c %Y "$f") ))
      if (( file_age > 172800 )); then
        echo -e "$f\t$cached_dur" >> "$tmp"
        found=1
        cache_hits=$((cache_hits + 1))
        continue
      fi
    fi

    dur="$(ffprobe -v error -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null | cut -d. -f1)"

    [[ "$dur" =~ ^[0-9]+$ ]] || continue

    echo -e "$f\t$dur" >> "$tmp"
    found=1
  done < <(find "$dir" -type f -print0)
  unset CACHE

  if (( found )); then
    mv "$tmp" "$index"
    log "Indexed $station (recursive from $raw, $cache_hits cache hits)"
    NEW_STATIONS+=("$station")
  else
    rm -f "$tmp"
    log "No playable content in $raw ($station)"
  fi
done

###############################################################################
# AUTO-REGISTER NEW CHANNELS
###############################################################################
log "Checking for new channels to register..."

for station in "${NEW_STATIONS[@]}"; do
  # Skip if already in channels.tsv
  if grep -qi "	${station}	" "$CHANNELS_TSV" 2>/dev/null; then
    continue
  fi

  # Find the next available channel number (between 6-998)
  next_num=6
  while grep -q "^${next_num}	" "$CHANNELS_TSV" 2>/dev/null; do
    next_num=$((next_num + 1))
    (( next_num >= 999 )) && { next_num=0; break; }
  done

  if (( next_num == 0 )); then
    log "WARNING: No available channel numbers for $station"
    continue
  fi

  # Add to channels.tsv (disabled by default)
  echo -e "${next_num}\t${station}\t0" >> "$CHANNELS_TSV"
  log "NEW CHANNEL: Added $station as CH${next_num} (disabled)"

  # Add to schedule_config.json channels + shows list
  python3 -c "
import json
with open('$SCHEDULE_CONFIG') as f:
    cfg = json.load(f)

# Add channel entry if not present
ch_names = [c['name'] for c in cfg.get('channels', [])]
if '$station' not in ch_names:
    cfg.setdefault('channels', []).append({
        'number': $next_num,
        'name': '$station',
        'station': '$station'
    })

# Count episodes and estimate runtime from index
import os
idx_paths = [
    '$OUT/$station/index.tsv',
    '$MEDIA/${station,,}/index.tsv',
]
episodes = 0
avg_runtime = 22
for idx_path in idx_paths:
    if os.path.exists(idx_path):
        with open(idx_path) as f:
            lines = [l.strip().split('\t') for l in f if l.strip()]
        episodes = len(lines)
        if episodes > 0:
            total_sec = sum(int(p[1]) for p in lines if len(p) >= 2 and p[1].isdigit())
            avg_runtime = max(1, (total_sec // episodes) // 60)
        break

# Add show entry if not present
show_ids = [s['id'] for s in cfg.get('shows', [])]
if '$station' not in show_ids:
    cfg.setdefault('shows', []).append({
        'id': '$station',
        'title': '$station'.title(),
        'path': '$MEDIA/${station,,}' if os.path.isdir('$MEDIA/${station,,}') else '$OUT/$station',
        'episodes': episodes,
        'runtime_min': avg_runtime,
        'channel': $next_num
    })

with open('$SCHEDULE_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null && log "Registered $station in schedule config" || log "WARNING: Failed to register $station in schedule config"

done

###############################################################################
# AUTO-REGISTER MTV CHANNELS (channels.tsv only, NOT scheduler)
###############################################################################
MTV_DIR="$MEDIA/MTV"
MTV_BASE_CH=100
MTV_YEAR_START=101

if [[ -d "$MTV_DIR" ]]; then
  # Ensure main MTV channel exists
  if ! grep -q "	MTV	" "$CHANNELS_TSV" 2>/dev/null; then
    echo -e "${MTV_BASE_CH}\tMTV\t1" >> "$CHANNELS_TSV"
    log "NEW CHANNEL: Added MTV as CH${MTV_BASE_CH}"
  fi

  # Register year sub-channels in channels.tsv (no scheduler entry)
  next_mtv_ch=$MTV_YEAR_START
  for year_dir in "$MTV_DIR"/*/; do
    [[ -d "$year_dir" ]] || continue
    year="$(basename "$year_dir")"
    [[ "$year" =~ ^[0-9]{4}$ ]] || continue

    station="MTV${year}"

    # Check if any actual video files exist
    vid_count=$(find "$year_dir" -maxdepth 1 -type f \( -name "*.mp4" -o -name "*.mkv" -o -name "*.avi" \) ! -name "*.part" 2>/dev/null | wc -l)
    (( vid_count > 0 )) || continue

    # Skip if already registered
    if grep -qi "	${station}	" "$CHANNELS_TSV" 2>/dev/null; then
      continue
    fi

    # Find next available channel number
    while grep -q "^${next_mtv_ch}	" "$CHANNELS_TSV" 2>/dev/null; do
      next_mtv_ch=$((next_mtv_ch + 1))
    done

    echo -e "${next_mtv_ch}\t${station}\t1" >> "$CHANNELS_TSV"
    log "NEW CHANNEL: Added $station as CH${next_mtv_ch} (enabled)"
    next_mtv_ch=$((next_mtv_ch + 1))
  done
fi

###############################################################################
# BUILD MTV INDEXES (epoch-based playback, not random)
###############################################################################
if [[ -d "$MTV_DIR" ]]; then
  # Main MTV index (all videos recursively)
  mtv_idx_dir="$OUT/MTV"
  mkdir -p "$mtv_idx_dir"
  mtv_tmp="$mtv_idx_dir/index.tsv.tmp"
  : > "$mtv_tmp"
  mtv_found=0

  # Load existing MTV index into cache
  declare -A MTV_CACHE=()
  if [[ -f "$mtv_idx_dir/index.tsv" ]]; then
    while IFS=$'\t' read -r cached_path cached_dur; do
      [[ -n "$cached_path" && "$cached_dur" =~ ^[0-9]+$ ]] || continue
      MTV_CACHE["$cached_path"]="$cached_dur"
    done < "$mtv_idx_dir/index.tsv"
  fi
  mtv_cache_hits=0

  while IFS= read -r -d '' f; do
    is_video "$f" || continue

    cached_dur="${MTV_CACHE[$f]:-}"
    if [[ -n "$cached_dur" ]]; then
      file_age=$(( $(date +%s) - $(stat -c %Y "$f") ))
      if (( file_age > 172800 )); then
        echo -e "$f\t$cached_dur" >> "$mtv_tmp"
        mtv_found=1
        mtv_cache_hits=$((mtv_cache_hits + 1))
        continue
      fi
    fi

    dur="$(ffprobe -v error -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null | cut -d. -f1)"
    [[ "$dur" =~ ^[0-9]+$ ]] || continue
    echo -e "$f\t$dur" >> "$mtv_tmp"
    mtv_found=1
  done < <(find "$MTV_DIR" -type f ! -name "*.part" ! -name "*.info.json" -print0 2>/dev/null)
  unset MTV_CACHE

  if (( mtv_found )); then
    mv "$mtv_tmp" "$mtv_idx_dir/index.tsv"
    log "Indexed MTV (all videos, $mtv_cache_hits cache hits)"
  else
    rm -f "$mtv_tmp"
  fi

  # Per-year MTV indexes
  for year_dir in "$MTV_DIR"/*/; do
    [[ -d "$year_dir" ]] || continue
    year="$(basename "$year_dir")"
    [[ "$year" =~ ^[0-9]{4}$ ]] || continue

    station="MTV${year}"
    yr_idx_dir="$OUT/$station"
    mkdir -p "$yr_idx_dir"
    yr_tmp="$yr_idx_dir/index.tsv.tmp"
    : > "$yr_tmp"
    yr_found=0

    # Load existing per-year index into cache
    declare -A YR_CACHE=()
    if [[ -f "$yr_idx_dir/index.tsv" ]]; then
      while IFS=$'\t' read -r cached_path cached_dur; do
        [[ -n "$cached_path" && "$cached_dur" =~ ^[0-9]+$ ]] || continue
        YR_CACHE["$cached_path"]="$cached_dur"
      done < "$yr_idx_dir/index.tsv"
    fi
    yr_cache_hits=0

    while IFS= read -r -d '' f; do
      is_video "$f" || continue

      cached_dur="${YR_CACHE[$f]:-}"
      if [[ -n "$cached_dur" ]]; then
        file_age=$(( $(date +%s) - $(stat -c %Y "$f") ))
        if (( file_age > 172800 )); then
          echo -e "$f\t$cached_dur" >> "$yr_tmp"
          yr_found=1
          yr_cache_hits=$((yr_cache_hits + 1))
          continue
        fi
      fi

      dur="$(ffprobe -v error -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null | cut -d. -f1)"
      [[ "$dur" =~ ^[0-9]+$ ]] || continue
      echo -e "$f\t$dur" >> "$yr_tmp"
      yr_found=1
    done < <(find "$year_dir" -maxdepth 1 -type f ! -name "*.part" ! -name "*.info.json" -print0 2>/dev/null)
    unset YR_CACHE

    if (( yr_found )); then
      mv "$yr_tmp" "$yr_idx_dir/index.tsv"
      log "Indexed $station ($yr_cache_hits cache hits)"
    else
      rm -f "$yr_tmp"
    fi
  done
fi

log "Index rebuild complete"
