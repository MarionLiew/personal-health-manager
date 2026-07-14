#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$PROJECT_DIR/hermes_skill/personal-health-manager"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
TARGET_ROOT="$HERMES_ROOT/skills"
TARGET="$TARGET_ROOT/personal-health-manager"

command -v hermes >/dev/null || { echo "Hermes CLI not found" >&2; exit 1; }
test -f "$SOURCE/SKILL.md" || { echo "Skill source missing" >&2; exit 1; }
if [[ -e "$TARGET" ]]; then
  echo "Refusing to overwrite existing Skill: $TARGET" >&2
  exit 2
fi
mkdir -p "$TARGET_ROOT"
cp -R "$SOURCE" "$TARGET"
echo "Installed personal-health-manager at $TARGET"
echo "Run: $PROJECT_DIR/hermes_skill/verify.sh"

