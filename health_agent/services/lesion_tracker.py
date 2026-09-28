from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.database.models import (
    AuditLog,
    Lesion,
    LesionMeasurement,
    LesionObservation,
    LesionSourceLink,
    SourceDocument,
)
from health_agent.database.repository import audit
from health_agent.errors import ValidationFailure

EVIDENCE = {"source_fact", "clinician_opinion", "user_report", "system_inference"}
STATUSES = {"confirmed", "user_confirmed", "probable", "unresolved", "rejected"}
TRACKING = {"active", "resolved", "uncertain", "archived"}


def require_lesion(session: Session, lesion_id: str) -> Lesion:
    lesion = session.get(Lesion, lesion_id)
    if lesion is None or not lesion.verified:
        raise ValidationFailure("Formal lesion not found")
    return lesion


def require_source(session: Session, source_id: str) -> SourceDocument:
    source = session.get(SourceDocument, source_id)
    if source is None or source.revoked:
        raise ValidationFailure("Source document not found or revoked")
    return source


def validate_evidence(evidence_type: str, status: str, scope: str = "individual") -> None:
    if evidence_type not in EVIDENCE or status not in STATUSES:
        raise ValidationFailure("Invalid evidence type or identity status")
    if scope not in {"individual", "bilateral_group"}:
        raise ValidationFailure("Invalid description scope")
    if scope == "bilateral_group" and status in {"confirmed", "user_confirmed"}:
        raise ValidationFailure("Bilateral group description cannot be confirmed for one lesion")
    if status == "user_confirmed" and evidence_type != "user_report":
        raise ValidationFailure("User-confirmed identity must retain user_report evidence type")
    if status == "confirmed" and evidence_type in {"user_report", "system_inference"}:
        raise ValidationFailure("Confirmed source identity requires report or clinician evidence")


def active_lesions(session: Session) -> list[Lesion]:
    lesions = session.scalars(select(Lesion).where(Lesion.verified.is_(True))).all()
    return [
        lesion
        for lesion in lesions
        if lesion.details.get("display_code")
        or (
            lesion.source_document_id
            and (source := session.get(SourceDocument, lesion.source_document_id)) is not None
            and not source.revoked
        )
    ]


def create_lesion(
    session: Session,
    *,
    display_code: str,
    name: str,
    laterality: str | None = None,
    body_region: str | None = None,
    anatomical_location: str | None = None,
    tracking_status: str = "active",
    notes: str | None = None,
) -> Lesion:
    if not display_code.strip() or not name.strip() or tracking_status not in TRACKING:
        raise ValidationFailure("Valid display code, name and tracking status required")
    if session.scalars(
        select(Lesion).where(Lesion.details["display_code"].as_string() == display_code)
    ).first():
        raise ValidationFailure("Display code already exists")
    entry = audit(session, "lesions.create", patient_id="local-primary", entity_type="Lesion")
    lesion = Lesion(
        patient_id="local-primary",
        source_type="user_report",
        verified=True,
        verification_status="user_confirmed",
        audit_id=entry.id,
        details={
            "display_code": display_code,
            "name": name,
            "laterality": laterality,
            "body_region": body_region,
            "anatomical_location": anatomical_location,
            "tracking_status": tracking_status,
            "notes": notes,
            "identity_basis": "user_report",
            "identity_confidence": None,
            "created_from": "manual",
        },
    )
    session.add(lesion)
    session.flush()
    entry.entity_id = lesion.id
    return lesion


def update_lesion(session: Session, lesion_id: str, **changes: Any) -> Lesion:
    lesion = require_lesion(session, lesion_id)
    if not changes or any(
        key
        not in {
            "name",
            "laterality",
            "body_region",
            "anatomical_location",
            "tracking_status",
            "notes",
        }
        for key in changes
    ):
        raise ValidationFailure("No valid mutable fields")
    if changes.get("tracking_status", "active") not in TRACKING:
        raise ValidationFailure("Invalid tracking status")
    previous = {key: lesion.details.get(key) for key in changes}
    audit(
        session,
        "lesions.update",
        patient_id=lesion.patient_id,
        entity_type="Lesion",
        entity_id=lesion.id,
        metadata={"previous": previous, "changes": changes},
    )
    lesion.details = {**lesion.details, **changes}
    return lesion


