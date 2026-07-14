from __future__ import annotations

import calendar
import re
from datetime import UTC, datetime, timedelta

import typer
from sqlalchemy import select

from health_agent.cli.helpers import parse_datetime, require_gate
from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import FollowUpEvent, FollowUpPlan
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure

app = typer.Typer(no_args_is_help=True)
CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
NUMBER = r"(?:\d+|十二|十一|十|[一二两三四五六七八九])"


def _amount(value: str) -> int:
    return int(value) if value.isdigit() else CHINESE_NUMBERS[value]


def add_months(value: datetime, months: int) -> datetime:
    month = value.month - 1 + months
    year, month = value.year + month // 12, month % 12 + 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


def parse_due(
    value: str | None, base: datetime
) -> tuple[datetime | None, datetime | None, datetime | None]:
    if not value:
        return None, None, None
    explicit = parse_datetime(value, "due") if re.match(r"^\d{4}-\d{2}-\d{2}", value) else None
    if explicit:
        return explicit, explicit, explicit
    range_match = re.search(rf"({NUMBER})\s*(?:至|到|[-~])\s*({NUMBER})\s*个?月", value)
    if range_match:
        return (
            None,
            add_months(base, _amount(range_match[1])),
            add_months(base, _amount(range_match[2])),
        )
    month_match = re.search(rf"({NUMBER})\s*个?月后", value)
    if month_match:
        exact = add_months(base, _amount(month_match[1]))
        return exact, exact, exact
    year_match = re.search(r"一?年后", value)
    if year_match:
        exact = add_months(base, 12)
        return exact, exact, exact
    week_match = re.search(rf"({NUMBER})\s*周后", value)
    if week_match:
        exact = base + timedelta(weeks=_amount(week_match[1]))
        return exact, exact, exact
    return None, None, None


def effective_status(item: FollowUpPlan, now: datetime | None = None) -> str:
    if item.status not in {"pending", "upcoming", "due", "overdue"}:
        return item.status
    now = (now or datetime.now(UTC)).replace(tzinfo=None)
    start = item.due_date_start or item.due_date
    end = item.due_date_end or item.due_date
    if end and end < now:
        return "overdue"
    if start and start <= now <= (end or start):
        return "due"
    if start and start <= now + timedelta(days=30):
        return "upcoming"
    return "pending"


def row(item: FollowUpPlan) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "category": item.category,
        "related_record_type": item.related_record_type,
        "related_record_id": item.related_record_id,
        "reason": item.reason,
        "recommended_by": item.recommended_by,
        "recommendation_source_type": item.recommendation_source_type,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "due_date_start": item.due_date_start.isoformat() if item.due_date_start else None,
        "due_date_end": item.due_date_end.isoformat() if item.due_date_end else None,
        "original_due_text": item.details.get("original_due_text"),
        "priority": item.priority,
        "status": item.status,
        "effective_status": effective_status(item),
        "department": item.department,
        "requested_test": item.requested_test,
        "completion_record_id": item.completion_record_id,
        "postpone_reason": item.postpone_reason,
        "notes": item.notes,
        "source_document_id": item.source_document_id,
        "verified": item.verified,
    }


