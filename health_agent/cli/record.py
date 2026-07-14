from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer
from sqlalchemy import select

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.constants import SourceType
from health_agent.database.migrations import migrate
from health_agent.database.models import ImagingReport, ImportSession, SourceDocument
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
                data.update({"duplicate": True, "source_document_id": existing.id})
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
            entry = audit(
                session,
                "record.import",
                patient_id="local-primary",
                entity_type="SourceDocument",
                entity_id=source.id,
                file_hash=preview.sha256,
                metadata={"parser_version": "1", "import_id": import_session.id},
            )
            report = ImagingReport(
                patient_id="local-primary",
                source_type=SourceType.SOURCE_FACT.value,
                source_document_id=source.id,
                original_text=preview.text,
                extraction_method=preview.parser,
                extraction_version="1",
                confidence=1.0 if preview.text else None,
                verified=True,
                verification_status="human_confirmed_source",
                audit_id=entry.id,
                details={"document_kind": "unclassified_medical_report"},
            )
            session.add(report)
            session.flush()
            data.update(
                {
                    "source_document_id": source.id,
                    "record_id": report.id,
                    "import_id": import_session.id,
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
