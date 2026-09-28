"""Local clinical exports: explicit evidence provenance, never inferred equivalence."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.database.models import (
    Lesion,
    LesionMeasurement,
    LesionObservation,
    SourceDocument,
)
from health_agent.errors import ValidationFailure

VERSION = "2"
_PRIVATE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|\d{17}[\dXx])(?!\d)")


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _PRIVATE.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {
            key: _redact(item)
            for key, item in value.items()
            if key not in {"phone", "phone_number", "identity_number", "id_number"}
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _source(session: Session, source_id: str | None) -> SourceDocument | None:
    source = session.get(SourceDocument, source_id) if source_id else None
    return source if source is not None and not source.revoked else None


def _archive_name(source: SourceDocument) -> str:
    # Never trust a user-supplied original filename or local path as a ZIP member.
    suffix = (
        ".pdf"
        if source.mime_type == "application/pdf"
        or source.original_filename.lower().endswith(".pdf")
        else ".bin"
    )
    return f"originals/{source.id}{suffix}"


def _source_entry(source: SourceDocument) -> dict[str, Any]:
    return {
        "source_document_id": source.id,
        "institution": _redact(source.institution),
        "sha256": source.sha256,
        "source_file": _archive_name(source),
        "original_filename": _redact(Path(source.original_filename).name),
    }


def build_lesion_bundle(
    session: Session, lesion_id: str, *, include_unconfirmed: bool = False
) -> dict[str, Any]:
    lesion = session.get(Lesion, lesion_id)
    if lesion is None or not lesion.verified:
        raise ValidationFailure("Lesion not found")
    source = _source(session, lesion.source_document_id)
    if lesion.source_document_id and source is None:
        raise ValidationFailure("Lesion source is unavailable or revoked")
    details = lesion.details or {}
    sources = {source.id: source} if source else {}
    measurements = []
    chain = []
    seen_keys = set()
    for measurement in session.scalars(
        select(LesionMeasurement).where(LesionMeasurement.patient_id == lesion.patient_id)
    ).all():
        data = measurement.details or {}
        if data.get("lesion_id") != lesion_id or not measurement.verified:
            continue
        status = data.get("identity_status", "confirmed")
        if status in {"rejected", "unresolved", "probable"} and not include_unconfirmed:
            continue
        evidence_source = _source(session, measurement.source_document_id)
        if evidence_source is None:
            continue
        sources[evidence_source.id] = evidence_source
        record = {
            "id": measurement.id,
            "date": measurement.occurred_at.date().isoformat() if measurement.occurred_at else None,
            "size": data.get("size"),
            "unit": data.get("unit"),
            "source_document_id": evidence_source.id,
            "identity_status": status,
        }
        measurements.append(record)
        chain.append(
            {
                "lesion_id": lesion_id,
                "examination_id": data.get("examination_id"),
                "report_record_id": data.get("report_record_id", measurement.id),
                "import_id": data.get("import_id"),
                "source_document_id": evidence_source.id,
                "source_file": _archive_name(evidence_source),
                "date": record["date"],
                "institution": _redact(evidence_source.institution),
                "examination_type": data.get("modality"),
                "page": data.get("page"),
                "original_offset": data.get("original_offset"),
                "original_quote": _redact(measurement.original_text),
                "source_type": data.get("source_type", "source_fact"),
                "identity_status": status,
            }
        )

    for observation in session.scalars(
        select(LesionObservation).where(LesionObservation.lesion_id == lesion_id)
    ).all():
        evidence_source = _source(session, observation.source_document_id)
        if evidence_source is None:
            continue
        if observation.status in {"rejected", "unresolved", "probable"} and not include_unconfirmed:
            continue
        sources[evidence_source.id] = evidence_source
        date = (
            observation.examination_date.date().isoformat()
            if observation.examination_date
            else None
        )
        key = (lesion_id, date, float(observation.size), observation.source_document_id)
        evidence_entry = {
            "lesion_id": lesion_id,
            "examination_id": None,
            "report_record_id": observation.id,
            "import_id": None,
            "source_document_id": evidence_source.id,
            "source_file": _archive_name(evidence_source),
            "date": date,
            "institution": _redact(evidence_source.institution),
            "examination_type": None,
            "page": None,
            "original_offset": None,
            "original_quote": _redact(observation.original_text),
            "source_type": observation.evidence_type,
            "identity_status": observation.status,
        }
        if key in seen_keys:
            continue
        seen_keys.add(key)
        chain.append(evidence_entry)
        measurements.append(
            {
                "id": observation.id,
                "date": date,
                "size": observation.size,
                "unit": observation.unit,
                "source_document_id": observation.source_document_id,
                "identity_status": observation.status,
            }
        )
    measurements.sort(key=lambda item: (item["date"] or "", item["id"]))
    chain.sort(key=lambda item: (item["date"] or "", item["report_record_id"]))
    return {
        "format_version": VERSION,
        "lesion": {
            "id": lesion.id,
            "date": lesion.occurred_at.date().isoformat() if lesion.occurred_at else None,
            "details": _redact(details),
            "source_document_id": lesion.source_document_id,
        },
        "original_quotes": (
            [
                {
                    "text": _redact(lesion.original_text),
                    "source_document_id": source.id,
                    "source_type": "source_fact",
                }
            ]
            if source and lesion.original_text
            else []
        ),
        "system_summary": _redact(details.get("summary")),
        "measurements": measurements,
        "evidence_chain": chain,
        "source_index": [
            _source_entry(item) for item in sorted(sources.values(), key=lambda item: item.id)
        ],
    }


def build_visit_bundle(
    session: Session, department: str, purpose: str, *, include_unconfirmed: bool = False
) -> dict[str, Any]:
    if not department.strip() or not purpose.strip():
        raise ValidationFailure("Department and purpose are required")
    lesions = [
        build_lesion_bundle(session, lesion.id, include_unconfirmed=include_unconfirmed)
        for lesion in session.scalars(select(Lesion).where(Lesion.verified.is_(True))).all()
        if (lesion.details or {}).get("department", "").casefold() == department.casefold()
    ]
    sources = {
        entry["source_document_id"]: entry for lesion in lesions for entry in lesion["source_index"]
    }
    return {
        "format_version": VERSION,
        "department": department,
        "purpose": purpose,
        "lesions": lesions,
        "source_index": list(sources.values()),
        "unresolved_questions": [
            f"Confirm identity of observation {entry['report_record_id']}"
            for lesion in lesions
            for entry in lesion["evidence_chain"]
            if entry["identity_status"] in {"probable", "unresolved"}
        ],
    }


def build_case_bundle(session: Session, *, include_unconfirmed: bool = False) -> dict[str, Any]:
    lesions = [
        build_lesion_bundle(session, lesion.id, include_unconfirmed=include_unconfirmed)
        for lesion in session.scalars(select(Lesion).where(Lesion.verified.is_(True))).all()
    ]
    sources = {
        entry["source_document_id"]: entry for lesion in lesions for entry in lesion["source_index"]
    }
    for source in session.scalars(
        select(SourceDocument).where(SourceDocument.revoked.is_(False))
    ).all():
        sources[source.id] = _source_entry(source)
    return {
        "format_version": VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "full_case",
        "lesions": lesions,
        "source_index": sorted(sources.values(), key=lambda item: item["source_document_id"]),
    }


def write_case_zip(
    session: Session, destination: Path, *, include_unconfirmed: bool = False
) -> dict[str, Any]:
    manifest = build_case_bundle(session, include_unconfirmed=include_unconfirmed)
    originals = []
    for entry in manifest["source_index"]:
        source = session.get(SourceDocument, entry["source_document_id"])
        assert source is not None
        path = Path(source.local_path)
        if not path.is_file() or path.is_symlink():
            raise ValidationFailure(f"Original source unavailable: {source.id}")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source.sha256:
            raise ValueError(f"Original checksum mismatch: {source.id}")
        originals.append((entry["source_file"], payload))
    if destination.exists():
        raise ValidationFailure("Export destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with destination.open("xb") as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for name, payload in originals:
                archive.writestr(name, payload)
    destination.chmod(0o600)
    return manifest
