#!/usr/bin/env bash

for i in {1..50}; do
  if aplay -l >/dev/null 2>&1; then
    exit 0
  fi
  sleep 0.2
done

echo "Audio not ready" >&2
exit 1
