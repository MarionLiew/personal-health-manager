from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated

import typer

from health_agent.cli.helpers import require_gate
from health_agent.cli.main import emit
from health_agent.config import load_settings
from health_agent.database.migrations import migrate
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure
from health_agent.services.clinical_exports import (
    VERSION as CLINICAL_VERSION,
)
from health_agent.services.clinical_exports import (
    build_case_bundle,
    build_lesion_bundle,
    build_visit_bundle,
    write_case_zip,
)
from health_agent.services.gpt_export import EXPORT_VERSION, build_gpt_bundle, bundle_counts

app = typer.Typer(no_args_is_help=True)


def _clinical_output(value: Path, suffix: str) -> Path:
    settings = load_settings()
    root = (settings.data_root / "exports").resolve()
    destination = (value if value.is_absolute() else root / value).resolve()
    if not destination.is_relative_to(root) or destination.suffix.lower() != suffix:
        raise ValidationFailure(
            f"Clinical export output must stay inside exports and end in {suffix}"
        )
    return destination


def _clinical_export(
    action: str,
    output: Path,
    dry_run: bool,
    confirm: bool,
    json_output: bool,
    builder,
    *,
    suffix: str = ".json",
) -> None:
    require_gate(dry_run, confirm)
    destination = _clinical_output(output, suffix)
    migrate()
    with session_scope() as session:
        if destination.exists() and not dry_run:
            raise ValidationFailure("Export destination already exists")
        if suffix == ".zip":
            preview_bundle = build_case_bundle(session)
            payload = None
        else:
            preview_bundle = builder(session)
            payload = (json.dumps(preview_bundle, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            )
        result = {
            "output": str(destination),
            "format_version": CLINICAL_VERSION,
            "source_count": len(preview_bundle["source_index"]),
            "scope": action,
        }
        if dry_run:
            emit(action + ".preview", result, json_output=json_output, requires_confirmation=True)
            return
        if suffix == ".zip":
            write_case_zip(session, destination)
        else:
            assert payload is not None
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with destination.open("xb") as handle:
                handle.write(payload)
            destination.chmod(0o600)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        entry = audit(
            session,
            action,
            patient_id="local-primary",
            entity_type="ClinicalExport",
            file_hash=digest,
            metadata={
                "format_version": CLINICAL_VERSION,
                "scope": action,
                "source_count": result["source_count"],
                "output": str(destination),
            },
        )
        result.update({"sha256": digest, "audit_id": entry.id, "created": True})
    emit(action, result, json_output=json_output)


@app.command("lesion-bundle")
def lesion_bundle_command(
    lesion_id: str,
    output: Annotated[Path, typer.Option("--output")],
    include_unconfirmed: bool = typer.Option(False, "--include-unconfirmed"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Export one lesion with its evidence chain as structured JSON."""
    _clinical_export(
        "export.lesion-bundle",
        output,
        dry_run,
        confirm,
        json_output,
        lambda session: build_lesion_bundle(
            session, lesion_id, include_unconfirmed=include_unconfirmed
        ),
    )


@app.command("visit-bundle")
def visit_bundle_command(
    department: Annotated[str, typer.Option("--department")],
    purpose: Annotated[str, typer.Option("--purpose")],
    output: Annotated[Path, typer.Option("--output")],
    include_unconfirmed: bool = typer.Option(False, "--include-unconfirmed"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Export a purpose-filtered doctor overview and report index."""
    _clinical_export(
        "export.visit-bundle",
        output,
        dry_run,
        confirm,
        json_output,
        lambda session: build_visit_bundle(
            session, department, purpose, include_unconfirmed=include_unconfirmed
        ),
    )


@app.command("record-index")
def record_index_command(
    output: Annotated[Path, typer.Option("--output")],
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Export the structured source/report index."""
    _clinical_export(
        "export.record-index",
        output,
        dry_run,
        confirm,
        json_output,
        lambda session: {
            "source_index": build_case_bundle(session)["source_index"],
            "format_version": CLINICAL_VERSION,
        },
    )


@app.command("case-bundle")
def case_bundle_command(
    output: Annotated[Path, typer.Option("--output")],
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Export full case manifest and verified original documents as ZIP."""
    _clinical_export(
        "export.case-bundle",
        output,
        dry_run,
        confirm,
        json_output,
        build_case_bundle,
        suffix=".zip",
    )


def _safe_output(value: Path) -> Path:
    settings = load_settings()
    root = (settings.data_root / "exports").resolve()
    candidate = value if value.is_absolute() else root / value
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValidationFailure(
            "GPT export output must stay inside the configured exports directory"
        )
    if resolved.suffix.lower() != ".json":
        raise ValidationFailure("GPT export output must use a .json extension")
    return resolved


@app.command("gpt-bundle")
def gpt_bundle_command(
    output: Annotated[Path, typer.Option("--output")],
    exclude_institutions: bool = typer.Option(False, "--exclude-institutions"),
    include_pending: bool = typer.Option(False, "--include-pending"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Create a local, redacted JSON bundle for optional user-directed GPT analysis."""
    require_gate(dry_run, confirm)
    destination = _safe_output(output)
    migrate()
    with session_scope() as session:
        bundle = build_gpt_bundle(
            session,
            include_institutions=not exclude_institutions,
            include_pending=include_pending,
        )
        counts = bundle_counts(bundle)
        preview = {
            "output": str(destination),
            "format_version": EXPORT_VERSION,
            "record_counts": counts,
            "source_count": len(bundle["source_index"]),
            "pending_candidate_count": bundle["pending_candidate_summary"]["count"],
            "pending_candidates_included": include_pending,
            "institutions_included": not exclude_institutions,
            "raw_documents_included": False,
            "raw_report_text_included": False,
            "images_included": False,
            "external_upload_performed": False,
        }
        if dry_run:
            emit(
                "export.gpt-bundle.preview",
                preview,
                json_output=json_output,
                warnings=[
                    "The generated file will still contain sensitive health information.",
                    "No upload to GPT or any external service is performed by this command.",
                    *(
                        [
                            "Pending parser candidates will be exported only as separately "
                            "labelled unconfirmed system inferences."
                        ]
                        if include_pending
                        else []
                    ),
                ],
                requires_confirmation=True,
            )
            return
        if destination.exists():
            raise ValidationFailure("Export destination already exists; choose a new filename")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encoded = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        with destination.open("xb") as handle:
            handle.write(encoded)
        destination.chmod(0o600)
        entry = audit(
            session,
            "export.gpt-bundle",
            patient_id="local-primary",
            entity_type="GPTAnalysisBundle",
            file_hash=content_hash,
            metadata={
                "format_version": EXPORT_VERSION,
                "source_count": len(bundle["source_index"]),
                "institutions_included": not exclude_institutions,
                "pending_candidates_included": include_pending,
            },
        )
        preview.update(
            {
                "created": True,
                "sha256": content_hash,
                "audit_id": entry.id,
                "file_size": len(encoded),
            }
        )
    emit(
        "export.gpt-bundle",
        preview,
        json_output=json_output,
        warnings=[
            "Review the JSON locally before choosing whether to upload it to an external service."
        ],
    )
