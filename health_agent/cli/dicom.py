from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pydicom
import typer
from sqlalchemy import select

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.database.migrations import migrate
from health_agent.database.models import (
    ImportSession,
    RadiationAcquisition,
    RadiationExposure,
    SourceDocument,
)
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.importers.archive import safe_extract_zip
from health_agent.importers.base import detected_mime, hash_path
from health_agent.parsers.dicom import DicomItem, scan_paths, unique_acquisitions
from health_agent.parsers.dicom_rdsr import parse_rdsr
from health_agent.safety.privacy import require_allowed_import_path

app = typer.Typer(no_args_is_help=True)


@contextmanager
def resolved_target(path: Path):
    settings = load_settings()
    source = require_allowed_import_path(path, settings)
    temporary: Path | None = None
    try:
        target = source
        if source.is_file() and source.suffix.lower() == ".zip":
            temporary = Path(
                tempfile.mkdtemp(prefix="dicom-", dir=settings.data_root / "quarantine")
            )
            safe_extract_zip(source, temporary, settings)
            target = temporary
        yield source, target, settings
    finally:
        if temporary:
            shutil.rmtree(temporary)


def _analysis(items: list[DicomItem]) -> dict[str, Any]:
    acquisitions = unique_acquisitions(items)
    studies = {item.metadata.get("StudyInstanceUID") for item in items}
    rdsr_reports = [parse_rdsr(pydicom.dcmread(item.path)) for item in items if item.is_rdsr]
    dose_screens = [
        item
        for item in items
        if any(
            term in str(item.metadata.get("SeriesDescription") or "").lower()
            for term in ("dose report", "dose screen", "剂量")
        )
    ]
    return {
        "dicom_files": len(items),
        "study_count": len(studies - {None}),
        "rdsr_count": len(rdsr_reports),
        "dose_screen_count": len(dose_screens),
        "rdsr_reports": rdsr_reports,
        "reconstruction_series_count": sum(item.is_reconstruction for item in items),
        "actual_acquisition_count": len(acquisitions),
        "identity_fields_detected": sorted(
            {tag for item in items for tag in item.identity_tags_present}
        ),
        "dose_data_quality": (
            "exact_machine_record"
            if rdsr_reports
            else "documented_value"
            if dose_screens
            else "insufficient_data"
        ),
        "warnings": [] if items else ["No valid DICOM datasets found"],
    }


def inspect_target(path: Path) -> dict[str, Any]:
    with resolved_target(path) as (_, target, _):
        return _analysis(scan_paths(target))


