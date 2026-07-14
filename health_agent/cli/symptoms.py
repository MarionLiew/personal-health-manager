from __future__ import annotations

from datetime import UTC, datetime

import typer
from sqlalchemy import select

from health_agent.cli.helpers import parse_datetime, require_gate
from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import SymptomEpisode, SymptomObservation
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure
from health_agent.rules.red_flags import assess_red_flags

app = typer.Typer(no_args_is_help=True)
STATUSES = {"active", "improving", "stable", "worsening", "resolved", "recurrent", "unknown"}


def _episode_row(item: SymptomEpisode) -> dict[str, object]:
    return {
        "id": item.id,
        "symptom_name": item.symptom_name,
        "normalized_symptom_name": item.normalized_symptom_name,
        "anatomical_region": item.anatomical_region,
        "anatomical_side": item.anatomical_side,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "ended_at": item.ended_at.isoformat() if item.ended_at else None,
        "status": item.status,
        "severity": item.severity,
        "severity_scale": item.severity_scale,
        "frequency": item.frequency,
        "duration_pattern": item.duration_pattern,
        "trigger": item.trigger,
        "relieving_factor": item.relieving_factor,
        "aggravating_factor": item.aggravating_factor,
        "associated_symptoms": item.associated_symptoms or [],
        "user_notes": item.user_notes,
        "source_type": item.source_type,
        "verified": item.verified,
    }