def link_source(
    session: Session,
    lesion_id: str,
    source_id: str,
    *,
    evidence_type: str,
    status: str,
    scope: str = "individual",
    original_text: str | None = None,
    import_id: str | None = None,
    report_record_id: str | None = None,
    page: int | None = None,
    original_offset: int | None = None,
    examination_date: datetime | None = None,
    examination_type: str | None = None,
) -> LesionSourceLink:
    lesion = require_lesion(session, lesion_id)
    source = require_source(session, source_id)
    validate_evidence(evidence_type, status, scope)
    if lesion.patient_id != source.patient_id:
        raise ValidationFailure("Source belongs to another patient")
    entry = audit(
        session,
        "lesions.link-source",
        patient_id=lesion.patient_id,
        entity_type="Lesion",
        entity_id=lesion.id,
        metadata={
            "source_document_id": source_id,
            "evidence_type": evidence_type,
            "status": status,
        },
    )
    link = LesionSourceLink(
        lesion_id=lesion_id,
        source_document_id=source_id,
        evidence_type=evidence_type,
        status=status,
        scope=scope,
        original_text=original_text,
        import_id=import_id,
        report_record_id=report_record_id,
        page=page,
        original_offset=original_offset,
        examination_date=examination_date,
        examination_type=examination_type,
    )
    session.add(link)
    session.flush()
    entry.metadata_json = {**entry.metadata_json, "link_id": link.id}
    return link


def unlink_source(session: Session, lesion_id: str, link_id: str) -> LesionSourceLink:
    lesion = require_lesion(session, lesion_id)
    link = session.get(LesionSourceLink, link_id)
    if link is None or link.lesion_id != lesion_id or link.unlinked_at is not None:
        raise ValidationFailure("Active source link not found")
    audit(
        session,
        "lesions.unlink",
        patient_id=lesion.patient_id,
        entity_type="Lesion",
        entity_id=lesion_id,
        metadata={"link_id": link_id, "previous_status": link.status},
    )
    from health_agent.database.models import now_utc

    link.unlinked_at = now_utc()
    return link


def add_measurement(
    session: Session,
    lesion_id: str,
    source_id: str,
    *,
    size: float,
    unit: str,
    original_text: str,
    laterality: str | None = None,
    evidence_type: str = "source_fact",
    status: str = "unresolved",
    scope: str = "individual",
    examination_date: datetime | None = None,
) -> LesionObservation:
    lesion = require_lesion(session, lesion_id)
    source = require_source(session, source_id)
    validate_evidence(evidence_type, status, scope)
    if scope != "individual" or (
        laterality and lesion.details.get("laterality") not in (None, laterality)
    ):
        raise ValidationFailure(
            "Measurement must refer to an individual lesion on the matching side"
        )
    if (
        lesion.patient_id != source.patient_id
        or size <= 0
        or not unit.strip()
        or not original_text.strip()
    ):
        raise ValidationFailure("Invalid measurement or source")
    entry = audit(
        session,
        "lesions.add-measurement",
        patient_id=lesion.patient_id,
        entity_type="Lesion",
        entity_id=lesion_id,
        metadata={"source_document_id": source_id},
    )
    observation = LesionObservation(
        lesion_id=lesion_id,
        source_document_id=source_id,
        size=size,
        unit=unit,
        original_text=original_text,
        laterality=laterality,
        evidence_type=evidence_type,
        status=status,
        examination_date=examination_date,
    )
    session.add(observation)
    session.flush()
    entry.metadata_json = {**entry.metadata_json, "measurement_id": observation.id}
    return observation


