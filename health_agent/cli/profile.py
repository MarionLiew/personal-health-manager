from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from sqlalchemy import select

from health_agent.cli.helpers import parse_datetime, require_gate
from health_agent.cli.main import emit
from health_agent.config import load_settings
from health_agent.constants import SourceType
from health_agent.database.migrations import migrate
from health_agent.database.models import (
    HealthTimelineEvent,
    HPVLesion,
    ImmuneContext,
    Lesion,
    LesionImage,
    PersonalCondition,
    RiskFactorProfile,
    ScarLesion,
    TreatmentEvent,
)
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.errors import ValidationFailure
from health_agent.importers.base import hash_file
from health_agent.safety.privacy import require_allowed_import_path
from health_agent.services import personal_profile

app = typer.Typer(no_args_is_help=True)

CONDITION_CATEGORIES = {
    "scar_disorder",
    "viral_infection",
    "dermatology",
    "mucosal_condition",
    "chronic_pain",
    "inflammatory_condition",
    "respiratory",
    "cardiovascular",
    "metabolic",
    "other",
}
CONDITION_STATUSES = {"active", "stable", "improving", "recurrent", "resolved", "unknown"}
EVIDENCE_TYPES = {item.value for item in SourceType}
HPV_RELATIONS = {"confirmed", "suspected", "uncertain", "not_supported"}
RECURRENCE_STATES = {"yes", "no", "observing", "unknown"}
RISK_GROUPS = {"modifiable", "non_modifiable", "condition_related"}
IMAGE_TYPES = {"scar", "hpv", "skin", "mucosal"}
FORBIDDEN_PROFILE_CLAIMS = {"免疫力评分", "炎症评分", "个人癌症概率", "HPV一定会癌变"}


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _json(value: str | None, expected: type, field: str) -> Any:
    if not value:
        return expected()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationFailure(f"Invalid JSON for {field}") from exc
    if not isinstance(parsed, expected):
        raise ValidationFailure(f"{field} must be a JSON {expected.__name__}")
    return parsed


def _source(value: str) -> str:
    if value not in EVIDENCE_TYPES:
        raise ValidationFailure("Invalid evidence source_type")
    return value


def _safe_profile_data(data: dict[str, Any]) -> None:
    serialized = json.dumps(data, ensure_ascii=False)
    matched = sorted(term for term in FORBIDDEN_PROFILE_CLAIMS if term in serialized)
    if matched:
        raise ValidationFailure("Profile data contains a prohibited diagnostic or score claim")


def _condition(session, condition_id: str) -> PersonalCondition:
    item = session.get(PersonalCondition, condition_id)
    if item is None or not item.verified:
        raise ValidationFailure("Personal condition not found")
    return item


def _timeline_event(
    session,
    *,
    condition_id: str | None,
    event_type: str,
    event_date: datetime,
    title: str,
    description: str | None,
    related_record_type: str,
    related_record_id: str,
    source_type: str,
    audit_id: str,
) -> HealthTimelineEvent:
    item = HealthTimelineEvent(
        patient_id="local-primary",
        source_type=source_type,
        occurred_at=event_date,
        event_date=event_date,
        condition_id=condition_id,
        event_type=event_type,
        title=title,
        description=description,
        related_record_type=related_record_type,
        related_record_id=related_record_id,
        verified=True,
        verification_status="user_confirmed",
        audit_id=audit_id,
    )
    session.add(item)
    return item


