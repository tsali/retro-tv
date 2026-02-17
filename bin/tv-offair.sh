#!/usr/bin/env bash
# tv-offair.sh — offair state flags

is_offair_active() {
  [[ -f "$OFFAIR_FLAG" ]]
}

set_offair_active() {
  : > "$OFFAIR_FLAG"
}

clear_offair_active() {
  rm -f "$OFFAIR_FLAG"
}
