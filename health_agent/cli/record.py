from __future__ import annotations

import calendar
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer
from sqlalchemy import select

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.database.migrations import migrate
from health_agent.database.models import (
    ClinicalOpinionCandidate,
    Diagnosis,
    FollowUpPlan,
    ImagingReport,
    ImportSession,
    LaboratoryReport,
    LaboratoryResult,
    Lesion,
    LesionMeasurement,
    PathologyCandidate,
    Procedure,
    RadiationExposure,
    RecordCandidate,
    SourceDocument,
)
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure
from health_agent.importers.report import preview_report
from health_agent.safety.privacy import require_allowed_import_path

app = typer.Typer(no_args_is_help=True)

PARSER_VERSION = "8"


def _add_candidate(
    session,
    import_session: ImportSession,
    candidate: dict,
) -> RecordCandidate:
    record_candidate = RecordCandidate(
        id=candidate["id"],
        import_session_id=import_session.id,
        patient_id=import_session.patient_id,
        candidate_type=candidate["candidate_type"],
        source_type="system_inference",
        payload=candidate["payload"],
        original_text=candidate["original_text"],
        original_offset=candidate["original_offset"],
        confidence=candidate["confidence"],
    )
    session.add(record_candidate)
    specialized = {
        "clinical_opinion": ClinicalOpinionCandidate,
        "pathology": PathologyCandidate,
    }.get(candidate["candidate_type"])
    if specialized:
        session.add(
            specialized(
                id=candidate["id"],
                import_session_id=import_session.id,
                patient_id=import_session.patient_id,
                payload=candidate["payload"],
                original_text=candidate["original_text"],
                confidence=candidate["confidence"],
            )
        )
    return record_candidate


