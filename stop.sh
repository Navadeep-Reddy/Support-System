#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd -P)/scripts/local-common.sh"
cd "$ROOT_DIR"
if [ "$#" -ne 0 ]; then
  echo "Usage: ./stop.sh" >&2
  exit 2
fi

# Only terminate processes recorded by start.sh and still matching their identity.
stop_process frontend
stop_process backend

echo "Stopping this project's Docker services (database volumes are retained)..."
docker compose stop
echo "Stopped. Existing database data and logs were preserved."
