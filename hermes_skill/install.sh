#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$PROJECT_DIR/hermes_skill/personal-health-manager"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
TARGET_ROOT="$HERMES_ROOT/skills"
TARGET="$TARGET_ROOT/personal-health-manager"
BACKUP_ROOT="$HERMES_ROOT/backups/personal-health-manager-skills"
LEGACY_BACKUP_ROOT="$TARGET_ROOT/.personal-health-manager-backups"
UPDATE=false

if [[ "${1:-}" == "--update" ]]; then
  UPDATE=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--update]" >&2
  exit 2
fi

command -v hermes >/dev/null || { echo "Hermes CLI not found" >&2; exit 1; }
test -f "$SOURCE/SKILL.md" || { echo "Skill source missing" >&2; exit 1; }
test -x "$SOURCE/tools/health.sh" || { echo "health wrapper is missing or not executable" >&2; exit 1; }
hermes skills list >/dev/null
if [[ -d "$LEGACY_BACKUP_ROOT" ]]; then
  mkdir -p "$BACKUP_ROOT"
  LEGACY_TARGET="$BACKUP_ROOT/legacy-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$LEGACY_BACKUP_ROOT" "$LEGACY_TARGET"
  echo "Moved legacy in-scan backups to $LEGACY_TARGET"
fi
if [[ -e "$TARGET" ]]; then
  if diff -qr "$SOURCE" "$TARGET" >/dev/null; then
    echo "personal-health-manager is already current at $TARGET"
    exit 0
  fi
  if [[ "$UPDATE" != true ]]; then
    echo "Skill exists with different content: $TARGET" >&2
    echo "Re-run with --update to create a backup and replace it." >&2
    exit 2
  fi
  BACKUP="$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$BACKUP_ROOT"
  cp -R "$TARGET" "$BACKUP"
  rm -rf "$TARGET"
  echo "Backed up previous Skill to $BACKUP"
fi
mkdir -p "$TARGET_ROOT"
cp -R "$SOURCE" "$TARGET"
chmod 0755 "$TARGET/tools/health.sh"
echo "Installed personal-health-manager at $TARGET"
echo "Run: $PROJECT_DIR/hermes_skill/verify.sh"