@app.command("add")
def add_command(
    title: str = typer.Option(..., "--title"),
    due: str | None = typer.Option(None, "--due"),
    base_date: str | None = typer.Option(None, "--base-date"),
    category: str = typer.Option("review", "--category"),
    reason: str | None = typer.Option(None, "--reason"),
    department: str | None = typer.Option(None, "--department"),
    requested_test: str | None = typer.Option(None, "--test"),
    recommended_by: str | None = typer.Option(None, "--recommended-by"),
    source_type: str = typer.Option("user_report", "--source-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    base = parse_datetime(base_date, "base-date") or datetime.now(UTC)
    exact, start, end = parse_due(due, base)
    data = {
        "title": title,
        "category": category,
        "reason": reason,
        "department": department,
        "requested_test": requested_test,
        "recommended_by": recommended_by,
        "source_type": source_type,
        "due_date": exact.isoformat() if exact else None,
        "due_date_start": start.isoformat() if start else None,
        "due_date_end": end.isoformat() if end else None,
        "original_due_text": due,
        "date_uncertain": bool(due and not start),
    }
    if dry_run:
        emit("followup.add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        entry = audit(
            session, "followup.add", patient_id="local-primary", entity_type="FollowUpPlan"
        )
        plan = FollowUpPlan(
            patient_id="local-primary",
            source_type=source_type,
            occurred_at=base,
            title=title,
            category=category,
            reason=reason,
            recommended_by=recommended_by,
            recommendation_source_type=source_type,
            due_date=exact,
            due_date_start=start,
            due_date_end=end,
            priority="normal",
            status="pending",
            department=department,
            requested_test=requested_test,
            notes=None,
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
            details={"original_due_text": due},
        )
        session.add(plan)
        session.flush()
        entry.entity_id = plan.id
        data["id"] = plan.id
    emit("followup.add", data, json_output=json_output)


def _plans(session) -> list[FollowUpPlan]:
    return session.scalars(select(FollowUpPlan).where(FollowUpPlan.verified.is_(True))).all()


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = [row(item) for item in _plans(session)]
    emit("followup.list", {"plans": rows}, json_output=json_output)


def _filtered(action: str, predicate, json_output: bool) -> None:
    migrate()
    with session_scope() as session:
        rows = [row(item) for item in _plans(session) if predicate(item)]
    emit(action, {"plans": rows}, json_output=json_output)


@app.command("pending")
def pending_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _filtered(
        "followup.pending",
        lambda item: (
            effective_status(item) in {"pending", "upcoming", "due", "overdue", "postponed"}
        ),
        json_output,
    )


@app.command("upcoming")
def upcoming_command(
    days: int = typer.Option(30, "--days"), json_output: bool = typer.Option(False, "--json")
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now + timedelta(days=days)
    _filtered(
        "followup.upcoming",
        lambda item: bool(
            (item.due_date_start or item.due_date)
            and now <= (item.due_date_start or item.due_date) <= cutoff
        ),
        json_output,
    )


@app.command("overdue")
def overdue_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _filtered("followup.overdue", lambda item: effective_status(item) == "overdue", json_output)


@app.command("show")
def show_command(followup_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        item = session.get(FollowUpPlan, followup_id)
        if item is None:
            raise ValidationFailure("Follow-up plan not found")
        data = row(item)
    emit("followup.show", data, json_output=json_output)


def _transition(
    followup_id: str,
    new_status: str,
    action: str,
    reason: str | None,
    date: str | None,
    record_id: str | None,
    dry_run: bool,
    confirm: bool,
    json_output: bool,
) -> None:
    require_gate(dry_run, confirm)
    new_date = parse_datetime(date, "date")
    data = {
        "followup_id": followup_id,
        "status": new_status,
        "reason": reason,
        "date": new_date.isoformat() if new_date else None,
        "record_id": record_id,
    }
    if dry_run:
        emit(f"{action}.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        item = session.get(FollowUpPlan, followup_id)
        if item is None or not item.verified:
            raise ValidationFailure("Follow-up plan not found")
        previous = row(item)
        entry = audit(
            session,
            action,
            patient_id=item.patient_id,
            entity_type="FollowUpPlan",
            entity_id=item.id,
            metadata={"previous": previous},
        )
        item.status = new_status
        item.completion_record_id = (
            record_id if new_status == "completed" else item.completion_record_id
        )
        if new_status == "postponed":
            item.due_date = new_date
            item.due_date_start = new_date
            item.due_date_end = new_date
            item.postpone_reason = reason
        session.add(
            FollowUpEvent(
                followup_id=item.id,
                event_type=new_status,
                reason=reason,
                related_record_id=record_id,
                previous_state=previous,
                audit_id=entry.id,
            )
        )
    emit(action, data, json_output=json_output)


@app.command("complete")
def complete_command(
    followup_id: str,
    record_id: str = typer.Option(..., "--record-id"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _transition(
        followup_id,
        "completed",
        "followup.complete",
        None,
        None,
        record_id,
        dry_run,
        confirm,
        json_output,
    )


@app.command("postpone")
def postpone_command(
    followup_id: str,
    date: str = typer.Option(..., "--date"),
    reason: str = typer.Option(..., "--reason"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _transition(
        followup_id,
        "postponed",
        "followup.postpone",
        reason,
        date,
        None,
        dry_run,
        confirm,
        json_output,
    )


@app.command("cancel")
def cancel_command(
    followup_id: str,
    reason: str = typer.Option(..., "--reason"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _transition(
        followup_id,
        "cancelled",
        "followup.cancel",
        reason,
        None,
        None,
        dry_run,
        confirm,
        json_output,
    )
