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
from health_agent.services.gpt_export import EXPORT_VERSION, build_gpt_bundle, bundle_counts

app = typer.Typer(no_args_is_help=True)


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
