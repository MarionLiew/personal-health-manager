#!/usr/bin/env bash
set -euo pipefail

# This wrapper deliberately knows the application location, not the database location.
PROJECT_DIR="/Users/marionliew/personal-health-agent"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "personal-health-agent project is unavailable: $PROJECT_DIR" >&2
  exit 127
fi

# Only the Hermes wrapper enables the exact, deployment-audited attachment cache.
export HEALTH_AGENT_CONFIG="$PROJECT_DIR/config/hermes.yaml"

if [[ -x "$PROJECT_DIR/.venv/bin/health" ]]; then
  exec "$PROJECT_DIR/.venv/bin/health" "$@"
fi

command -v uv >/dev/null 2>&1 || {
  echo "health CLI is unavailable: install uv or create the project virtual environment" >&2
  exit 127
}
exec uv run --project "$PROJECT_DIR" health "$@"
