from __future__ import annotations

from sqlalchemy import Engine, select

from health_agent.database.models import Base, Patient, SchemaVersion
from health_agent.database.session import build_engine, session_scope

SCHEMA_VERSION = 1


def migrate(engine: Engine | None = None) -> int:
    target = engine or build_engine()
    # Migration 1 is the auditable baseline. Future versions must use additive, numbered functions.
    Base.metadata.create_all(target)
    with session_scope(target) as session:
        current = session.scalar(
            select(SchemaVersion.version).order_by(SchemaVersion.version.desc())
        )
        if current is None:
            session.add(SchemaVersion(version=SCHEMA_VERSION))
        elif current > SCHEMA_VERSION:
            raise RuntimeError(f"Database version {current} is newer than code {SCHEMA_VERSION}")
        patient = session.get(Patient, "local-primary")
        if patient is None:
            session.add(Patient(id="local-primary", local_label="Primary local patient"))
    return SCHEMA_VERSION


def current_version(engine: Engine | None = None) -> int | None:
    target = engine or build_engine()
    try:
        with session_scope(target) as session:
            return session.scalar(
                select(SchemaVersion.version).order_by(SchemaVersion.version.desc())
            )
    except Exception:
        return None
