#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$PROJECT_DIR/hermes_skill/personal-health-manager"
VALIDATOR="/Users/marionliew/.codex/skills/.system/skill-creator/scripts/quick_validate.py"

python3 "$VALIDATOR" "$SKILL"
uv run --project "$PROJECT_DIR" health doctor --json >/dev/null
if grep -Eiq '(sqlite3[[:space:]]+[^`]|psql[[:space:]]+[^`]|health\.sqlite3)' "$SKILL/SKILL.md"; then
  echo "Skill contains a prohibited direct database instruction" >&2
  exit 1
fi
grep -q 'health symptoms add' "$SKILL/references/command-map.md"
grep -q 'health followup postpone' "$SKILL/references/command-map.md"
grep -q 'health dicom dose-screen' "$SKILL/references/command-map.md"
grep -q -- '--candidate-ids' "$SKILL/references/wechat-examples.md"
grep -q 'Never run a database client' "$SKILL/SKILL.md"
echo "Skill structure and CLI integration verified"