@app.command("condition-add")
def condition_add(
    name: str = typer.Option(..., "--name"),
    category: str = typer.Option(..., "--category"),
    body_region: str | None = typer.Option(None, "--body-region"),
    first_noted: str | None = typer.Option(None, "--first-noted"),
    status: str = typer.Option("unknown", "--status"),
    severity: str | None = typer.Option(None, "--severity"),
    recurrence: str | None = typer.Option(None, "--recurrence-pattern"),
    treatment_history_json: str | None = typer.Option(None, "--treatment-history-json"),
    related_records_json: str | None = typer.Option(None, "--related-records-json"),
    monitoring_json: str | None = typer.Option(None, "--monitoring-json"),
    notes: str | None = typer.Option(None, "--notes"),
    source_type: str = typer.Option("user_report", "--source-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if category not in CONDITION_CATEGORIES:
        raise ValidationFailure("Invalid condition category")
    if status not in CONDITION_STATUSES:
        raise ValidationFailure("Invalid condition status")
    source_type = _source(source_type)
    first = parse_datetime(first_noted, "first-noted")
    monitoring_plan = _json(monitoring_json, dict, "monitoring-json")
    treatment_history = _json(treatment_history_json, list, "treatment-history-json")
    related_records = _json(related_records_json, list, "related-records-json")
    data = {
        "condition_name": name,
        "normalized_name": name.strip().lower(),
        "category": category,
        "body_region": body_region,
        "first_noted_date": first.isoformat() if first else None,
        "current_status": status,
        "severity": severity,
        "recurrence_pattern": recurrence,
        "treatment_history": treatment_history,
        "related_records": related_records,
        "monitoring_plan": monitoring_plan,
        "notes": notes,
        "source_type": source_type,
    }
    _safe_profile_data(data)
    if dry_run:
        emit(
            "profile.condition-add.preview",
            data,
            json_output=json_output,
            requires_confirmation=True,
        )
        return
    migrate()
    with session_scope() as session:
        existing = session.scalar(
            select(PersonalCondition)
            .where(PersonalCondition.verified.is_(True))
            .where(PersonalCondition.normalized_name == data["normalized_name"])
            .where(PersonalCondition.body_region == body_region)
        )
        if existing:
            data.update({"id": existing.id, "duplicate": True})
        else:
            entry = audit(
                session,
                "profile.condition-add",
                patient_id="local-primary",
                entity_type="PersonalCondition",
            )
            item = PersonalCondition(
                patient_id="local-primary",
                source_type=source_type,
                occurred_at=first,
                condition_name=name,
                normalized_name=str(data["normalized_name"]),
                category=category,
                body_region=body_region,
                first_noted_date=first,
                current_status=status,
                severity=severity,
                recurrence_pattern=recurrence,
                treatment_history=treatment_history,
                related_records=related_records,
                monitoring_plan=monitoring_plan,
                notes=notes,
                verified=True,
                verification_status="user_confirmed",
                audit_id=entry.id,
            )
            session.add(item)
            session.flush()
            entry.entity_id = item.id
            _timeline_event(
                session,
                condition_id=item.id,
                event_type="condition_noted",
                event_date=first or datetime.now(UTC),
                title=f"长期问题记录：{name}",
                description=notes,
                related_record_type="PersonalCondition",
                related_record_id=item.id,
                source_type=source_type,
                audit_id=entry.id,
            )
            data.update({"id": item.id, "duplicate": False})
    emit("profile.condition-add", data, json_output=json_output)


@app.command("condition-update")
def condition_update(
    condition_id: str,
    status: str = typer.Option(..., "--status"),
    severity: str | None = typer.Option(None, "--severity"),
    recurrence: str | None = typer.Option(None, "--recurrence-pattern"),
    monitoring_json: str | None = typer.Option(None, "--monitoring-json"),
    notes: str | None = typer.Option(None, "--notes"),
    date: str | None = typer.Option(None, "--date"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if status not in CONDITION_STATUSES:
        raise ValidationFailure("Invalid condition status")
    changed_at = parse_datetime(date, "date") or datetime.now(UTC)
    monitoring_plan = _json(monitoring_json, dict, "monitoring-json") if monitoring_json else None
    data = {
        "condition_id": condition_id,
        "current_status": status,
        "severity": severity,
        "recurrence_pattern": recurrence,
        "monitoring_plan": monitoring_plan,
        "notes": notes,
        "date": changed_at.isoformat(),
    }
    _safe_profile_data(data)
    if dry_run:
        emit(
            "profile.condition-update.preview",
            data,
            json_output=json_output,
            requires_confirmation=True,
        )
        return
    migrate()
    with session_scope() as session:
        item = _condition(session, condition_id)
        previous = personal_profile.condition_row(item)
        entry = audit(
            session,
            "profile.condition-update",
            patient_id=item.patient_id,
            entity_type="PersonalCondition",
            entity_id=item.id,
            metadata={"previous": previous},
        )
        item.current_status = status
        item.severity = severity if severity is not None else item.severity
        item.recurrence_pattern = recurrence if recurrence is not None else item.recurrence_pattern
        item.monitoring_plan = (
            monitoring_plan if monitoring_plan is not None else item.monitoring_plan
        )
        item.notes = notes if notes is not None else item.notes
        _timeline_event(
            session,
            condition_id=item.id,
            event_type="condition_status_change",
            event_date=changed_at,
            title=f"{item.condition_name}状态更新为{status}",
            description=notes,
            related_record_type="PersonalCondition",
            related_record_id=item.id,
            source_type="user_report",
            audit_id=entry.id,
        )
    emit("profile.condition-update", data, json_output=json_output)


@app.command("scar-add")
def scar_add(
    condition_id: str = typer.Option(..., "--condition-id"),
    location: str = typer.Option(..., "--location"),
    scar_type: str = typer.Option("uncertain", "--scar-type"),
    onset: str | None = typer.Option(None, "--onset"),
    trigger_event: str | None = typer.Option(None, "--trigger-event"),
    previous_treatment: str = typer.Option("", "--previous-treatment"),
    treatment_date: str | None = typer.Option(None, "--treatment-date"),
    recurrence: bool | None = typer.Option(None, "--recurrence/--no-recurrence"),
    size_change: str | None = typer.Option(None, "--size-change"),
    color_change: str | None = typer.Option(None, "--color-change"),
    hardness_change: str | None = typer.Option(None, "--hardness-change"),
    symptoms: str = typer.Option("", "--symptoms"),
    dermatologist_assessment: str | None = typer.Option(None, "--dermatologist-assessment"),
    source_type: str = typer.Option("user_report", "--source-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    source_type = _source(source_type)
    onset_at = parse_datetime(onset, "onset")
    treated_at = parse_datetime(treatment_date, "treatment-date")
    data = {
        "condition_id": condition_id,
        "location": location,
        "scar_type": scar_type,
        "onset_date": onset_at.isoformat() if onset_at else None,
        "trigger_event": trigger_event,
        "previous_treatment": _csv(previous_treatment),
        "treatment_date": treated_at.isoformat() if treated_at else None,
        "recurrence_after_treatment": recurrence,
        "size_change": size_change,
        "color_change": color_change,
        "hardness_change": hardness_change,
        "symptoms": _csv(symptoms),
        "dermatologist_assessment": dermatologist_assessment,
        "source_type": source_type,
    }
    _safe_profile_data(data)
    if dry_run:
        emit("profile.scar-add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        _condition(session, condition_id)
        entry = audit(
            session, "profile.scar-add", patient_id="local-primary", entity_type="ScarLesion"
        )
        item = ScarLesion(
            patient_id="local-primary",
            source_type=source_type,
            occurred_at=onset_at,
            condition_id=condition_id,
            location=location,
            scar_type=scar_type,
            onset_date=onset_at,
            trigger_event=trigger_event,
            previous_treatment=data["previous_treatment"],
            treatment_date=treated_at,
            recurrence_after_treatment=recurrence,
            size_change=size_change,
            color_change=color_change,
            hardness_change=hardness_change,
            symptoms=data["symptoms"],
            dermatologist_assessment=dermatologist_assessment,
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
        )
        session.add(item)
        session.flush()
        entry.entity_id = item.id
        _timeline_event(
            session,
            condition_id=condition_id,
            event_type="scar_observation",
            event_date=onset_at or datetime.now(UTC),
            title=f"瘢痕记录：{location}",
            description=f"类型：{scar_type}",
            related_record_type="ScarLesion",
            related_record_id=item.id,
            source_type=source_type,
            audit_id=entry.id,
        )
        data["id"] = item.id
    emit(
        "profile.scar-add",
        data,
        json_output=json_output,
        uncertainties=[
            "Scar type is recorded as reported and is not a diagnosis or cancer-risk inference."
        ],
    )


@app.command("hpv-add")
def hpv_add(
    condition_id: str = typer.Option(..., "--condition-id"),
    location: str = typer.Option(..., "--location"),
    lesion_type: str = typer.Option("uncertain", "--lesion-type"),
    first_found: str | None = typer.Option(None, "--first-found"),
    diagnosis_method: str | None = typer.Option(None, "--diagnosis-method"),
    hpv_related: str = typer.Option("uncertain", "--hpv-related"),
    laser_dates: str = typer.Option("", "--laser-dates"),
    recurrence: str = typer.Option("unknown", "--recurrence"),
    pathology_done: bool | None = typer.Option(None, "--pathology-done/--no-pathology"),
    dermatologist_opinion: str | None = typer.Option(None, "--dermatologist-opinion"),
    photos_available: bool = typer.Option(False, "--photos-available"),
    status: str = typer.Option("unknown", "--status"),
    source_type: str = typer.Option("user_report", "--source-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if hpv_related not in HPV_RELATIONS:
        raise ValidationFailure("Invalid HPV relationship status")
    if recurrence not in RECURRENCE_STATES:
        raise ValidationFailure("Invalid recurrence status")
    if status not in CONDITION_STATUSES:
        raise ValidationFailure("Invalid lesion status")
    source_type = _source(source_type)
    found_at = parse_datetime(first_found, "first-found")
    dates = _csv(laser_dates)
    for value in dates:
        parse_datetime(value, "laser-dates")
    data = {
        "condition_id": condition_id,
        "location": location,
        "lesion_type": lesion_type,
        "first_found": found_at.isoformat() if found_at else None,
        "diagnosis_method": diagnosis_method,
        "hpv_related": hpv_related,
        "laser_dates": dates,
        "recurrence": recurrence,
        "pathology_done": pathology_done,
        "dermatologist_opinion": dermatologist_opinion,
        "photos_available": photos_available,
        "current_status": status,
        "source_type": source_type,
    }
    _safe_profile_data(data)
    if dry_run:
        emit("profile.hpv-add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        _condition(session, condition_id)
        entry = audit(
            session, "profile.hpv-add", patient_id="local-primary", entity_type="HPVLesion"
        )
        item = HPVLesion(
            patient_id="local-primary",
            source_type=source_type,
            occurred_at=found_at,
            condition_id=condition_id,
            location=location,
            lesion_type=lesion_type,
            first_found=found_at,
            diagnosis_method=diagnosis_method,
            hpv_related=hpv_related,
            laser_dates=dates,
            recurrence=recurrence,
            pathology_done=pathology_done,
            dermatologist_opinion=dermatologist_opinion,
            photos_available=photos_available,
            current_status=status,
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
        )
        session.add(item)
        session.flush()
        entry.entity_id = item.id
        _timeline_event(
            session,
            condition_id=condition_id,
            event_type="skin_lesion_observation",
            event_date=found_at or datetime.now(UTC),
            title=f"皮损记录：{location}",
            description=f"HPV关系：{hpv_related}",
            related_record_type="HPVLesion",
            related_record_id=item.id,
            source_type=source_type,
            audit_id=entry.id,
        )
        data["id"] = item.id
    emit(
        "profile.hpv-add",
        data,
        json_output=json_output,
        uncertainties=[
            "HPV relationship and lesion type remain as recorded; no malignant "
            "transformation is inferred."
        ],
    )


@app.command("treatment-add")
def treatment_add(
    condition_id: str = typer.Option(..., "--condition-id"),
    treatment_type: str = typer.Option(..., "--type"),
    date: str = typer.Option(..., "--date"),
    target_type: str | None = typer.Option(None, "--target-type"),
    target_id: str | None = typer.Option(None, "--target-id"),
    institution: str | None = typer.Option(None, "--institution"),
    response: str | None = typer.Option(None, "--response"),
    recurrence_time: str | None = typer.Option(None, "--recurrence-time"),
    source_type: str = typer.Option("user_report", "--source-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    source_type = _source(source_type)
    treated_at = parse_datetime(date, "date")
    if treated_at is None:
        raise ValidationFailure("Treatment date is required")
    recurrence_at = parse_datetime(recurrence_time, "recurrence-time")
    data = {
        "condition_id": condition_id,
        "target_type": target_type,
        "target_id": target_id,
        "treatment_type": treatment_type,
        "date": treated_at.isoformat(),
        "institution": institution,
        "response": response,
        "recurrence_time": recurrence_at.isoformat() if recurrence_at else None,
        "source_type": source_type,
    }
    _safe_profile_data(data)
    if dry_run:
        emit(
            "profile.treatment-add.preview",
            data,
            json_output=json_output,
            requires_confirmation=True,
        )
        return
    migrate()
    with session_scope() as session:
        condition = _condition(session, condition_id)
        entry = audit(
            session,
            "profile.treatment-add",
            patient_id="local-primary",
            entity_type="TreatmentEvent",
        )
        item = TreatmentEvent(
            patient_id="local-primary",
            source_type=source_type,
            occurred_at=treated_at,
            condition_id=condition_id,
            target_type=target_type,
            target_id=target_id,
            treatment_type=treatment_type,
            treatment_date=treated_at,
            institution=institution,
            response=response,
            recurrence_time=recurrence_at,
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
        )
        session.add(item)
        session.flush()
        entry.entity_id = item.id
        condition.treatment_history = [
            *(condition.treatment_history or []),
            {"treatment_event_id": item.id, "type": treatment_type, "date": treated_at.isoformat()},
        ]
        if target_type == "hpv" and target_id:
            lesion = session.get(HPVLesion, target_id)
            if lesion is None or lesion.condition_id != condition_id:
                raise ValidationFailure("HPV treatment target does not belong to the condition")
            lesion.treatment_history = [
                *(lesion.treatment_history or []),
                {
                    "treatment_event_id": item.id,
                    "type": treatment_type,
                    "date": treated_at.isoformat(),
                },
            ]
            if "激光" in treatment_type or "laser" in treatment_type.lower():
                lesion.laser_dates = [*(lesion.laser_dates or []), treated_at.date().isoformat()]
        if target_type == "scar" and target_id:
            lesion = session.get(ScarLesion, target_id)
            if lesion is None or lesion.condition_id != condition_id:
                raise ValidationFailure("Scar treatment target does not belong to the condition")
            lesion.previous_treatment = [*(lesion.previous_treatment or []), treatment_type]
            lesion.treatment_date = treated_at
        _timeline_event(
            session,
            condition_id=condition_id,
            event_type="treatment",
            event_date=treated_at,
            title=f"治疗：{treatment_type}",
            description=response,
            related_record_type="TreatmentEvent",
            related_record_id=item.id,
            source_type=source_type,
            audit_id=entry.id,
        )
        data["id"] = item.id
    emit("profile.treatment-add", data, json_output=json_output)


@app.command("image-add")
def image_add(
    file: Path,
    condition_id: str = typer.Option(..., "--condition-id"),
    lesion_type: str = typer.Option(..., "--lesion-type"),
    lesion_id: str = typer.Option(..., "--lesion-id"),
    taken_date: str = typer.Option(..., "--taken-date"),
    body_location: str = typer.Option(..., "--body-location"),
    notes: str | None = typer.Option(None, "--notes"),
    comparison_group: str | None = typer.Option(None, "--comparison-group"),
    size_description: str | None = typer.Option(None, "--size-description"),
    count_description: str | None = typer.Option(None, "--count-description"),
    appearance_description: str | None = typer.Option(None, "--appearance-description"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if lesion_type not in IMAGE_TYPES:
        raise ValidationFailure("Invalid lesion image type")
    settings = load_settings()
    source = require_allowed_import_path(file, settings)
    if not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".heic"}:
        raise ValidationFailure("Lesion image must be JPEG, PNG, or HEIC")
    taken_at = parse_datetime(taken_date, "taken-date")
    if taken_at is None:
        raise ValidationFailure("Taken date is required")
    image_hash = hash_file(source)
    data = {
        "condition_id": condition_id,
        "lesion_type": lesion_type,
        "lesion_id": lesion_id,
        "taken_date": taken_at.isoformat(),
        "body_location": body_location,
        "image_hash": image_hash,
        "notes": notes,
        "comparison_group": comparison_group,
        "observations": {
            "size": size_description,
            "count": count_description,
            "appearance": appearance_description,
        },
        "allowed_comparison": ["size_change", "count_change", "appearance_change"],
        "diagnostic_interpretation": None,
    }
    _safe_profile_data(data)
    if dry_run:
        emit("profile.image-add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        _condition(session, condition_id)
        if lesion_type == "hpv":
            target = session.get(HPVLesion, lesion_id)
            if target is None or target.condition_id != condition_id:
                raise ValidationFailure("HPV image target does not belong to the condition")
        elif lesion_type == "scar":
            target = session.get(ScarLesion, lesion_id)
            if target is None or target.condition_id != condition_id:
                raise ValidationFailure("Scar image target does not belong to the condition")
        else:
            target = session.get(Lesion, lesion_id)
            if target is None or not target.verified:
                raise ValidationFailure("Lesion image target was not found")
        existing = session.scalar(select(LesionImage).where(LesionImage.image_hash == image_hash))
        if existing:
            entry = audit(
                session,
                "profile.image-add.duplicate",
                patient_id="local-primary",
                entity_type="LesionImage",
                entity_id=existing.id,
                file_hash=image_hash,
            )
            data.update({"id": existing.id, "duplicate": True, "audit_id": entry.id})
        else:
            destination_dir = settings.data_root / "reports" / "profile-images"
            destination_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = destination_dir / f"{image_hash}{source.suffix.lower()}"
            shutil.copy2(source, destination)
            destination.chmod(0o400)
            entry = audit(
                session,
                "profile.image-add",
                patient_id="local-primary",
                entity_type="LesionImage",
                file_hash=image_hash,
            )
            item = LesionImage(
                patient_id="local-primary",
                source_type="user_report",
                occurred_at=taken_at,
                condition_id=condition_id,
                lesion_type=lesion_type,
                lesion_id=lesion_id,
                taken_date=taken_at,
                body_location=body_location,
                image_hash=image_hash,
                local_path=str(destination),
                notes=notes,
                comparison_group=comparison_group,
                details=data["observations"],
                verified=True,
                verification_status="user_confirmed",
                audit_id=entry.id,
            )
            session.add(item)
            session.flush()
            entry.entity_id = item.id
            if isinstance(target, HPVLesion):
                target.photos_available = True
            _timeline_event(
                session,
                condition_id=condition_id,
                event_type="lesion_photo",
                event_date=taken_at,
                title=f"皮损照片：{body_location}",
                description=notes,
                related_record_type="LesionImage",
                related_record_id=item.id,
                source_type="user_report",
                audit_id=entry.id,
            )
            data.update({"id": item.id, "duplicate": False})
    emit(
        "profile.image-add",
        data,
        json_output=json_output,
        uncertainties=[
            "Images are stored for longitudinal visual comparison only and are not diagnosed."
        ],
    )


@app.command("immune-add")
def immune_add(
    infections_json: str | None = typer.Option(None, "--infections-json"),
    vaccinations_json: str | None = typer.Option(None, "--vaccinations-json"),
    factors_json: str | None = typer.Option(None, "--factors-json"),
    laboratory_ids: str = typer.Option("", "--laboratory-ids"),
    observations: str = typer.Option("", "--observations"),
    monitoring_items: str = typer.Option("", "--monitoring-items"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    data = {
        "infections": _json(infections_json, list, "infections-json"),
        "vaccinations": _json(vaccinations_json, list, "vaccinations-json"),
        "influencing_factors": _json(factors_json, dict, "factors-json"),
        "laboratory_record_ids": _csv(laboratory_ids),
        "current_observations": _csv(observations),
        "monitoring_items": _csv(monitoring_items),
        "source_type": "user_report",
    }
    _safe_profile_data(data)
    if dry_run:
        emit(
            "profile.immune-add.preview", data, json_output=json_output, requires_confirmation=True
        )
        return
    migrate()
    with session_scope() as session:
        entry = audit(
            session, "profile.immune-add", patient_id="local-primary", entity_type="ImmuneContext"
        )
        item = ImmuneContext(
            patient_id="local-primary",
            source_type="user_report",
            infections=data["infections"],
            vaccinations=data["vaccinations"],
            influencing_factors=data["influencing_factors"],
            laboratory_record_ids=data["laboratory_record_ids"],
            current_observations=data["current_observations"],
            monitoring_items=data["monitoring_items"],
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
        )
        session.add(item)
        session.flush()
        entry.entity_id = item.id
        data["id"] = item.id
    emit(
        "profile.immune-add",
        data,
        json_output=json_output,
        uncertainties=[
            "This is contextual history, not a score or causal explanation of infection."
        ],
    )


@app.command("timeline-add")
def timeline_add(
    title: str = typer.Option(..., "--title"),
    event_type: str = typer.Option(..., "--event-type"),
    date: str = typer.Option(..., "--date"),
    condition_id: str | None = typer.Option(None, "--condition-id"),
    description: str | None = typer.Option(None, "--description"),
    source_type: str = typer.Option("user_report", "--source-type"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    source_type = _source(source_type)
    event_date = parse_datetime(date, "date")
    if event_date is None:
        raise ValidationFailure("Timeline date is required")
    data = {
        "title": title,
        "event_type": event_type,
        "date": event_date.isoformat(),
        "condition_id": condition_id,
        "description": description,
        "source_type": source_type,
    }
    _safe_profile_data(data)
    if dry_run:
        emit(
            "profile.timeline-add.preview",
            data,
            json_output=json_output,
            requires_confirmation=True,
        )
        return
    migrate()
    with session_scope() as session:
        if condition_id:
            _condition(session, condition_id)
        entry = audit(
            session,
            "profile.timeline-add",
            patient_id="local-primary",
            entity_type="HealthTimelineEvent",
        )
        item = _timeline_event(
            session,
            condition_id=condition_id,
            event_type=event_type,
            event_date=event_date,
            title=title,
            description=description,
            related_record_type="manual_timeline_event",
            related_record_id=entry.id,
            source_type=source_type,
            audit_id=entry.id,
        )
        session.flush()
        entry.entity_id = item.id
        item.related_record_id = item.id
        data["id"] = item.id
    emit("profile.timeline-add", data, json_output=json_output)


@app.command("risk-add")
def risk_add(
    name: str = typer.Option(..., "--name"),
    factor_group: str = typer.Option(..., "--group"),
    category: str = typer.Option(..., "--category"),
    current_state: str | None = typer.Option(None, "--current-state"),
    management_action: str | None = typer.Option(None, "--management-action"),
    monitoring_metric: str | None = typer.Option(None, "--monitoring-metric"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    require_gate(dry_run, confirm)
    if factor_group not in RISK_GROUPS:
        raise ValidationFailure(
            "Risk factor group must be modifiable, non_modifiable, or condition_related"
        )
    data = {
        "factor_name": name,
        "factor_group": factor_group,
        "category": category,
        "current_state": current_state,
        "management_action": management_action,
        "monitoring_metric": monitoring_metric,
        "source_type": "user_report",
    }
    _safe_profile_data(data)
    if dry_run:
        emit("profile.risk-add.preview", data, json_output=json_output, requires_confirmation=True)
        return
    migrate()
    with session_scope() as session:
        entry = audit(
            session, "profile.risk-add", patient_id="local-primary", entity_type="RiskFactorProfile"
        )
        item = RiskFactorProfile(
            patient_id="local-primary",
            source_type="user_report",
            factor_name=name,
            factor_group=factor_group,
            category=category,
            current_state=current_state,
            management_action=management_action,
            monitoring_metric=monitoring_metric,
            status="active",
            verified=True,
            verification_status="user_confirmed",
            audit_id=entry.id,
        )
        session.add(item)
        session.flush()
        entry.entity_id = item.id
        data["id"] = item.id
    emit(
        "profile.risk-add",
        data,
        json_output=json_output,
        uncertainties=[
            "Risk factors guide modifiable actions and are not converted into disease probability."
        ],
    )


def _query(action: str, key: str, builder, json_output: bool) -> None:
    migrate()
    with session_scope() as session:
        value = builder(session)
    emit(action, {key: value}, json_output=json_output)


@app.command("summary")
def summary_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.summary", "profile", personal_profile.summary, json_output)


@app.command("conditions")
def conditions_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.conditions", "conditions", personal_profile.conditions, json_output)


@app.command("timeline")
def timeline_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.timeline", "events", personal_profile.timeline, json_output)


@app.command("skin")
def skin_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.skin", "skin", personal_profile.skin, json_output)


@app.command("image-compare")
def image_compare_command(
    group: str = typer.Option(..., "--group"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    migrate()
    with session_scope() as session:
        value = personal_profile.image_comparison(session, group)
    emit("profile.image-compare", {"comparison": value}, json_output=json_output)


@app.command("infections")
def infections_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.infections", "infection_context", personal_profile.infections, json_output)


@app.command("monitoring")
def monitoring_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.monitoring", "monitoring", personal_profile.monitoring, json_output)


@app.command("priorities")
def priorities_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _query("profile.priorities", "priorities", personal_profile.priorities, json_output)
