from __future__ import annotations

import typer
from sqlalchemy import select

from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import ImagingReport, ImagingStudy, SourceDocument
from health_agent.database.session import session_scope

app = typer.Typer(no_args_is_help=True)


def _record_row(record: ImagingReport | ImagingStudy) -> dict[str, object]:
    return {
        "id": record.id,
        "record_type": "report" if isinstance(record, ImagingReport) else "study",
        "occurred_at": record.occurred_at.isoformat() if record.occurred_at else None,
        "source_type": record.source_type,
        "source_document_id": record.source_document_id,
        "verified": record.verified,
        "verification_status": record.verification_status,
        "details": record.details,
    }


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    """List active imaging studies and confirmed imaging reports."""
    migrate()
    with session_scope() as session:
        records: list[ImagingReport | ImagingStudy] = []
        for model in (ImagingStudy, ImagingReport):
            records.extend(
                session.scalars(
                    select(model)
                    .outerjoin(SourceDocument, model.source_document_id == SourceDocument.id)
                    .where(
                        model.verified.is_(True),
                        (SourceDocument.id.is_(None)) | (SourceDocument.revoked.is_(False)),
                    )
                ).all()
            )
    records.sort(
        key=lambda item: (item.occurred_at is not None, item.occurred_at, item.recorded_at),
        reverse=True,
    )
    emit(
        "imaging.list",
        {"imaging": [_record_row(record) for record in records]},
        json_output=json_output,
    )