@app.command("import")
def import_record(
    file: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    ocr: bool = typer.Option(False, "--ocr", help="Use local OCR for a scanned PDF."),
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
        preview = preview_report(path, settings.max_import_bytes, allow_ocr=ocr)
        data = {
            "sha256": preview.sha256,
            "filename": preview.filename,
            "mime_type": preview.mime_type,
            "size": preview.size,
            "parser": preview.parser,
            "candidates": preview.candidates,
            "text_preview": preview.text[:1000] if preview.text else None,
            "duplicate": False,
            "ocr_requested": ocr,
        }
        if dry_run:
            if settings.database_path.exists():
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
                parser_version=PARSER_VERSION,
                institution=preview.candidates.get("institution"),
                institution_verified=False,
                institution_source_type=(
                    "system_inference" if preview.candidates.get("institution") else None
                ),
            )
            source.revoked = False
            if not source.institution_verified:
                source.institution = preview.candidates.get("institution")
                source.institution_source_type = (
                    "system_inference" if source.institution else None
                )
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
                metadata={"parser_version": PARSER_VERSION, "import_id": import_session.id},
            )
            for candidate in preview.candidates.get("items", []):
                _add_candidate(session, import_session, candidate)
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
def list_records(
    institution: str | None = typer.Option(None, "--institution"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    migrate()
    with session_scope() as session:
        statement = select(SourceDocument).where(SourceDocument.revoked.is_(False))
        if institution:
            statement = statement.where(SourceDocument.institution == institution)
        records = session.scalars(statement).all()
        data = {
            "records": [
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "sha256": item.sha256,
                    "imported_at": item.imported_at.isoformat(),
                    "institution": item.institution,
                    "institution_verified": item.institution_verified,
                    "institution_source_type": item.institution_source_type,
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
            "institution": item.institution,
            "institution_verified": item.institution_verified,
            "institution_source_type": item.institution_source_type,
        }
    emit("record.show", data, json_output=json_output)


@app.command("institution-set")
def set_institution(
    record_id: str,
    institution: str = typer.Option(..., "--institution"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Independently confirm a source document's institution without changing medical facts."""
    if dry_run == confirm:
        raise ValidationFailure("Specify exactly one of --dry-run or --confirm")
    normalized = " ".join(institution.split())
    if not normalized or len(normalized) > 255:
        raise ValidationFailure("Institution must contain 1 to 255 characters")
    if not re.search(r"(?:医院|医学中心|检验所|门诊部|诊所)$", normalized):
        raise ValidationFailure("Institution must be a complete medical organization name")
    migrate()
    with session_scope() as session:
        source = session.get(SourceDocument, record_id)
        if source is None or source.revoked:
            raise ValidationFailure("Active source document not found")
        changed = not (
            source.institution == normalized
            and source.institution_verified
            and source.institution_source_type == "source_fact"
        )
        data = {
            "source_document_id": source.id,
            "current_institution": source.institution,
            "proposed_institution": normalized,
            "current_verified": source.institution_verified,
            "source_type": "source_fact",
            "verification_status": "human_confirmed",
            "will_change_candidates": False,
            "will_change_formal_medical_records": False,
            "changed": changed,
        }
        if dry_run:
            emit(
                "record.institution-set.preview",
                data,
                json_output=json_output,
                requires_confirmation=True,
            )
            return
        if changed:
            source.institution = normalized
            source.institution_verified = True
            source.institution_source_type = "source_fact"
            source.institution_updated_at = datetime.now(UTC)
            entry = audit(
                session,
                "record.institution-set",
                patient_id=source.patient_id,
                entity_type="SourceDocument",
                entity_id=source.id,
                file_hash=source.sha256,
                metadata={"verified": True},
            )
            data["audit_id"] = entry.id
        data["institution"] = source.institution
    emit("record.institution-set", data, json_output=json_output)


def _specialized_candidate_model(candidate_type: str):
    return {
        "clinical_opinion": ClinicalOpinionCandidate,
        "pathology": PathologyCandidate,
    }.get(candidate_type)


@app.command("reparse")
def reparse_record(
    record_id: str,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    ocr: bool = typer.Option(False, "--ocr", help="Use local OCR for a scanned PDF."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Re-run the current parser for a saved source without confirming medical facts."""
    try:
        if dry_run == confirm:
            raise ValueError("Specify exactly one of --dry-run or --confirm")
        settings = load_settings()
        migrate()
        with session_scope() as session:
            source = session.get(SourceDocument, record_id)
            if source is None or source.revoked:
                raise ValueError("Active source document not found")
            source_path = Path(source.local_path).resolve(strict=True)
            if not source_path.is_relative_to(settings.data_root.resolve()):
                raise ValueError("Saved source path is outside the managed data root")
            preview = preview_report(source_path, settings.max_import_bytes, allow_ocr=ocr)
            if preview.sha256 != source.sha256:
                raise ValueError("Saved source integrity check failed")
            import_session = session.scalar(
                select(ImportSession)
                .where(ImportSession.source_document_id == source.id)
                .where(ImportSession.status != "undone")
                .order_by(ImportSession.created_at.desc())
            )
            if import_session is None:
                raise ValueError("Active import session not found")
            existing = session.scalars(
                select(RecordCandidate).where(
                    RecordCandidate.import_session_id == import_session.id
                )
            ).all()
            parsed_institution = preview.candidates.get("institution")
            effective_institution = (
                source.institution if source.institution_verified else parsed_institution
            )
            items = preview.candidates.get("items", [])
            for item in items:
                item["payload"]["institution"] = effective_institution
            new_ids = {item["id"] for item in items}
            pending_to_supersede = sorted(
                item.id for item in existing if item.status == "pending" and item.id not in new_ids
            )
            protected = sorted(
                item.id for item in existing if item.status in {"confirmed", "rejected"}
            )
            data = {
                "source_document_id": source.id,
                "import_id": import_session.id,
                "parser": preview.parser,
                "parser_version": PARSER_VERSION,
                "report_type": preview.candidates.get("report_type"),
                "classification_confidence": preview.candidates.get(
                    "classification_confidence"
                ),
                "dates": preview.candidates.get("dates", {}),
                "parsed_institution": parsed_institution,
                "institution": effective_institution,
                "institution_verified": source.institution_verified,
                "candidates": items,
                "pending_candidate_ids_to_supersede": pending_to_supersede,
                "protected_candidate_ids": protected,
                "ocr_requested": ocr,
            }
            if dry_run:
                emit(
                    "record.reparse.preview",
                    data,
                    json_output=json_output,
                    uncertainties=list(preview.uncertainties),
                    requires_confirmation=True,
                )
                return

            existing_by_id = {item.id: item for item in existing}
            added: list[str] = []
            retained: list[str] = []
            revived: list[str] = []
            for candidate_data in items:
                candidate = existing_by_id.get(candidate_data["id"])
                if candidate is None:
                    _add_candidate(session, import_session, candidate_data)
                    added.append(candidate_data["id"])
                    continue
                if candidate.status == "superseded":
                    candidate.status = "pending"
                    candidate.reviewed_at = None
                    specialized_model = _specialized_candidate_model(candidate.candidate_type)
                    if specialized_model and (
                        specialized := session.get(specialized_model, candidate.id)
                    ):
                        specialized.status = "pending"
                        specialized.reviewed_at = None
                    revived.append(candidate.id)
                else:
                    retained.append(candidate.id)
                if candidate.status == "pending":
                    candidate.payload = candidate_data["payload"]
                    candidate.original_text = candidate_data["original_text"]
                    candidate.original_offset = candidate_data["original_offset"]
                    candidate.confidence = candidate_data["confidence"]

            for candidate in existing:
                if candidate.id not in pending_to_supersede:
                    continue
                candidate.status = "superseded"
                candidate.reviewed_at = datetime.now(UTC)
                specialized_model = _specialized_candidate_model(candidate.candidate_type)
                if specialized_model and (
                    specialized := session.get(specialized_model, candidate.id)
                ):
                    specialized.status = "superseded"
                    specialized.reviewed_at = datetime.now(UTC)

            source.parser_name = preview.parser
            source.parser_version = PARSER_VERSION
            if not source.institution_verified:
                source.institution = parsed_institution
                source.institution_source_type = (
                    "system_inference" if parsed_institution else None
                )
            import_session.preview = {
                "sha256": preview.sha256,
                "filename": source.original_filename,
                "mime_type": preview.mime_type,
                "size": preview.size,
                "parser": preview.parser,
                "candidates": preview.candidates,
                "reparsed_at": datetime.now(UTC).isoformat(),
                "parser_version": PARSER_VERSION,
            }
            audit(
                session,
                "record.reparse",
                patient_id=import_session.patient_id,
                entity_type="SourceDocument",
                entity_id=source.id,
                file_hash=source.sha256,
                metadata={
                    "import_id": import_session.id,
                    "parser_version": PARSER_VERSION,
                    "added": len(added),
                    "superseded": len(pending_to_supersede),
                },
            )
            data.update(
                {
                    "added_candidate_ids": sorted(added),
                    "retained_candidate_ids": sorted(retained),
                    "revived_candidate_ids": sorted(revived),
                    "superseded_candidate_ids": pending_to_supersede,
                }
            )
        emit("record.reparse", data, json_output=json_output)
    except Exception as exc:
        emit_error("record.reparse", exc)
        raise typer.Exit(1) from exc


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
                    "details": {
                        "report_type": "laboratory",
                        "import_id": import_session.id,
                        "institution": candidate.payload.get("institution"),
                    },
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
    if candidate.candidate_type == "procedure":
        record = Procedure(**common)
        session.add(record)
        session.flush()
        return "Procedure", record.id
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
    if candidate.candidate_type in {"clinical_opinion", "pathology"}:
        record = Diagnosis(**common)
        record.source_type = (
            "clinician_opinion" if candidate.candidate_type == "clinical_opinion" else "source_fact"
        )
        session.add(record)
        session.flush()
        specialized_model = (
            ClinicalOpinionCandidate
            if candidate.candidate_type == "clinical_opinion"
            else PathologyCandidate
        )
        specialized = session.get(specialized_model, candidate.id)
        if specialized:
            specialized.status = "confirmed"
            specialized.formal_record_id = record.id
            specialized.reviewed_at = datetime.now(UTC)
        return "Diagnosis", record.id
    if candidate.candidate_type == "followup_plan":
        payload = candidate.payload
        base = (
            datetime.fromisoformat(payload["base_date"])
            if payload.get("base_date")
            else datetime.now(UTC)
        )

        def plus_months(value: datetime, months: int) -> datetime:
            month = value.month - 1 + months
            year, month = value.year + month // 12, month % 12 + 1
            return value.replace(
                year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
            )

        start = plus_months(base, int(payload["interval_months_min"]))
        end = plus_months(base, int(payload["interval_months_max"]))
        plan = FollowUpPlan(
            **common,
            title=payload["title"],
            category=payload["category"],
            recommendation_source_type="clinician_opinion",
            due_date=None,
            due_date_start=start,
            due_date_end=end,
            priority="normal",
            status="pending",
            reason=candidate.original_text,
        )
        session.add(plan)
        session.flush()
        return "FollowUpPlan", plan.id
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
            specialized_model = {
                "clinical_opinion": ClinicalOpinionCandidate,
                "pathology": PathologyCandidate,
            }.get(candidate.candidate_type)
            if specialized_model and (specialized := session.get(specialized_model, candidate.id)):
                specialized.status = "rejected"
                specialized.reviewed_at = datetime.now(UTC)
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
                Diagnosis,
                FollowUpPlan,
                LaboratoryReport,
                LaboratoryResult,
                ImagingReport,
                Procedure,
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
