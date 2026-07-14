from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import typer

from health_agent.cli.main import emit, emit_error
from health_agent.config import load_settings
from health_agent.importers.archive import safe_extract_zip
from health_agent.parsers.dicom import scan_paths, unique_acquisitions
from health_agent.safety.privacy import require_allowed_import_path

app = typer.Typer(no_args_is_help=True)


def inspect_target(path: Path) -> dict[str, object]:
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
        items = scan_paths(target)
        acquisitions = unique_acquisitions(items)
        studies = {item.metadata.get("StudyInstanceUID") for item in items}
        return {
            "dicom_files": len(items),
            "study_count": len(studies - {None}),
            "rdsr_count": sum(item.is_rdsr for item in items),
            "reconstruction_series_count": sum(item.is_reconstruction for item in items),
            "actual_acquisition_count": len(acquisitions),
            "identity_fields_detected": sorted(
                {tag for item in items for tag in item.identity_tags_present}
            ),
            "dose_data_quality": "exact_machine_record"
            if any(item.is_rdsr for item in items)
            else "insufficient_data",
            "warnings": [] if items else ["No valid DICOM datasets found"],
        }
    finally:
        if temporary:
            shutil.rmtree(temporary)


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
        emit("dicom.dose", data, json_output=json_output, uncertainties=uncertainties)
    except Exception as exc:
        emit_error("dicom.dose", exc)
        raise typer.Exit(1) from exc
