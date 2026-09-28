from __future__ import annotations

import typer

from health_agent.cli.helpers import parse_datetime, require_gate
from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import Lesion, LesionSourceLink
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure
from health_agent.services.lesion_tracker import (
    active_lesions,
    add_measurement,
    comparison,
    create_lesion,
    formal_history,
    link_source,
    measurement_rows,
    require_lesion,
    unlink_source,
    update_lesion,
)

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        lesions = active_lesions(session)
        data = {
            "lesions": [
                {"id": lesion.id, **lesion.details, "source_document_id": lesion.source_document_id}
                for lesion in lesions
            ]
        }
    emit("lesions.list", data, json_output=json_output)


@app.command("show")
def show_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        lesion = session.get(Lesion, lesion_id)
        if lesion is None:
            raise typer.BadParameter("Lesion not found")
        rows = measurement_rows(session, lesion_id)
        data = {"id": lesion.id, **lesion.details, "measurements": rows}
    emit("lesions.show", data, json_output=json_output)


@app.command("measurements")
def measurements_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = measurement_rows(session, lesion_id)
    emit(
        "lesions.measurements",
        {"lesion_id": lesion_id, "measurements": rows},
        json_output=json_output,
    )


@app.command("compare")
def compare_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = measurement_rows(session, lesion_id)
    emit(
        "lesions.compare",
        {"lesion_id": lesion_id, **comparison(rows)},
        json_output=json_output,
    )


