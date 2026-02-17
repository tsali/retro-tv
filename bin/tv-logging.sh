#!/usr/bin/env bash

log() {
  echo "[$(date '+%F %T')] $*" >> "$LOG"
}
