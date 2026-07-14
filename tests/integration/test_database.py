from __future__ import annotations

from sqlalchemy import inspect, select

from health_agent.database.migrations import SCHEMA_VERSION, current_version, migrate
from health_agent.database.models import AuditLog, Patient
from health_agent.database.repository import audit
from health_agent.database.session import build_engine, session_scope


def test_migration_is_idempotent_and_has_core_entities(isolated_env) -> None:
    engine = build_engine(isolated_env)
    assert migrate(engine) == SCHEMA_VERSION
    assert migrate(engine) == SCHEMA_VERSION
    tables = set(inspect(engine).get_table_names())
    assert {
        "patients",
        "source_documents",
        "import_sessions",
        "audit_logs",
        "laboratory_results",
        "lesions",
        "radiation_exposures",
        "radiation_acquisitions",
        "health_samples",
        "inflammation_evidence_assessments",
        "record_candidates",
    } <= tables
    assert current_version(engine) == SCHEMA_VERSION
    with session_scope(engine) as session:
        assert session.get(Patient, "local-primary") is not None


def test_audit_log_uses_hash_prefix_only(isolated_env) -> None:
    engine = build_engine(isolated_env)
    migrate(engine)
    with session_scope(engine) as session:
        entry = audit(
            session,
            "record.import",
            patient_id="local-primary",
            file_hash="a" * 64,
            metadata={"parser_version": "1"},
        )
        audit_id = entry.id
    with session_scope(engine) as session:
        saved = session.scalar(select(AuditLog).where(AuditLog.id == audit_id))
        assert saved is not None
        assert saved.file_hash_prefix == "a" * 12
