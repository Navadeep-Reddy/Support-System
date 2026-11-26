#!/usr/bin/env bash
# Shared helpers for the local start/stop scripts.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTANCE_ID="$(printf '%s' "$ROOT_DIR" | cksum | awk '{print $1}')"
STATE_DIR="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/support-system-$(id -u)-${INSTANCE_ID}"

record_process() {
  local name="$1" pid="$2" started
  started="$(ps -p "$pid" -o lstart= | xargs)"
  [ -n "$started" ] || return 1
  printf '%s\n%s\n' "$pid" "$started" > "$STATE_DIR/$name.pid"
}

process_is_ours() {
  local name="$1" pid started current command expected
  [ -f "$STATE_DIR/$name.pid" ] || return 1
  { read -r pid; read -r started; } < "$STATE_DIR/$name.pid"
  [[ "$pid" =~ ^[0-9]+$ ]] && [ -n "$started" ] || return 1
  current="$(ps -p "$pid" -o lstart= 2>/dev/null | xargs)"
  command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  case "$name" in
    backend) expected="$ROOT_DIR/backend/.venv/bin/python -m uvicorn" ;;
    frontend) expected="$ROOT_DIR/frontend/node_modules/vite/bin/vite.js" ;;
    *) return 1 ;;
  esac
  [ "$current" = "$started" ] && [[ "$command" == *"$expected"* ]]
}

stop_process() {
  local name="$1" pid
  if ! process_is_ours "$name"; then
    [ ! -f "$STATE_DIR/$name.pid" ] || echo "No matching $name process; leaving unrelated processes alone."
    rm -f "$STATE_DIR/$name.pid"
    return 0
  fi
  read -r pid < "$STATE_DIR/$name.pid"
  echo "Stopping $name (PID $pid)..."
  kill "$pid" 2>/dev/null || true
  for _ in {1..100}; do
    if ! process_is_ours "$name"; then
      rm -f "$STATE_DIR/$name.pid"
      return 0
    fi
    sleep 0.1
  done
  echo "$name did not stop; it has not been force-killed." >&2
  return 1
}