@app.command("add")
def add_command(
    name: str = typer.Option(..., "--name"),
    location: str | None = typer.Option(None, "--location"),
    side: str | None = typer.Option(None, "--side"),
    started: str | None = typer.Option(None, "--started"),
    severity: float | None = typer.Option(None, "--severity"),
    status: str = typer.Option("active", "--status"),
    notes: str | None = typer.Option(None, "--notes"),
    red_flags: str = typer.Option("", "--red-flags"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if status not in STATUSES:
        raise ValidationFailure("Invalid symptom status")
    if severity is not None and not 0 <= severity <= 10:
        raise ValidationFailure("Symptom severity must be between 0 and 10")
    started_at = parse_datetime(started, "started") or datetime.now(UTC)
    flags = assess_red_flags({value.strip() for value in red_flags.split(",") if value.strip()})
    data = {
        "symptom_name": name,
        "normalized_symptom_name": name.strip().lower(),
        "anatomical_region": location,
        "anatomical_side": side,
        "started_at": started_at.isoformat(),
        "severity": severity,
        "severity_scale": "0-10" if severity is not None else None,
        "status": status,
        "user_notes": notes,
        "source_type": "user_report",
        "red_flags": list(flags.matched),
        "red_flag_rule": "red-flags-v1" if flags.matched else None,
    }
    if dry_run:
        emit("symptoms.add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        entry = audit(
            session, "symptoms.add", patient_id="local-primary", entity_type="SymptomEpisode"
        )
        episode = SymptomEpisode(
            patient_id="local-primary",
            source_type="user_report",
            occurred_at=started_at,
            started_at=started_at,
            symptom_name=name,
            normalized_symptom_name=name.strip().lower(),
            anatomical_region=location,
            anatomical_side=side,
            severity=severity,
            severity_scale=data["severity_scale"],
            status=status,
            user_notes=notes,
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
            details={"red_flags": list(flags.matched)},
        )
        session.add(episode)
        session.flush()
        entry.entity_id = episode.id
        data["id"] = episode.id
    emit("symptoms.add", data, json_output=json_output, medical_action_level=flags.action_level)


def _get_episode(session, episode_id: str) -> SymptomEpisode:
    item = session.get(SymptomEpisode, episode_id)
    if item is None or not item.verified:
        raise ValidationFailure("Symptom episode not found")
    return item


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = [
            _episode_row(item)
            for item in session.scalars(
                select(SymptomEpisode).where(SymptomEpisode.verified.is_(True))
            ).all()
        ]
    emit("symptoms.list", {"episodes": rows}, json_output=json_output)


@app.command("active")
def active_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        items = session.scalars(
            select(SymptomEpisode)
            .where(SymptomEpisode.verified.is_(True))
            .where(SymptomEpisode.status != "resolved")
        ).all()
        rows = [_episode_row(item) for item in items]
    emit("symptoms.active", {"episodes": rows}, json_output=json_output)


@app.command("show")
def show_command(episode_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        item = _get_episode(session, episode_id)
        observations = session.scalars(
            select(SymptomObservation)
            .where(SymptomObservation.symptom_episode_id == episode_id)
            .order_by(SymptomObservation.observed_at)
        ).all()
        data = {
            **_episode_row(item),
            "observations": [
                {
                    "id": row.id,
                    "observed_at": row.observed_at.isoformat(),
                    "severity": row.severity,
                    "status": row.status,
                    "trigger": row.trigger,
                    "medication_or_action": row.medication_or_action,
                    "response": row.response,
                    "notes": row.notes,
                    "source_type": row.source_type,
                }
                for row in observations
            ],
        }
    emit("symptoms.show", data, json_output=json_output)


@app.command("timeline")
def timeline_command(
    location: str | None = typer.Option(None, "--location"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    migrate()
    with session_scope() as session:
        query = select(SymptomEpisode).where(SymptomEpisode.verified.is_(True))
        if location:
            query = query.where(SymptomEpisode.anatomical_region == location)
        episodes = session.scalars(query.order_by(SymptomEpisode.started_at)).all()
        rows = [_episode_row(item) for item in episodes]
    emit("symptoms.timeline", {"episodes": rows, "location": location}, json_output=json_output)


def _change(
    episode_id: str,
    status: str,
    observed: str | None,
    severity: float | None,
    notes: str | None,
    dry_run: bool,
    confirm: bool,
    action: str,
    json_output: bool,
) -> None:
    require_gate(dry_run, confirm)
    if status not in STATUSES:
        raise ValidationFailure("Invalid symptom status")
    if severity is not None and not 0 <= severity <= 10:
        raise ValidationFailure("Symptom severity must be between 0 and 10")
    observed_at = parse_datetime(observed, "observed") or datetime.now(UTC)
    data = {
        "episode_id": episode_id,
        "status": status,
        "severity": severity,
        "observed_at": observed_at.isoformat(),
        "notes": notes,
    }
    if dry_run:
        emit(f"{action}.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        item = _get_episode(session, episode_id)
        previous = {
            "status": item.status,
            "severity": item.severity,
            "ended_at": item.ended_at.isoformat() if item.ended_at else None,
        }
        entry = audit(
            session,
            action,
            patient_id=item.patient_id,
            entity_type="SymptomEpisode",
            entity_id=item.id,
            metadata={"previous": previous},
        )
        item.status = status
        item.severity = severity if severity is not None else item.severity
        item.ended_at = observed_at if status == "resolved" else None
        session.add(
            SymptomObservation(
                symptom_episode_id=item.id,
                observed_at=observed_at,
                severity=item.severity,
                status=status,
                notes=notes,
                source_type="user_report",
                verified=True,
                audit_id=entry.id,
            )
        )
    emit(action, data, json_output=json_output)


@app.command("update")
def update_command(
    episode_id: str,
    status: str = typer.Option(..., "--status"),
    observed: str | None = typer.Option(None, "--observed"),
    severity: float | None = typer.Option(None, "--severity"),
    notes: str | None = typer.Option(None, "--notes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _change(
        episode_id,
        status,
        observed,
        severity,
        notes,
        dry_run,
        confirm,
        "symptoms.update",
        json_output,
    )


@app.command("resolve")
def resolve_command(
    episode_id: str,
    date: str = typer.Option(..., "--date"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _change(
        episode_id, "resolved", date, None, None, dry_run, confirm, "symptoms.resolve", json_output
    )


@app.command("reopen")
def reopen_command(
    episode_id: str,
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _change(
        episode_id, "recurrent", None, None, None, dry_run, confirm, "symptoms.reopen", json_output
    )
