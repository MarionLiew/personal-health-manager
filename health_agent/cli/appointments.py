from __future__ import annotations

from datetime import UTC, datetime

import typer
from sqlalchemy import select

from health_agent.cli.helpers import parse_datetime, require_gate
from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import Appointment
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure

app = typer.Typer(no_args_is_help=True)


def row(item: Appointment) -> dict[str, object]:
    return {
        "id": item.id,
        "department": item.department,
        "clinician_name": item.clinician_name,
        "institution": item.institution,
        "scheduled_start": item.scheduled_start.isoformat() if item.scheduled_start else None,
        "scheduled_end": item.scheduled_end.isoformat() if item.scheduled_end else None,
        "purpose": item.purpose,
        "related_followup_ids": item.related_followup_ids or [],
        "status": item.status,
        "preparation_notes": item.preparation_notes,
        "outcome_notes": item.outcome_notes,
        "source_type": item.source_type,
    }


@app.command("add")
def add_command(
    department: str = typer.Option(..., "--department"),
    start: str = typer.Option(..., "--start"),
    end: str | None = typer.Option(None, "--end"),
    clinician: str | None = typer.Option(None, "--clinician"),
    institution: str | None = typer.Option(None, "--institution"),
    purpose: str | None = typer.Option(None, "--purpose"),
    followup_ids: str = typer.Option("", "--followup-ids"),
    preparation: str | None = typer.Option(None, "--preparation"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    start_at = parse_datetime(start, "start")
    end_at = parse_datetime(end, "end")
    data = {
        "department": department,
        "scheduled_start": start_at.isoformat() if start_at else None,
        "scheduled_end": end_at.isoformat() if end_at else None,
        "clinician_name": clinician,
        "institution": institution,
        "purpose": purpose,
        "related_followup_ids": [
            value.strip() for value in followup_ids.split(",") if value.strip()
        ],
        "preparation_notes": preparation,
        "source_type": "user_report",
    }
    if dry_run:
        emit("appointments.add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        entry = audit(
            session, "appointments.add", patient_id="local-primary", entity_type="Appointment"
        )
        item = Appointment(
            patient_id="local-primary",
            source_type="user_report",
            occurred_at=start_at,
            department=department,
            clinician_name=clinician,
            institution=institution,
            scheduled_start=start_at,
            scheduled_end=end_at,
            purpose=purpose,
            related_followup_ids=data["related_followup_ids"],
            status="scheduled",
            preparation_notes=preparation,
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
        )
        session.add(item)
        session.flush()
        entry.entity_id = item.id
        data["id"] = item.id
    emit("appointments.add", data, json_output=json_output)


def _items(session):
    return session.scalars(select(Appointment).where(Appointment.verified.is_(True))).all()


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = [row(item) for item in _items(session)]
    emit("appointments.list", {"appointments": rows}, json_output=json_output)


@app.command("upcoming")
def upcoming_command(json_output: bool = typer.Option(False, "--json")) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    migrate()
    with session_scope() as session:
        rows = [
            row(item)
            for item in _items(session)
            if item.status == "scheduled" and item.scheduled_start and item.scheduled_start >= now
        ]
    emit("appointments.upcoming", {"appointments": rows}, json_output=json_output)


@app.command("show")
def show_command(appointment_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        item = session.get(Appointment, appointment_id)
        if item is None:
            raise ValidationFailure("Appointment not found")
        data = row(item)
    emit("appointments.show", data, json_output=json_output)


def _status(appointment_id: str, status: str, action: str, json_output: bool) -> None:
    migrate()
    with session_scope() as session:
        item = session.get(Appointment, appointment_id)
        if item is None:
            raise ValidationFailure("Appointment not found")
        previous = item.status
        audit(
            session,
            action,
            patient_id=item.patient_id,
            entity_type="Appointment",
            entity_id=item.id,
            metadata={"previous_status": previous},
        )
        item.status = status
    emit(action, {"appointment_id": appointment_id, "status": status}, json_output=json_output)


@app.command("complete")
def complete_command(
    appointment_id: str, json_output: bool = typer.Option(False, "--json")
) -> None:
    _status(appointment_id, "completed", "appointments.complete", json_output)


@app.command("cancel")
def cancel_command(appointment_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    _status(appointment_id, "cancelled", "appointments.cancel", json_output)