def formal_history(session: Session, lesion_id: str) -> dict[str, Any]:
    lesion = require_lesion(session, lesion_id)
    links = session.scalars(
        select(LesionSourceLink).where(LesionSourceLink.lesion_id == lesion_id)
    ).all()
    observations = session.scalars(
        select(LesionObservation).where(LesionObservation.lesion_id == lesion_id)
    ).all()
    events = session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "Lesion", AuditLog.entity_id == lesion_id)
        .order_by(AuditLog.occurred_at, AuditLog.id)
    ).all()

    def source_row(source_id: str) -> dict[str, Any]:
        source = session.get(SourceDocument, source_id)
        return {
            "source_document_id": source_id,
            "original_filename": source.original_filename if source else None,
            "local_path": source.local_path if source and not source.revoked else None,
            "institution": source.institution if source else None,
        }

    return {
        "id": lesion.id,
        **lesion.details,
        "source_type": lesion.source_type,
        "sources": [
            {
                "id": link.id,
                **source_row(link.source_document_id),
                "import_id": link.import_id,
                "report_record_id": link.report_record_id,
                "evidence_type": link.evidence_type,
                "status": link.status,
                "scope": link.scope,
                "original_text": link.original_text,
                "page": link.page,
                "original_offset": link.original_offset,
                "examination_date": link.examination_date.isoformat()
                if link.examination_date
                else None,
                "examination_type": link.examination_type,
            }
            for link in links
            if link.unlinked_at is None
        ],
        "measurements": [
            {
                "id": row.id,
                **source_row(row.source_document_id),
                "size": row.size,
                "unit": row.unit,
                "laterality": row.laterality,
                "original_text": row.original_text,
                "evidence_type": row.evidence_type,
                "status": row.status,
                "examination_date": row.examination_date.isoformat()
                if row.examination_date
                else None,
            }
            for row in observations
        ],
        "audit": [
            {
                "operation": item.operation,
                "metadata": item.metadata_json,
                "occurred_at": item.occurred_at.isoformat(),
            }
            for item in events
        ],
    }


def measurement_rows(session: Session, lesion_id: str) -> list[dict[str, Any]]:
    measurements = session.scalars(
        select(LesionMeasurement).where(LesionMeasurement.verified.is_(True))
    ).all()
    rows = []
    for measurement in measurements:
        if measurement.details.get("lesion_id") != lesion_id:
            continue
        source = session.get(SourceDocument, measurement.source_document_id)
        if source is None or source.revoked:
            continue
        rows.append(
            {
                "id": measurement.id,
                "date": measurement.occurred_at.date().isoformat()
                if measurement.occurred_at
                else None,
                "size": measurement.details.get("size"),
                "unit": measurement.details.get("unit"),
                "modality": measurement.details.get("modality"),
                "laterality": measurement.details.get("laterality"),
                "anatomical_location": measurement.details.get("anatomical_location"),
                "original_text": measurement.original_text,
                "source_document_id": measurement.source_document_id,
                "follow_up_advice": measurement.details.get("follow_up_advice"),
            }
        )
    return sorted(rows, key=lambda row: (row["date"] or "", row["id"]))


def comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"comparable": False, "reason": "No confirmed measurements"}
    first, latest = rows[0], rows[-1]
    comparable = all(
        first.get(key) == latest.get(key)
        for key in ("unit", "modality", "laterality", "anatomical_location")
    )
    delta = None
    possible_error = True
    if comparable and first.get("size") is not None and latest.get("size") is not None:
        delta = float(latest["size"]) - float(first["size"])
        possible_error = abs(delta) <= max(
            1.0 if first["unit"] == "mm" else 0.1, float(first["size"]) * 0.1
        )
    return {
        "first": first,
        "latest": latest,
        "measurements": rows,
        "comparable": comparable,
        "size_change": delta,
        "measurement_error_possible": possible_error,
        "uncertainty": (
            "Small differences may reflect technique, slice selection, reader, or "
            "measurement error."
        ),
    }
