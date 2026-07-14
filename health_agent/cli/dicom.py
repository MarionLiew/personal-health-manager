from __future__ import annotations

import json
import shutil
import subprocess
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
    DoseScreenCandidate,
    ImportSession,
    RadiationAcquisition,
    RadiationExposure,
    SourceDocument,
)
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import OcrUnavailable, ValidationFailure
from health_agent.importers.archive import safe_extract_zip
from health_agent.importers.base import detected_mime, hash_path
from health_agent.parsers.dicom import (
    DicomItem,
    metadata_dose_events,
    scan_paths,
    unique_acquisitions,
)
from health_agent.parsers.dicom_rdsr import parse_rdsr
from health_agent.parsers.dose_screen import dose_screen_warnings, parse_dose_screen_text
from health_agent.safety.privacy import require_allowed_import_path

app = typer.Typer(no_args_is_help=True)


def _local_ocr_text(path: Path) -> str:
    if path.suffix.lower() in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        raise OcrUnavailable(
            "Dose Screen OCR supports an image or locally extracted OCR text; DICOM pixel "
            "rendering is not available in this installation."
        )
    executable = shutil.which("tesseract")
    if executable is None:
        raise OcrUnavailable("No local OCR engine is installed; no image data was sent externally.")
    result = subprocess.run(  # noqa: S603 - executable is a resolved local tesseract path.
        [executable, str(path), "stdout"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise OcrUnavailable("Local OCR engine could not read the Dose Screen image.")
    return result.stdout


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
    metadata_events = metadata_dose_events(items)
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
        "metadata_dose_events": metadata_events,
        "reconstruction_series_count": sum(item.is_reconstruction for item in items),
        "actual_acquisition_count": len(acquisitions),
        "identity_fields_detected": sorted(
            {tag for item in items for tag in item.identity_tags_present}
        ),
        "dose_data_quality": (
            "exact_machine_record"
            if rdsr_reports
            else "documented_value"
            if dose_screens or any(event["ctdi_vol_mgy"] is not None for event in metadata_events)
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


@app.command("dose-screen")
def dose_screen_command(
    path: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    candidate_ids: str | None = typer.Option(None, "--candidate-ids"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    try:
        if dry_run == confirm:
            raise ValidationFailure("Specify exactly one of --dry-run or --confirm")
        settings = load_settings()
        source_path = require_allowed_import_path(path, settings)
        if not source_path.is_file():
            raise ValidationFailure("Dose Screen input must be one file")
        source_hash = hash_path(source_path)
        ocr_text = _local_ocr_text(source_path)
        candidates = parse_dose_screen_text(ocr_text, source_hash)
        if not candidates:
            raise ValidationFailure("No CT dose fields were detected in the Dose Screen")
        warnings = dose_screen_warnings(candidates)
        data: dict[str, Any] = {
            "sha256": source_hash,
            "candidates": candidates,
            "ocr_engine": "provided_text"
            if source_path.suffix.lower() in {".txt", ".md"}
            else "tesseract-local",
            "candidate_count": len(candidates),
        }
        if dry_run:
            emit(
                "dicom.dose-screen.preview",
                data,
                json_output=json_output,
                warnings=warnings,
                uncertainties=["OCR fields are candidates and are not machine-record values."],
                requires_confirmation=True,
            )
            return
        selected_ids = {item.strip() for item in (candidate_ids or "").split(",") if item.strip()}
        selected = [item for item in candidates if item["id"] in selected_ids]
        if not selected_ids or len(selected) != len(selected_ids):
            raise ValidationFailure("Every confirmed candidate ID must exist in the preview")
        migrate()
        with session_scope() as session:
            existing = session.scalar(
                select(SourceDocument).where(SourceDocument.sha256 == source_hash)
            )
            if existing and not existing.revoked:
                data.update({"duplicate": True, "source_document_id": existing.id})
                emit("dicom.dose-screen", data, json_output=json_output, warnings=warnings)
                return
            originals = settings.data_root / "reports" / "originals"
            originals.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = originals / f"{source_hash}{source_path.suffix.lower()}"
            if not destination.exists():
                shutil.copy2(source_path, destination)
                destination.chmod(0o400)
            source = existing or SourceDocument(
                patient_id="local-primary",
                original_filename=source_path.name,
                local_path=str(destination),
                mime_type=detected_mime(source_path),
                file_size=source_path.stat().st_size,
                sha256=source_hash,
                data_origin="dose_screen",
                human_confirmed=True,
                parser_name="local-dose-screen-ocr",
                parser_version="3",
            )
            source.revoked = False
            session.add(source)
            session.flush()
            import_session = ImportSession(
                patient_id="local-primary",
                source_sha256=source_hash,
                source_document_id=source.id,
                kind="dose_screen",
                status="confirmed",
                preview={"candidates": candidates},
                confirmed_at=datetime.now(UTC),
            )
            session.add(import_session)
            session.flush()
            entry = audit(
                session,
                "dicom.dose-screen",
                patient_id="local-primary",
                entity_type="ImportSession",
                entity_id=import_session.id,
                file_hash=source_hash,
                metadata={"confirmed_candidate_ids": sorted(selected_ids)},
            )
            for item in candidates:
                session.add(
                    DoseScreenCandidate(
                        id=item["id"],
                        import_session_id=import_session.id,
                        patient_id="local-primary",
                        payload={
                            "field": item["field"],
                            "value": item["value"],
                            "unit": item["unit"],
                        },
                        original_text=item["original_text"],
                        confidence=item["confidence"],
                        status="accepted" if item["id"] in selected_ids else "rejected",
                        region=item["region"],
                        reviewed_at=datetime.now(UTC),
                    )
                )
            by_field: dict[str, list[dict[str, Any]]] = {}
            for item in selected:
                by_field.setdefault(str(item["field"]), []).append(item)
            event_dlps = by_field.get("event_dlp", [])
            ctdis = by_field.get("ctdi_vol", [])
            protocol = str(by_field.get("protocol", [{}])[0].get("value") or "CT Dose Screen")
            total_dlp = (
                float(by_field["total_dlp"][0]["value"]) if by_field.get("total_dlp") else None
            )
            exposure = RadiationExposure(
                patient_id="local-primary",
                source_type="source_fact",
                source_document_id=source.id,
                extraction_method="local-ocr+human-confirmation",
                extraction_version="3",
                confidence=min(float(item["confidence"]) for item in selected),
                verified=True,
                verification_status="human_confirmed_ocr",
                audit_id=entry.id,
                modality="CT",
                examination_name=protocol,
                protocol_name=protocol,
                acquisition_count=max(len(event_dlps), len(ctdis)),
                dose_data_source="scanner_dose_page",
                data_quality="documented_value",
                notes="OCR-derived values confirmed by user; Total DLP is not added to event DLP.",
                details={"import_id": import_session.id, "total_dlp_mgy_cm": total_dlp},
            )
            session.add(exposure)
            session.flush()
            for index in range(max(len(event_dlps), len(ctdis))):
                session.add(
                    RadiationAcquisition(
                        exposure_id=exposure.id,
                        acquisition_type="dose_screen_event",
                        ctdi_vol_mgy=(float(ctdis[index]["value"]) if index < len(ctdis) else None),
                        dlp_mgy_cm=(
                            float(event_dlps[index]["value"]) if index < len(event_dlps) else None
                        ),
                        original_text="Human-confirmed Dose Screen OCR candidates",
                    )
                )
            data.update(
                {
                    "duplicate": False,
                    "import_id": import_session.id,
                    "source_document_id": source.id,
                    "exposure_id": exposure.id,
                    "confirmed_candidate_ids": sorted(selected_ids),
                }
            )
        emit("dicom.dose-screen", data, json_output=json_output, warnings=warnings)
    except Exception as exc:
        emit_error("dicom.dose-screen", exc)
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


def _save_metadata_exposure(
    session,
    events: list[dict[str, Any]],
    source: SourceDocument,
    import_id: str,
    audit_id: str,
) -> RadiationExposure:
    first = events[0]
    occurred = _dicom_datetime(first)
    has_machine_value = any(event.get("ctdi_vol_mgy") is not None for event in events)
    exposure = RadiationExposure(
        patient_id="local-primary",
        source_type="source_fact",
        source_document_id=source.id,
        occurred_at=occurred,
        extraction_method="pydicom-metadata",
        extraction_version="3",
        confidence=0.9 if has_machine_value else 0.6,
        verified=True,
        verification_status="metadata_confirmed",
        audit_id=audit_id,
        examination_date=occurred,
        modality=str(first.get("modality") or "unknown"),
        examination_name=str(first.get("protocol_name") or "DICOM examination"),
        body_region=first.get("body_region"),
        protocol_name=first.get("protocol_name"),
        acquisition_count=len(events),
        dose_data_source="dicom_metadata",
        data_quality="documented_value" if has_machine_value else "insufficient_data",
        notes="DLP and effective dose were not inferred from ordinary DICOM images.",
        details={"import_id": import_id, "dose_incomplete": True},
    )
    session.add(exposure)
    session.flush()
    for event in events:
        session.add(
            RadiationAcquisition(
                exposure_id=exposure.id,
                series_number=event.get("series_number"),
                irradiation_event_uid=event.get("irradiation_event_uid"),
                acquisition_uid=event.get("acquisition_uid"),
                acquisition_type=str(event.get("acquisition_type") or "unknown"),
                body_region=event.get("body_region"),
                ctdi_vol_mgy=event.get("ctdi_vol_mgy"),
                dlp_mgy_cm=None,
                tube_voltage_kvp=event.get("tube_voltage_kvp"),
                tube_current_mas=event.get("tube_current_mas"),
                pitch=event.get("pitch"),
                original_text=json.dumps(event, ensure_ascii=False, sort_keys=True),
            )
        )
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
                    requires_confirmation=bool(
                        analysis["rdsr_count"] or analysis["metadata_dose_events"]
                    ),
                )
                return
            if not analysis["rdsr_reports"] and not analysis["metadata_dose_events"]:
                raise ValueError("No radiation acquisition was found")
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
                    if analysis["rdsr_reports"]:
                        exposures = [
                            _save_rdsr(session, report, source, import_session.id, entry.id)
                            for report in analysis["rdsr_reports"]
                        ]
                    else:
                        exposures = [
                            _save_metadata_exposure(
                                session,
                                analysis["metadata_dose_events"],
                                source,
                                import_session.id,
                                entry.id,
                            )
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
