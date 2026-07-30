#!/bin/zsh
set -eu

if [[ $# -lt 4 || $# -gt 6 ]]; then
  print -u2 "usage: $0 <status-file> <expected-status> <delivery-file> <completion-marker> [timeout-seconds>=1] [poll-seconds>=1]"
  exit 64
fi

status_file="$1"
expected_status="$2"
delivery_file="$3"
completion_marker="$4"
timeout_seconds="${5:-1200}"
poll_seconds="${6:-20}"

if [[ "$status_file" != /* || "$delivery_file" != /* ]]; then
  print -u2 "status and delivery files must use absolute paths"
  exit 64
fi
if [[ -z "$expected_status" || "$expected_status" == *$'\n'* || -z "$completion_marker" || "$completion_marker" == *$'\n'* ]]; then
  print -u2 "status and marker must be non-empty single-line values"
  exit 64
fi
if [[ ! "$timeout_seconds" =~ '^[0-9]+$' || "$timeout_seconds" -lt 1 ]]; then
  print -u2 "timeout must be a positive integer"
  exit 64
fi
if [[ ! "$poll_seconds" =~ '^[0-9]+$' || "$poll_seconds" -lt 1 ]]; then
  print -u2 "poll interval must be a positive integer"
  exit 64
fi

deadline=$((SECONDS + timeout_seconds))
last_status="MISSING"

while true; do
  if [[ -f "$status_file" ]]; then
    last_status="$(LC_ALL=C head -c 128 "$status_file")"
    if [[ "$last_status" == *$'\n'* ]]; then
      last_status="INVALID_MULTILINE"
    fi
  else
    last_status="MISSING"
  fi

  if [[ "$last_status" == "$expected_status" && -f "$delivery_file" ]]; then
    last_line="$(tail -n 1 "$delivery_file" 2>/dev/null || true)"
    if [[ "$last_line" == "$completion_marker" ]]; then
      printf 'CLI_DELIVERY_COMPLETE\t%s\n' "$delivery_file"
      exit 0
    fi
  fi

  case "$last_status" in
    (*_BLOCKED_USER_DECISION|*_SCOPE_DRIFT|*_ERROR|*_ABORTED)
      printf 'CLI_ACTION_REQUIRED\tstatus=%s\n' "$last_status"
      exit 3
      ;;
  esac

  if (( SECONDS >= deadline )); then
    printf 'CLI_WAIT_TIMEOUT\tstatus=%s\ttimeout=%s\n' "$last_status" "$timeout_seconds" >&2
    exit 124
  fi

  sleep "$poll_seconds"
done
