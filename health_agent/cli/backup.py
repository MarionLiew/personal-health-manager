from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.services.backup import (
    configured_key,
    create_backup,
    read_backup,
    restore_to_new_file,
)

app = typer.Typer(no_args_is_help=True)


@app.command("create")
def create_command(json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        settings = load_settings()
        path = create_backup(
            settings.database_path, settings.data_root / "backups", configured_key()
        )
        emit(
            "backup.create",
            {"path": str(path), "encrypted": path.suffix == ".enc"},
            json_output=json_output,
            warnings=[]
            if path.suffix == ".enc"
            else ["Backup is integrity-checked but not encrypted."],
        )
    except Exception as exc:
        emit_error("backup.create", exc)
        raise typer.Exit(1) from exc


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    root = load_settings().data_root / "backups"
    backups = sorted(str(item) for item in root.glob("*.phab*")) if root.exists() else []
    emit("backup.list", {"backups": backups}, json_output=json_output)


@app.command("verify")
def verify_command(file: Path, json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        manifest, _ = read_backup(file.resolve(strict=True), configured_key())
        emit("backup.verify", {"valid": True, "manifest": manifest}, json_output=json_output)
    except Exception as exc:
        emit_error("backup.verify", exc)
        raise typer.Exit(1) from exc


@app.command("restore")
def restore_command(
    file: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    try:
        if dry_run == confirm:
            raise ValueError("Specify exactly one of --dry-run or --confirm")
        manifest, _ = read_backup(file.resolve(strict=True), configured_key())
        if dry_run:
            emit(
                "backup.restore.preview",
                {"valid": True, "manifest": manifest, "overwrites_current": False},
                json_output=json_output,
                requires_confirmation=True,
            )
            return
        settings = load_settings()
        destination = settings.database_path.with_name(
            f"health.restored-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
        )
        restore_to_new_file(file, destination, configured_key())
        emit(
            "backup.restore",
            {"restored_path": str(destination), "current_database_unchanged": True},
            json_output=json_output,
        )
    except Exception as exc:
        emit_error("backup.restore", exc)
        raise typer.Exit(1) from exc