@app.command("create")
def create_command(
    display_code: str = typer.Option(..., "--display-code"),
    name: str = typer.Option(..., "--name"),
    laterality: str | None = typer.Option(None, "--laterality"),
    body_region: str | None = typer.Option(None, "--body-region"),
    anatomical_location: str | None = typer.Option(None, "--anatomical-location"),
    tracking_status: str = typer.Option("active", "--tracking-status"),
    notes: str | None = typer.Option(None, "--notes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if (
        not display_code.strip()
        or not name.strip()
        or tracking_status not in {"active", "resolved", "uncertain", "archived"}
    ):
        raise ValidationFailure("Invalid lesion fields")
    data = dict(
        display_code=display_code,
        name=name,
        laterality=laterality,
        body_region=body_region,
        anatomical_location=anatomical_location,
        tracking_status=tracking_status,
        notes=notes,
    )
    migrate()
    with session_scope() as session:
        if dry_run:
            from sqlalchemy import select

            if session.scalars(
                select(Lesion).where(Lesion.details["display_code"].as_string() == display_code)
            ).first():
                raise ValidationFailure("Display code already exists")
        else:
            lesion = create_lesion(session, **data)
            data.update(id=lesion.id, source_type=lesion.source_type)
    emit(
        "lesions.create.preview" if dry_run else "lesions.create",
        data,
        json_output=json_output,
        requires_confirmation=dry_run,
    )


@app.command("update")
def update_command(
    lesion_id: str,
    name: str | None = typer.Option(None, "--name"),
    laterality: str | None = typer.Option(None, "--laterality"),
    body_region: str | None = typer.Option(None, "--body-region"),
    anatomical_location: str | None = typer.Option(None, "--anatomical-location"),
    tracking_status: str | None = typer.Option(None, "--tracking-status"),
    notes: str | None = typer.Option(None, "--notes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    changes = {
        key: value
        for key, value in dict(
            name=name,
            laterality=laterality,
            body_region=body_region,
            anatomical_location=anatomical_location,
            tracking_status=tracking_status,
            notes=notes,
        ).items()
        if value is not None
    }
    if not changes or (
        tracking_status and tracking_status not in {"active", "resolved", "uncertain", "archived"}
    ):
        raise ValidationFailure("No valid mutable fields")
    migrate()
    with session_scope() as session:
        lesion = require_lesion(session, lesion_id)
        previous = dict(lesion.details)
        if not dry_run:
            lesion = update_lesion(session, lesion_id, **changes)
        data = {
            "id": lesion.id,
            **({**previous, **changes} if dry_run else lesion.details),
            "previous": previous,
        }
    emit(
        "lesions.update.preview" if dry_run else "lesions.update",
        data,
        json_output=json_output,
        requires_confirmation=dry_run,
    )


@app.command("link-source")
def link_source_command(
    lesion_id: str,
    source_document_id: str,
    evidence_type: str = typer.Option(..., "--evidence-type"),
    status: str = typer.Option(..., "--status"),
    scope: str = typer.Option("individual", "--scope"),
    original_text: str | None = typer.Option(None, "--original-text"),
    import_id: str | None = typer.Option(None, "--import-id"),
    report_record_id: str | None = typer.Option(None, "--report-record-id"),
    page: int | None = typer.Option(None, "--page"),
    original_offset: int | None = typer.Option(None, "--original-offset"),
    examination_date: str | None = typer.Option(None, "--examination-date"),
    examination_type: str | None = typer.Option(None, "--examination-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    from health_agent.services.lesion_tracker import require_source, validate_evidence

    require_gate(dry_run, confirm)
    validate_evidence(evidence_type, status, scope)
    date = parse_datetime(examination_date, "examination-date")
    data = dict(
        lesion_id=lesion_id,
        source_document_id=source_document_id,
        evidence_type=evidence_type,
        status=status,
        scope=scope,
        original_text=original_text,
        import_id=import_id,
        report_record_id=report_record_id,
        page=page,
        original_offset=original_offset,
        examination_date=examination_date,
        examination_type=examination_type,
    )
    migrate()
    with session_scope() as session:
        require_lesion(session, lesion_id)
        source = require_source(session, source_document_id)
        if not dry_run:
            link = link_source(
                session,
                lesion_id,
                source_document_id,
                evidence_type=evidence_type,
                status=status,
                scope=scope,
                original_text=original_text,
                import_id=import_id,
                report_record_id=report_record_id,
                page=page,
                original_offset=original_offset,
                examination_date=date,
                examination_type=examination_type,
            )
            data["id"] = link.id
        data["original_filename"] = source.original_filename
    emit(
        "lesions.link-source.preview" if dry_run else "lesions.link-source",
        data,
        json_output=json_output,
        requires_confirmation=dry_run,
    )


@app.command("unlink")
def unlink_command(
    lesion_id: str,
    link_id: str,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    migrate()
    with session_scope() as session:
        require_lesion(session, lesion_id)
        link = session.get(LesionSourceLink, link_id)
        if link is None or link.lesion_id != lesion_id or link.unlinked_at is not None:
            raise ValidationFailure("Active source link not found")
        data = {
            "lesion_id": lesion_id,
            "link_id": link_id,
            "source_document_id": link.source_document_id,
            "previous_status": link.status,
        }
        if not dry_run:
            unlink_source(session, lesion_id, link_id)
    emit(
        "lesions.unlink.preview" if dry_run else "lesions.unlink",
        data,
        json_output=json_output,
        requires_confirmation=dry_run,
    )


@app.command("add-measurement")
def add_measurement_command(
    lesion_id: str,
    source: str = typer.Option(..., "--source"),
    size: float = typer.Option(..., "--size"),
    unit: str = typer.Option(..., "--unit"),
    original_text: str = typer.Option(..., "--original-text"),
    laterality: str | None = typer.Option(None, "--laterality"),
    evidence_type: str = typer.Option("source_fact", "--evidence-type"),
    status: str = typer.Option("unresolved", "--status"),
    scope: str = typer.Option("individual", "--scope"),
    examination_date: str | None = typer.Option(None, "--examination-date"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    from health_agent.services.lesion_tracker import require_source, validate_evidence

    require_gate(dry_run, confirm)
    validate_evidence(evidence_type, status, scope)
    date = parse_datetime(examination_date, "examination-date")
    migrate()
    with session_scope() as session:
        lesion = require_lesion(session, lesion_id)
        require_source(session, source)
        if scope != "individual" or (
            laterality and lesion.details.get("laterality") not in (None, laterality)
        ):
            raise ValidationFailure(
                "Group description or wrong-side measurement cannot be assigned to one lesion"
            )
        if size <= 0 or not unit.strip() or not original_text.strip():
            raise ValidationFailure("Invalid measurement")
        data = dict(
            lesion_id=lesion_id,
            source_document_id=source,
            size=size,
            unit=unit,
            original_text=original_text,
            laterality=laterality,
            evidence_type=evidence_type,
            status=status,
            examination_date=examination_date,
        )
        if not dry_run:
            observation = add_measurement(
                session,
                lesion_id,
                source,
                size=size,
                unit=unit,
                original_text=original_text,
                laterality=laterality,
                evidence_type=evidence_type,
                status=status,
                scope=scope,
                examination_date=date,
            )
            data["id"] = observation.id
    emit(
        "lesions.add-measurement.preview" if dry_run else "lesions.add-measurement",
        data,
        json_output=json_output,
        requires_confirmation=dry_run,
    )


@app.command("history")
def history_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        data = formal_history(session, lesion_id)
    emit("lesions.history", data, json_output=json_output)
