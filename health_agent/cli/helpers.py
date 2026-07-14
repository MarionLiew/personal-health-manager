from __future__ import annotations

from datetime import UTC, datetime

from health_agent.errors import ValidationFailure


def parse_datetime(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=parsed.tzinfo or UTC)
    except ValueError as exc:
        raise ValidationFailure(f"Invalid ISO date/time for {field}") from exc


def require_gate(dry_run: bool, confirm: bool) -> None:
    if dry_run == confirm:
        raise ValidationFailure("Specify exactly one of --dry-run or --confirm")
