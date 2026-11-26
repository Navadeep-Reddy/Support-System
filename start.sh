#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd -P)/scripts/local-common.sh"
cd "$ROOT_DIR"

usage() {
  echo "Usage: ./start.sh [--seed]"
  echo "Starts Docker, the API and the frontend. --seed also refreshes demo account data and seeds missing knowledge articles."
}
seed_requested=false
case "${1:-}" in
  "") ;;
  --seed) seed_requested=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { usage >&2; exit 2; }

for command in docker uv npm node python3 curl ps; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done
docker compose version >/dev/null
API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
python3 - "$API_PORT" "$FRONTEND_PORT" <<'PY'
import socket, sys
ports = [int(value) for value in sys.argv[1:]]
if len(set(ports)) != 2 or any(port < 1 or port > 65535 for port in ports):
    sys.exit('API_PORT and FRONTEND_PORT must be different valid TCP ports.')
for port in ports:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError:
            sys.exit(f'Port {port} is already in use. Stop that service or choose different API_PORT/FRONTEND_PORT values.')
PY

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
for name in backend frontend; do
  if process_is_ours "$name"; then
    echo "$name is already running from this script. Run ./stop.sh first." >&2
    exit 1
  fi
done

if [ ! -f .env ] && [ ! -f backend/.env ]; then
  echo "Configure .env or backend/.env first; see README.md and the .env.example files." >&2
  exit 1
fi

echo "Starting Docker services..."
docker compose up -d --wait

echo "Installing backend dependencies..."
(cd backend && uv sync --locked)
(cd backend && .venv/bin/python - <<'PY'
from support_agent.core.config import get_settings
settings = get_settings()
if not settings.nvidia_api_key.get_secret_value().strip():
    print('Warning: NVIDIA_API_KEY is not set; agent and indexing calls will fail.')
if settings.session_secret.get_secret_value() in ('', 'insecure-local-development-secret-change-me', 'replace-with-a-random-local-secret'):
    print('Warning: configure a random SESSION_SECRET in backend/.env for signed demo sessions.')
PY
)
if [ ! -f frontend/node_modules/vite/bin/vite.js ]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm ci)
fi

echo "Checking demo data (first-time indexing may take a while)..."
if [ "$seed_requested" = true ]; then
  (cd backend && .venv/bin/python -m scripts.bootstrap_demo --refresh)
else
  (cd backend && .venv/bin/python -m scripts.bootstrap_demo)
fi

cleanup_on_failure() {
  local result=$?
  if [ "$result" -ne 0 ]; then
    echo "Startup failed; stopping processes launched by this script. Docker services remain running." >&2
    stop_process frontend || true
    stop_process backend || true
  fi
}
trap cleanup_on_failure EXIT

echo "Starting API..."
(cd backend && FRONTEND_ORIGIN="http://localhost:$FRONTEND_PORT" exec nohup "$ROOT_DIR/backend/.venv/bin/python" -m uvicorn support_agent.main:app --host 127.0.0.1 --port "$API_PORT") > "$STATE_DIR/backend.log" 2>&1 < /dev/null &
record_process backend "$!"
echo "Starting frontend..."
(cd frontend && VITE_API_BASE_URL="http://localhost:$API_PORT" exec nohup node "$ROOT_DIR/frontend/node_modules/vite/bin/vite.js" --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort) > "$STATE_DIR/frontend.log" 2>&1 < /dev/null &
record_process frontend "$!"

wait_for_service() {
  local name="$1" url="$2"
  for _ in {1..150}; do
    if ! process_is_ours "$name"; then
      echo "$name exited during startup. See $STATE_DIR/$name.log" >&2
      return 1
    fi
    if curl --silent --fail --max-time 1 "$url" >/dev/null; then return 0; fi
    sleep 0.2
  done
  echo "$name did not become ready. See $STATE_DIR/$name.log" >&2
  return 1
}
wait_for_service backend "http://127.0.0.1:$API_PORT/health"
wait_for_service frontend "http://127.0.0.1:$FRONTEND_PORT/"
trap - EXIT
printf '\nReady!\n  App:     http://localhost:%s\n  API:     http://localhost:%s/docs\n  Adminer: http://localhost:8080\n  Logs:    %s\nStop with ./stop.sh\n' "$FRONTEND_PORT" "$API_PORT" "$STATE_DIR"
