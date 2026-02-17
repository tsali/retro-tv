#!/usr/bin/env bash

STATUS="$HOME/state/status.json"

fmt() {
  printf "%02d:%02d:%02d" \
    $(( $1 / 3600 )) \
    $(( ($1 % 3600) / 60 )) \
    $(( $1 % 60 ))
}

echo "Last update: $(jq -r .updated "$STATUS")"
echo

jq -c '.channels | to_entries[]' "$STATUS" | while read -r row; do
  ch="$(jq -r .key <<<"$row")"
  now="$(jq -r .value.now <<<"$row")"
  next="$(jq -r .value.next <<<"$row")"
  e="$(jq -r .value.elapsed <<<"$row")"
  r="$(jq -r .value.remaining <<<"$row")"
  d="$(jq -r .value.duration <<<"$row")"

  echo "Channel: $ch"
  echo "  Now:       $now"
  echo "  Next:      $next"
  echo "  Elapsed:   $(fmt "$e")"
  echo "  Remaining: $(fmt "$r")"
  echo "  Duration:  $(fmt "$d")"
  echo
done
