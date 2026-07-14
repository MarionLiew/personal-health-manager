from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer
from sqlalchemy import select

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.database.migrations import migrate
from health_agent.database.models import (
    ImagingReport,
    ImportSession,
    LaboratoryReport,
    LaboratoryResult,
    Lesion,
    LesionMeasurement,
    RadiationExposure,
    RecordCandidate,
    SourceDocument,
)
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.importers.report import preview_report
from health_agent.safety.privacy import require_allowed_import_path

app = typer.Typer(no_args_is_help=True)


@app.command("import")
def import_record(
    file: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Preview or confirm a general report import."""
    try:
        if dry_run == confirm:
            raise ValueError("Specify exactly one of --dry-run or --confirm")
        settings = load_settings()
        path = require_allowed_import_path(file, settings)
        if not path.is_file():
            raise ValueError("General report import requires a file")
        preview = preview_report(path, settings.max_import_bytes)
        data = {
            "sha256": preview.sha256,
            "filename": preview.filename,
            "mime_type": preview.mime_type,
            "size": preview.size,
            "parser": preview.parser,
            "candidates": preview.candidates,
            "text_preview": preview.text[:1000] if preview.text else None,
            "duplicate": False,
        }
        if dry_run:
            emit(
                "record.import.preview",
                data,
                json_output=json_output,
                uncertainties=list(preview.uncertainties),
                requires_confirmation=True,
            )
            return
        migrate()
        with session_scope() as session:
            existing = session.scalar(
                select(SourceDocument).where(SourceDocument.sha256 == preview.sha256)
            )
            if existing and not existing.revoked:
                existing_import = session.scalar(
                    select(ImportSession)
                    .where(ImportSession.source_document_id == existing.id)
                    .where(ImportSession.status != "undone")
                    .order_by(ImportSession.created_at.desc())
                )
                data.update(
                    {
                        "duplicate": True,
                        "source_document_id": existing.id,
                        "import_id": existing_import.id if existing_import else None,
                    }
                )
                emit("record.import", data, json_output=json_output)
                return
            originals = settings.data_root / "reports" / "originals"
            originals.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = originals / f"{preview.sha256}{path.suffix.lower()}"
            if not destination.exists():
                shutil.copy2(path, destination)
                destination.chmod(0o400)
            source = existing or SourceDocument(
                patient_id="local-primary",
                original_filename=preview.filename,
                local_path=str(destination),
                mime_type=preview.mime_type,
                file_size=preview.size,
                sha256=preview.sha256,
                human_confirmed=True,
                parser_name=preview.parser,
                parser_version="1",
            )
            source.revoked = False
            session.add(source)
            session.flush()
            import_session = ImportSession(
                patient_id="local-primary",
                source_sha256=preview.sha256,
                source_document_id=source.id,
                kind="general_report",
                status="confirmed",
                preview=data,
                confirmed_at=datetime.now(UTC),
            )
            session.add(import_session)
            session.flush()
            audit(
                session,
                "record.import",
                patient_id="local-primary",
                entity_type="SourceDocument",
                entity_id=source.id,
                file_hash=preview.sha256,
                metadata={"parser_version": "1", "import_id": import_session.id},
            )
            for candidate in preview.candidates.get("items", []):
                session.add(
                    RecordCandidate(
                        id=candidate["id"],
                        import_session_id=import_session.id,
                        patient_id="local-primary",
                        candidate_type=candidate["candidate_type"],
                        source_type="system_inference",
                        payload=candidate["payload"],
                        original_text=candidate["original_text"],
                        original_offset=candidate["original_offset"],
                        confidence=candidate["confidence"],
                    )
                )
            data.update(
                {
                    "source_document_id": source.id,
                    "import_id": import_session.id,
                    "candidate_count": len(preview.candidates.get("items", [])),
                }
            )
        emit("record.import", data, json_output=json_output)
    except Exception as exc:
        emit_error("record.import", exc)
        raise typer.Exit(1) from exc


@app.command("list")
def list_records(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        records = session.scalars(
            select(SourceDocument).where(SourceDocument.revoked.is_(False))
        ).all()
        data = {
            "records": [
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "sha256": item.sha256,
                    "imported_at": item.imported_at.isoformat(),
                }
                for item in records
            ]
        }
    emit("record.list", data, json_output=json_output)


@app.command("show")
def show_record(record_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        item = session.get(SourceDocument, record_id)
        if item is None:
            raise typer.BadParameter("Record not found")
        data = {
            "id": item.id,
            "filename": item.original_filename,
            "sha256": item.sha256,
            "mime_type": item.mime_type,
            "file_size": item.file_size,
            "revoked": item.revoked,
            "parser": item.parser_name,
        }
    emit("record.show", data, json_output=json_output)


@app.command("candidates")
def candidates_command(import_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        items = session.scalars(
            select(RecordCandidate)
            .where(RecordCandidate.import_session_id == import_id)
            .order_by(RecordCandidate.original_offset, RecordCandidate.id)
        ).all()
        data = {
            "import_id": import_id,
            "candidates": [
                {
                    "id": item.id,
                    "type": item.candidate_type,
                    "source_type": item.source_type,
                    "payload": item.payload,
                    "original_text": item.original_text,
                    "original_offset": item.original_offset,
                    "confidence": item.confidence,
                    "status": item.status,
                    "formal_record_id": item.formal_record_id,
                }
                for item in items
            ],
        }
    emit("record.candidates", data, json_output=json_output)


def _formalize_candidate(
    session,
    candidate: RecordCandidate,
    import_session: ImportSession,
    audit_id: str,
    lesion_id: str | None,
) -> tuple[str, str]:
    common = {
        "patient_id": candidate.patient_id,
        "source_type": "source_fact",
        "source_document_id": import_session.source_document_id,
        "occurred_at": (
            datetime.fromisoformat(candidate.payload["examination_date"])
            if candidate.payload.get("examination_date")
            else None
        ),
        "original_text": candidate.original_text,
        "extraction_method": "deterministic-parser+human-confirmation",
        "extraction_version": "2",
        "confidence": candidate.confidence,
        "verified": True,
        "verification_status": "human_confirmed",
        "audit_id": audit_id,
        "details": candidate.payload,
    }
    if candidate.candidate_type == "laboratory_result":
        report = session.scalar(
            select(LaboratoryReport).where(
                LaboratoryReport.source_document_id == import_session.source_document_id
            )
        )
        if report is None:
            report = LaboratoryReport(
                **{
                    **common,
                    "original_text": None,
                    "details": {"report_type": "laboratory", "import_id": import_session.id},
                }
            )
            session.add(report)
            session.flush()
        record = LaboratoryResult(**common)
        record.details = {**candidate.payload, "laboratory_report_id": report.id}
        session.add(record)
        session.flush()
        return "LaboratoryResult", record.id
    if candidate.candidate_type == "imaging_report":
        record = ImagingReport(**common)
        session.add(record)
        session.flush()
        return "ImagingReport", record.id
    if candidate.candidate_type == "lesion":
        lesion = session.get(Lesion, lesion_id) if lesion_id else None
        if lesion_id and lesion is None:
            raise ValueError("Requested lesion link does not exist")
        if lesion is not None:
            for key in ("laterality", "anatomical_location"):
                existing_value = lesion.details.get(key)
                candidate_value = candidate.payload.get(key)
                if existing_value and candidate_value and existing_value != candidate_value:
                    raise ValueError(
                        f"Candidate {key} does not match linked lesion; "
                        "explicit correction required"
                    )
        if lesion is None:
            lesion = Lesion(**common)
            lesion.details = {
                key: candidate.payload.get(key)
                for key in ("lesion_kind", "laterality", "anatomical_location")
            }
            session.add(lesion)
            session.flush()
        measurement = LesionMeasurement(**common)
        measurement.details = {**candidate.payload, "lesion_id": lesion.id}
        session.add(measurement)
        session.flush()
        return "LesionMeasurement", measurement.id
    raise ValueError(f"Unsupported candidate type: {candidate.candidate_type}")


@app.command("confirm-candidates")
def confirm_candidates(
    import_id: str,
    candidate_ids: str = typer.Option(..., "--candidate-ids"),
    lesion_id: str | None = typer.Option(None, "--lesion-id"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    migrate()
    requested = {value.strip() for value in candidate_ids.split(",") if value.strip()}
    with session_scope() as session:
        import_session = session.get(ImportSession, import_id)
        if import_session is None or import_session.status == "undone":
            raise typer.BadParameter("Active import not found")
        candidates = session.scalars(
            select(RecordCandidate)
            .where(RecordCandidate.import_session_id == import_id)
            .where(RecordCandidate.id.in_(requested))
        ).all()
        if {item.id for item in candidates} != requested:
            raise typer.BadParameter("One or more candidate IDs do not belong to this import")
        entry = audit(
            session,
            "record.confirm-candidates",
            patient_id=import_session.patient_id,
            entity_type="ImportSession",
            entity_id=import_id,
            metadata={"candidate_ids": sorted(requested)},
        )
        confirmed = []
        for candidate in candidates:
            if candidate.status == "confirmed":
                confirmed.append(candidate.formal_record_id)
                continue
            if candidate.status == "rejected":
                raise typer.BadParameter(f"Candidate was rejected: {candidate.id}")
            record_type, record_id = _formalize_candidate(
                session, candidate, import_session, entry.id, lesion_id
            )
            candidate.status = "confirmed"
            candidate.reviewed_at = datetime.now(UTC)
            candidate.formal_record_type = record_type
            candidate.formal_record_id = record_id
            confirmed.append(record_id)
        data = {
            "import_id": import_id,
            "confirmed_candidate_ids": sorted(requested),
            "formal_record_ids": confirmed,
        }
    emit("record.confirm-candidates", data, json_output=json_output)


@app.command("reject-candidates")
def reject_candidates(
    import_id: str,
    candidate_ids: str = typer.Option(..., "--candidate-ids"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    migrate()
    requested = {value.strip() for value in candidate_ids.split(",") if value.strip()}
    with session_scope() as session:
        candidates = session.scalars(
            select(RecordCandidate)
            .where(RecordCandidate.import_session_id == import_id)
            .where(RecordCandidate.id.in_(requested))
        ).all()
        if {item.id for item in candidates} != requested:
            raise typer.BadParameter("One or more candidate IDs do not belong to this import")
        for candidate in candidates:
            if candidate.status == "confirmed":
                raise typer.BadParameter(f"Candidate is already confirmed: {candidate.id}")
            candidate.status = "rejected"
            candidate.reviewed_at = datetime.now(UTC)
        audit(
            session,
            "record.reject-candidates",
            patient_id="local-primary",
            entity_type="ImportSession",
            entity_id=import_id,
            metadata={"candidate_ids": sorted(requested)},
        )
    emit(
        "record.reject-candidates",
        {"import_id": import_id, "rejected_candidate_ids": sorted(requested)},
        json_output=json_output,
    )


@app.command("undo-import")
def undo_import(
    import_id: str,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if dry_run == confirm:
        raise typer.BadParameter("Specify exactly one of --dry-run or --confirm")
    migrate()
    with session_scope() as session:
        item = session.get(ImportSession, import_id)
        if item is None:
            raise typer.BadParameter("Import not found")
        data = {"import_id": item.id, "current_status": item.status}
        if dry_run:
            emit(
                "record.undo-import.preview",
                data,
                json_output=json_output,
                requires_confirmation=True,
            )
            return
        if item.status != "undone":
            item.status = "undone"
            item.undone_at = datetime.now(UTC)
            source = session.get(SourceDocument, item.source_document_id)
            if source:
                source.revoked = True
            for model in (
                LaboratoryReport,
                LaboratoryResult,
                ImagingReport,
                Lesion,
                LesionMeasurement,
                RadiationExposure,
            ):
                formal_records = session.scalars(
                    select(model).where(model.source_document_id == item.source_document_id)
                ).all()
                for formal in formal_records:
                    formal.verified = False
                    formal.verification_status = "revoked_by_import_undo"
            candidates = session.scalars(
                select(RecordCandidate).where(RecordCandidate.import_session_id == item.id)
            ).all()
            for candidate in candidates:
                candidate.status = "revoked"
            audit(
                session,
                "record.undo-import",
                patient_id=item.patient_id,
                entity_type="ImportSession",
                entity_id=item.id,
                file_hash=item.source_sha256,
            )
        data["status"] = "undone"
    emit("record.undo-import", data, json_output=json_output)
