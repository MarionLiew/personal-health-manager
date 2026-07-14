#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm" ]]; then
  echo "Usage: $0 --confirm" >&2
  exit 2
fi
TARGET="${HERMES_HOME:-$HOME/.hermes}/skills/personal-health-manager"
if [[ ! -d "$TARGET" ]]; then
  echo "Skill is not installed: $TARGET"
  exit 0
fi
rm -rf "$TARGET"
echo "Removed $TARGET"

