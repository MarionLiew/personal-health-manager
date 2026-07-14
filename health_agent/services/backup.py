from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from health_agent.database.migrations import SCHEMA_VERSION
from health_agent.errors import ValidationFailure


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_database(database: Path) -> bytes:
    buffer_path = database.with_suffix(".backup-tmp")
    try:
        with sqlite3.connect(database) as source, sqlite3.connect(buffer_path) as target:
            source.backup(target)
        return buffer_path.read_bytes()
    finally:
        buffer_path.unlink(missing_ok=True)


def create_backup(database: Path, output_dir: Path, key: str | None = None) -> Path:
    if not database.exists():
        raise ValidationFailure("Database does not exist; run health init first")
    data = snapshot_database(database)
    manifest = {
        "format": 1,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "database_sha256": sha256_bytes(data),
    }
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        archive.writestr("health.sqlite3", data)
    payload = archive_buffer.getvalue()
    encrypted = bool(key)
    if key:
        payload = Fernet(key.encode()).encrypt(payload)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    suffix = ".phab.enc" if encrypted else ".phab"
    path = output_dir / f"health-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}{suffix}"
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def read_backup(path: Path, key: str | None = None) -> tuple[dict[str, object], bytes]:
    payload = path.read_bytes()
    if path.suffix == ".enc":
        if not key:
            raise ValidationFailure("Encrypted backup requires HEALTH_AGENT_BACKUP_KEY")
        try:
            payload = Fernet(key.encode()).decrypt(payload)
        except (InvalidToken, ValueError) as exc:
            raise ValidationFailure("Backup key or encrypted data is invalid") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if set(archive.namelist()) != {"manifest.json", "health.sqlite3"}:
                raise ValidationFailure("Unexpected backup contents")
            manifest = json.loads(archive.read("manifest.json"))
            database = archive.read("health.sqlite3")
    except (zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ValidationFailure("Invalid backup archive") from exc
    if sha256_bytes(database) != manifest.get("database_sha256"):
        raise ValidationFailure("Backup integrity check failed")
    if int(manifest.get("schema_version", -1)) > SCHEMA_VERSION:
        raise ValidationFailure("Backup schema is newer than installed code")
    return manifest, database


def restore_to_new_file(path: Path, destination: Path, key: str | None = None) -> Path:
    _, database = read_backup(path, key)
    if destination.exists():
        raise ValidationFailure("Restore destination already exists; refusing to overwrite")
    destination.write_bytes(database)
    destination.chmod(0o600)
    with sqlite3.connect(destination) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            destination.unlink(missing_ok=True)
            raise ValidationFailure("Restored SQLite integrity check failed")
    return destination


def configured_key() -> str | None:
    return os.getenv("HEALTH_AGENT_BACKUP_KEY") or None
