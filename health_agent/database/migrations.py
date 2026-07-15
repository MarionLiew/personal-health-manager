from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, inspect, text

from health_agent.database.models import (
    Base,
    ClinicalOpinionCandidate,
    DoseScreenCandidate,
    FollowUpEvent,
    HealthTimelineEvent,
    HPVLesion,
    ImmuneContext,
    LesionImage,
    PathologyCandidate,
    PersonalCondition,
    RecordCandidate,
    ReminderDeliveryLog,
    RiskFactorProfile,
    ScarLesion,
    SymptomObservation,
    TreatmentEvent,
)
from health_agent.database.session import build_engine
from health_agent.errors import ConfirmationRequired

LATEST_SCHEMA_VERSION = 5
SCHEMA_VERSION = LATEST_SCHEMA_VERSION


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection], None]


def _migration_1(connection: Connection) -> None:
    future_tables = {
        RecordCandidate.__table__,
        Base.metadata.tables["symptom_episodes"],
        Base.metadata.tables["follow_up_plans"],
        Base.metadata.tables["appointments"],
        SymptomObservation.__table__,
        FollowUpEvent.__table__,
        ClinicalOpinionCandidate.__table__,
        PathologyCandidate.__table__,
        DoseScreenCandidate.__table__,
        ReminderDeliveryLog.__table__,
        PersonalCondition.__table__,
        ScarLesion.__table__,
        HPVLesion.__table__,
        TreatmentEvent.__table__,
        LesionImage.__table__,
        ImmuneContext.__table__,
        HealthTimelineEvent.__table__,
        RiskFactorProfile.__table__,
    }
    tables = [table for table in Base.metadata.sorted_tables if table not in future_tables]
    Base.metadata.create_all(connection, tables=tables)
    # These three entities existed in schema v1 as provenance-only records. Keep that
    # historical shape here so a database created from zero genuinely traverses v1 -> v3.
    for table in ("symptom_episodes", "follow_up_plans", "appointments"):
        connection.exec_driver_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id VARCHAR(36) PRIMARY KEY NOT NULL,
                patient_id VARCHAR(36) NOT NULL REFERENCES patients(id),
                source_type VARCHAR(32) NOT NULL,
                source_document_id VARCHAR(36) REFERENCES source_documents(id),
                occurred_at DATETIME,
                original_text TEXT,
                extraction_method VARCHAR(64) NOT NULL,
                extraction_version VARCHAR(32) NOT NULL,
                confidence FLOAT,
                verified BOOLEAN NOT NULL,
                verification_status VARCHAR(32) NOT NULL,
                created_by VARCHAR(64) NOT NULL,
                updated_by VARCHAR(64) NOT NULL,
                audit_id VARCHAR(36),
                details JSON NOT NULL,
                recorded_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_patient_id ON {table}(patient_id)"
        )
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_source_type ON {table}(source_type)"
        )
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_source_document_id "
            f"ON {table}(source_document_id)"
        )
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


def _add_columns(connection: Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migration_3(connection: Connection) -> None:
    for table in (
        SymptomObservation.__table__,
        FollowUpEvent.__table__,
        ClinicalOpinionCandidate.__table__,
        PathologyCandidate.__table__,
        DoseScreenCandidate.__table__,
        ReminderDeliveryLog.__table__,
    ):
        table.create(connection, checkfirst=True)
    _add_columns(
        connection,
        "symptom_episodes",
        {
            "symptom_name": "VARCHAR(255)",
            "normalized_symptom_name": "VARCHAR(255)",
            "anatomical_region": "VARCHAR(128)",
            "anatomical_side": "VARCHAR(32)",
            "started_at": "DATETIME",
            "ended_at": "DATETIME",
            "status": "VARCHAR(32)",
            "severity": "FLOAT",
            "severity_scale": "VARCHAR(32)",
            "frequency": "VARCHAR(128)",
            "duration_pattern": "VARCHAR(255)",
            "trigger": "TEXT",
            "relieving_factor": "TEXT",
            "aggravating_factor": "TEXT",
            "associated_symptoms": "JSON",
            "user_notes": "TEXT",
        },
    )
    _add_columns(
        connection,
        "follow_up_plans",
        {
            "title": "VARCHAR(255)",
            "category": "VARCHAR(64)",
            "related_record_type": "VARCHAR(64)",
            "related_record_id": "VARCHAR(36)",
            "reason": "TEXT",
            "recommended_by": "VARCHAR(255)",
            "recommendation_source_type": "VARCHAR(32)",
            "due_date": "DATETIME",
            "due_date_start": "DATETIME",
            "due_date_end": "DATETIME",
            "recurrence_rule": "VARCHAR(255)",
            "priority": "VARCHAR(32)",
            "status": "VARCHAR(32)",
            "department": "VARCHAR(128)",
            "requested_test": "VARCHAR(255)",
            "completion_record_id": "VARCHAR(36)",
            "postpone_reason": "TEXT",
            "notes": "TEXT",
        },
    )
    _add_columns(
        connection,
        "appointments",
        {
            "department": "VARCHAR(128)",
            "clinician_name": "VARCHAR(255)",
            "institution": "VARCHAR(255)",
            "scheduled_start": "DATETIME",
            "scheduled_end": "DATETIME",
            "purpose": "TEXT",
            "related_followup_ids": "JSON",
            "status": "VARCHAR(32)",
            "preparation_notes": "TEXT",
            "outcome_notes": "TEXT",
        },
    )


def _migration_4(connection: Connection) -> None:
    for table in (
        PersonalCondition.__table__,
        ScarLesion.__table__,
        HPVLesion.__table__,
        TreatmentEvent.__table__,
        LesionImage.__table__,
        ImmuneContext.__table__,
        HealthTimelineEvent.__table__,
        RiskFactorProfile.__table__,
    ):
        table.create(connection, checkfirst=True)


def _migration_5(connection: Connection) -> None:
    _add_columns(
        connection,
        "source_documents",
        {"institution": "VARCHAR(255)"},
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_source_documents_institution "
        "ON source_documents(institution)"
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial_schema", _migration_1),
    Migration(2, "record_candidates", _migration_2),
    Migration(3, "daily_medical_management", _migration_3),
    Migration(4, "personal_health_profile", _migration_4),
    Migration(5, "source_document_institution", _migration_5),
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
    with sqlite3.connect(destination) as verification:
        integrity = verification.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError("Pre-migration backup integrity verification failed")
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
