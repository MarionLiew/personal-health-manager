from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from health_agent.database.models import AuditLog


def audit(
    session: Session,
    operation: str,
    *,
    patient_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    file_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        operation=operation,
        patient_id=patient_id,
        entity_type=entity_type,
        entity_id=entity_id,
        file_hash_prefix=file_hash[:12] if file_hash else None,
        metadata_json=metadata or {},
    )
    session.add(entry)
    session.flush()
    return entry
