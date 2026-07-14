from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, inspect, text

from health_agent.database.models import Base, RecordCandidate
from health_agent.database.session import build_engine
from health_agent.errors import ConfirmationRequired

LATEST_SCHEMA_VERSION = 2
SCHEMA_VERSION = LATEST_SCHEMA_VERSION


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection], None]


def _migration_1(connection: Connection) -> None:
    tables = [
        table for table in Base.metadata.sorted_tables if table is not RecordCandidate.__table__
    ]
    Base.metadata.create_all(connection, tables=tables)
    patient = connection.execute(text("SELECT 1 FROM patients WHERE id = 'local-primary'")).scalar()
    if not patient:
        connection.execute(
            text(
                "INSERT INTO patients(id, local_label, created_at, recorded_at, updated_at) "
                "VALUES ('local-primary', 'Primary local patient', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )


def _migration_2(connection: Connection) -> None:
    RecordCandidate.__table__.create(connection, checkfirst=True)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial_schema", _migration_1),
    Migration(2, "record_candidates", _migration_2),
)


def current_version(engine: Engine | None = None) -> int:
    target = engine or build_engine()
    database = Path(target.url.database or "")
    if not database.exists():
        return 0
    if "schema_version" not in inspect(target).get_table_names():
        return 0
    with target.connect() as connection:
        return int(
            connection.execute(
                text("SELECT COALESCE(MAX(version), 0) FROM schema_version")
            ).scalar()
            or 0
        )


def pending_migrations(
    engine: Engine | None = None, migrations: Sequence[Migration] = MIGRATIONS
) -> list[Migration]:
    version = current_version(engine)
    return [migration for migration in migrations if migration.version > version]


def _sqlite_backup(database: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(database) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    destination.chmod(0o600)
    return destination


def upgrade(
    engine: Engine | None = None,
    *,
    migrations: Sequence[Migration] = MIGRATIONS,
    backup_path: Path | None = None,
) -> list[int]:
    target = engine or build_engine()
    current = current_version(target)
    pending = [migration for migration in migrations if migration.version > current]
    if current and pending and backup_path is None:
        raise ConfirmationRequired(
            "A backup path is required before upgrading an existing database"
        )
    if backup_path is not None:
        database = Path(target.url.database or "")
        if database.exists():
            _sqlite_backup(database, backup_path)
    applied: list[int] = []
    for migration in pending:
        try:
            with target.begin() as connection:
                migration.apply(connection)
                connection.execute(
                    text(
                        "INSERT INTO schema_version(version, applied_at) "
                        "VALUES (:version, CURRENT_TIMESTAMP)"
                    ),
                    {"version": migration.version},
                )
                connection.execute(
                    text(
                        "INSERT INTO audit_logs(id, operation, actor, status, metadata_json, "
                        "occurred_at) VALUES (lower(hex(randomblob(16))), 'db.migrate', "
                        "'health-cli', 'success', :metadata, CURRENT_TIMESTAMP)"
                    ),
                    {"metadata": f'{{"version":{migration.version},"name":"{migration.name}"}}'},
                )
            applied.append(migration.version)
        except Exception:
            # SQLite DDL support varies; restore is deterministic if a migration changes schema.
            if backup_path and backup_path.exists():
                database = Path(target.url.database or "")
                target.dispose()
                Path(f"{database}-wal").unlink(missing_ok=True)
                Path(f"{database}-shm").unlink(missing_ok=True)
                database.unlink(missing_ok=True)
                database.write_bytes(backup_path.read_bytes())
            raise
    return applied


def migrate(engine: Engine | None = None) -> int:
    """Initialize a new database; existing upgrades require `health db upgrade --confirm`."""
    target = engine or build_engine()
    version = current_version(target)
    if version == 0:
        upgrade(target)
    elif version < LATEST_SCHEMA_VERSION:
        raise ConfirmationRequired("Database upgrade requires health db upgrade --confirm")
    elif version > LATEST_SCHEMA_VERSION:
        raise RuntimeError(f"Database version {version} is newer than code {LATEST_SCHEMA_VERSION}")
    return current_version(target)


def verify_database(engine: Engine | None = None) -> dict[str, object]:
    target = engine or build_engine()
    database = Path(target.url.database or "")
    with sqlite3.connect(database) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    tables = set(inspect(target).get_table_names())
    required = {table.name for table in Base.metadata.sorted_tables}
    return {
        "valid": integrity == "ok" and not foreign_keys and required <= tables,
        "integrity": integrity,
        "foreign_key_errors": len(foreign_keys),
        "missing_tables": sorted(required - tables),
        "version": current_version(target),
        "expected_version": LATEST_SCHEMA_VERSION,
    }
