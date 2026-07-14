#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$PROJECT_DIR/hermes_skill/personal-health-manager"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
INSTALLED="$HERMES_ROOT/skills/personal-health-manager"
VALIDATOR="/Users/marionliew/.codex/skills/.system/skill-creator/scripts/quick_validate.py"
WRAPPER="$SKILL/tools/health.sh"

python3 "$VALIDATOR" "$SKILL"
test -x "$WRAPPER" || { echo "health wrapper is not executable" >&2; exit 1; }
test -f "$SKILL/references/command-map.md"
test -f "$SKILL/references/wechat-examples.md"

doctor_json="$($WRAPPER doctor --json)"
db_json="$($WRAPPER db verify --json)"
python3 -c 'import json,sys; p=json.load(sys.stdin); assert p["status"] == "success"; assert p["data"]["healthy"] is True' <<<"$doctor_json"
python3 -c 'import json,sys; p=json.load(sys.stdin); assert p["status"] == "success"' <<<"$db_json"

if grep -REiq '(sqlite3[[:space:]]|psql[[:space:]]|health\.sqlite3|/data/)' "$SKILL"; then
  echo "Skill contains a prohibited direct database instruction" >&2
  exit 1
fi
grep -q 'health symptoms add' "$SKILL/references/command-map.md"
grep -q 'health followup postpone' "$SKILL/references/command-map.md"
grep -q 'health dicom dose-screen' "$SKILL/references/command-map.md"
grep -q 'health profile summary' "$SKILL/references/command-map.md"
grep -q 'health profile scar-add' "$SKILL/references/command-map.md"
grep -q 'health imaging list' "$SKILL/references/command-map.md"
grep -q 'Never diagnose a scar' "$SKILL/SKILL.md"
grep -q -- '--candidate-ids' "$SKILL/references/wechat-examples.md"
grep -q 'Never run a database client' "$SKILL/SKILL.md"
grep -q '查看我的健康概览' "$SKILL/references/wechat-examples.md"
grep -q 'visit-summary --department 耳鼻喉科 --json' "$SKILL/references/wechat-examples.md"

if [[ -d "$INSTALLED" ]]; then
  skills_list="$(hermes skills list)"
  grep -q 'personal-health-manager' <<<"$skills_list"
  echo "Installed Hermes Skill is discoverable: $INSTALLED"
else
  echo "Source Skill verified; install it to verify Hermes discovery."
fi
echo "Skill structure, health doctor, database, and CLI integration verified"