@app.command("inspect")
def inspect_command(path: Path, json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        data = inspect_target(path)
        emit("dicom.inspect", data, json_output=json_output, warnings=data.pop("warnings"))
    except Exception as exc:
        emit_error("dicom.inspect", exc)
        raise typer.Exit(1) from exc


@app.command("dose")
def dose_command(path: Path, json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        data = inspect_target(path)
        uncertainties = []
        if data["rdsr_count"] == 0:
            uncertainties.append(
                "No RDSR was found; no precise mSv is generated from protocol or image count."
            )
        if data["dose_screen_count"] and not data["rdsr_count"]:
            uncertainties.append(
                "Dose Screen detected; OCR values require candidate confirmation before entry."
            )
        emit("dicom.dose", data, json_output=json_output, uncertainties=uncertainties)
    except Exception as exc:
        emit_error("dicom.dose", exc)
        raise typer.Exit(1) from exc


def _dicom_datetime(report: dict[str, Any]) -> datetime | None:
    value = f"{report.get('study_date') or ''}{str(report.get('study_time') or '')[:6]}"
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _save_rdsr(
    session,
    report: dict[str, Any],
    source: SourceDocument,
    import_id: str,
    audit_id: str,
) -> RadiationExposure:
    occurred = _dicom_datetime(report)
    exposure = RadiationExposure(
        patient_id="local-primary",
        source_type="source_fact",
        source_document_id=source.id,
        occurred_at=occurred,
        original_text=None,
        extraction_method="pydicom-rdsr",
        extraction_version="2",
        confidence=1.0,
        verified=True,
        verification_status="machine_record_confirmed",
        audit_id=audit_id,
        examination_date=occurred,
        institution=None,
        modality="CT",
        examination_name=str(report.get("protocol_name") or "CT examination"),
        body_region=report.get("body_region"),
        protocol_name=report.get("protocol_name"),
        acquisition_count=len(report["events"]),
        dose_data_source="dicom_rdsr",
        data_quality="exact_machine_record",
        details={
            **{key: value for key, value in report.items() if key != "events"},
            "import_id": import_id,
        },
    )
    session.add(exposure)
    session.flush()
    seen: set[str] = set()
    for event in report["events"]:
        uid = str(event.get("irradiation_event_uid") or "")
        fallback = json.dumps(event, sort_keys=True)
        key = uid or fallback
        if key in seen:
            continue
        seen.add(key)
        session.add(
            RadiationAcquisition(
                exposure_id=exposure.id,
                irradiation_event_uid=uid or None,
                acquisition_type=str(event.get("acquisition_type") or "unknown"),
                body_region=report.get("body_region"),
                scan_length_cm=event.get("scanning_length_cm"),
                ctdi_vol_mgy=event.get("ctdi_vol_mgy"),
                dlp_mgy_cm=event.get("dlp_mgy_cm"),
                tube_voltage_kvp=event.get("tube_voltage_kvp"),
                tube_current_mas=event.get("mas") or event.get("effective_mas"),
                exposure_time=event.get("exposure_time_s"),
                pitch=event.get("pitch"),
                repeat_reason=event.get("repeat_reason"),
                original_text=json.dumps(event, ensure_ascii=False, sort_keys=True),
            )
        )
    exposure.acquisition_count = len(seen)
    return exposure


@app.command("import")
def import_command(
    path: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    try:
        if dry_run == confirm:
            raise ValueError("Specify exactly one of --dry-run or --confirm")
        with resolved_target(path) as (source_path, target, settings):
            analysis = _analysis(scan_paths(target))
            source_hash = hash_path(source_path)
            data = {**analysis, "sha256": source_hash, "source_path": str(source_path)}
            if dry_run:
                emit(
                    "dicom.import.preview",
                    data,
                    json_output=json_output,
                    warnings=data.pop("warnings"),
                    requires_confirmation=bool(analysis["rdsr_count"]),
                )
                return
            if not analysis["rdsr_reports"]:
                raise ValueError("No RDSR available for confirmed dose import")
            migrate()
            with session_scope() as session:
                existing = session.scalar(
                    select(SourceDocument).where(SourceDocument.sha256 == source_hash)
                )
                if existing and not existing.revoked:
                    exposures = session.scalars(
                        select(RadiationExposure).where(
                            RadiationExposure.source_document_id == existing.id
                        )
                    ).all()
                    data.update(
                        {"duplicate": True, "exposure_ids": [item.id for item in exposures]}
                    )
                else:
                    source = existing or SourceDocument(
                        patient_id="local-primary",
                        original_filename=source_path.name,
                        local_path=str(source_path),
                        mime_type=detected_mime(source_path),
                        file_size=source_path.stat().st_size if source_path.is_file() else 0,
                        sha256=source_hash,
                        data_origin="dicom",
                        contains_identity=bool(analysis["identity_fields_detected"]),
                        human_confirmed=True,
                        parser_name="pydicom-rdsr",
                        parser_version="2",
                    )
                    source.revoked = False
                    session.add(source)
                    session.flush()
                    import_session = ImportSession(
                        patient_id="local-primary",
                        source_sha256=source_hash,
                        source_document_id=source.id,
                        kind="dicom_rdsr",
                        status="confirmed",
                        preview=data,
                        confirmed_at=datetime.now(UTC),
                    )
                    session.add(import_session)
                    session.flush()
                    entry = audit(
                        session,
                        "dicom.import",
                        patient_id="local-primary",
                        entity_type="ImportSession",
                        entity_id=import_session.id,
                        file_hash=source_hash,
                    )
                    exposures = [
                        _save_rdsr(session, report, source, import_session.id, entry.id)
                        for report in analysis["rdsr_reports"]
                    ]
                    data.update(
                        {
                            "duplicate": False,
                            "import_id": import_session.id,
                            "source_document_id": source.id,
                            "exposure_ids": [item.id for item in exposures],
                        }
                    )
            emit("dicom.import", data, json_output=json_output)
    except Exception as exc:
        emit_error("dicom.import", exc)
        raise typer.Exit(1) from exc
