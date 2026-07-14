from __future__ import annotations

from datetime import UTC, datetime

import typer

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.database.migrations import (
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
    current_version,
    pending_migrations,
    upgrade,
    verify_database,
)
from health_agent.database.session import build_engine

app = typer.Typer(no_args_is_help=True)


@app.command("version")
def version_command(json_output: bool = typer.Option(False, "--json")) -> None:
    emit(
        "db.version",
        {"current": current_version(), "latest": LATEST_SCHEMA_VERSION},
        json_output=json_output,
    )


@app.command("migrations")
def migrations_command(json_output: bool = typer.Option(False, "--json")) -> None:
    current = current_version()
    emit(
        "db.migrations",
        {
            "current": current,
            "migrations": [
                {
                    "version": item.version,
                    "name": item.name,
                    "status": "applied" if item.version <= current else "pending",
                }
                for item in MIGRATIONS
            ],
        },
        json_output=json_output,
    )


@app.command("upgrade")
def upgrade_command(
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    try:
        if dry_run == confirm:
            raise ValueError("Specify exactly one of --dry-run or --confirm")
        engine = build_engine()
        pending = pending_migrations(engine)
        data = {
            "current": current_version(engine),
            "target": LATEST_SCHEMA_VERSION,
            "pending": [{"version": item.version, "name": item.name} for item in pending],
        }
        if dry_run:
            emit(
                "db.upgrade.preview",
                data,
                json_output=json_output,
                requires_confirmation=bool(pending),
            )
            return
        backup_path = None
        if data["current"] and pending:
            settings = load_settings()
            backup_path = (
                settings.data_root
                / "backups"
                / (
                    f"pre-migration-v{data['current']}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
                )
            )
        applied = upgrade(engine, backup_path=backup_path)
        data.update(
            {
                "applied": applied,
                "current": current_version(engine),
                "backup_path": str(backup_path) if backup_path else None,
            }
        )
        emit("db.upgrade", data, json_output=json_output)
    except Exception as exc:
        emit_error("db.upgrade", exc)
        raise typer.Exit(1) from exc


@app.command("verify")
def verify_command(json_output: bool = typer.Option(False, "--json")) -> None:
    result = verify_database()
    emit("db.verify", result, json_output=json_output)
    if not result["valid"]:
        raise typer.Exit(1)
