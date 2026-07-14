from __future__ import annotations

from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.config import ROOT
from health_agent.database.models import (
    HealthTimelineEvent,
    HPVLesion,
    ImmuneContext,
    LesionImage,
    PersonalCondition,
    RiskFactorProfile,
    ScarLesion,
    TreatmentEvent,
)
from health_agent.services.laboratory_trends import lab_rows


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def condition_row(item: PersonalCondition) -> dict[str, Any]:
    return {
        "id": item.id,
        "condition_id": item.id,
        "condition_name": item.condition_name,
        "normalized_name": item.normalized_name,
        "category": item.category,
        "body_region": item.body_region,
        "first_noted_date": _iso(item.first_noted_date),
        "current_status": item.current_status,
        "severity": item.severity,
        "recurrence_pattern": item.recurrence_pattern,
        "treatment_history": item.treatment_history or [],
        "related_records": item.related_records or [],
        "monitoring_plan": item.monitoring_plan or {},
        "source_type": item.source_type,
        "verified": item.verified,
        "notes": item.notes,
    }


def conditions(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(PersonalCondition)
        .where(PersonalCondition.verified.is_(True))
        .order_by(PersonalCondition.first_noted_date, PersonalCondition.recorded_at)
    ).all()
    return [condition_row(item) for item in rows]


def skin(session: Session) -> dict[str, Any]:
    scars = session.scalars(select(ScarLesion).where(ScarLesion.verified.is_(True))).all()
    hpv = session.scalars(select(HPVLesion).where(HPVLesion.verified.is_(True))).all()
    images = session.scalars(
        select(LesionImage).where(LesionImage.verified.is_(True)).order_by(LesionImage.taken_date)
    ).all()
    treatments = session.scalars(
        select(TreatmentEvent)
        .where(TreatmentEvent.verified.is_(True))
        .order_by(TreatmentEvent.treatment_date)
    ).all()
    return {
        "scar_lesions": [
            {
                "id": item.id,
                "scar_lesion_id": item.id,
                "condition_id": item.condition_id,
                "location": item.location,
                "scar_type": item.scar_type,
                "onset_date": _iso(item.onset_date),
                "trigger_event": item.trigger_event,
                "previous_treatment": item.previous_treatment or [],
                "treatment_date": _iso(item.treatment_date),
                "recurrence_after_treatment": item.recurrence_after_treatment,
                "changes": {
                    "size": item.size_change,
                    "color": item.color_change,
                    "hardness": item.hardness_change,
                },
                "symptoms": item.symptoms or [],
                "dermatologist_assessment": item.dermatologist_assessment,
                "source_type": item.source_type,
            }
            for item in scars
        ],
        "hpv_lesions": [
            {
                "id": item.id,
                "hpv_lesion_id": item.id,
                "condition_id": item.condition_id,
                "location": item.location,
                "lesion_type": item.lesion_type,
                "first_found": _iso(item.first_found),
                "diagnosis_method": item.diagnosis_method,
                "hpv_related": item.hpv_related,
                "treatment_history": item.treatment_history or [],
                "laser_dates": item.laser_dates or [],
                "recurrence": item.recurrence,
                "pathology_done": item.pathology_done,
                "dermatologist_opinion": item.dermatologist_opinion,
                "photos_available": item.photos_available,
                "current_status": item.current_status,
                "source_type": item.source_type,
            }
            for item in hpv
        ],
        "treatments": [
            {
                "id": item.id,
                "treatment_event_id": item.id,
                "condition_id": item.condition_id,
                "target_type": item.target_type,
                "target_id": item.target_id,
                "treatment_type": item.treatment_type,
                "date": _iso(item.treatment_date),
                "institution": item.institution,
                "response": item.response,
                "recurrence_time": _iso(item.recurrence_time),
                "source_type": item.source_type,
            }
            for item in treatments
        ],
        "images": [
            {
                "id": item.id,
                "image_id": item.id,
                "condition_id": item.condition_id,
                "lesion_type": item.lesion_type,
                "lesion_id": item.lesion_id,
                "taken_date": _iso(item.taken_date),
                "body_location": item.body_location,
                "image_hash": item.image_hash,
                "notes": item.notes,
                "comparison_group": item.comparison_group,
                "observations": item.details or {},
                "allowed_comparison": ["size_change", "count_change", "appearance_change"],
                "diagnostic_interpretation": None,
            }
            for item in images
        ],
        "medical_boundary": (
            "Scar and lesion photographs are tracked for change only, not diagnosis or cancer "
            "inference."
        ),
    }


def image_comparison(session: Session, group: str) -> dict[str, Any]:
    images = session.scalars(
        select(LesionImage)
        .where(LesionImage.verified.is_(True))
        .where(LesionImage.comparison_group == group)
        .order_by(LesionImage.taken_date)
    ).all()
    return {
        "comparison_group": group,
        "images": [
            {
                "id": item.id,
                "image_id": item.id,
                "taken_date": _iso(item.taken_date),
                "body_location": item.body_location,
                "observations": item.details or {},
                "source_type": item.source_type,
            }
            for item in images
        ],
        "comparable_fields": ["size", "count", "appearance"],
        "automatic_diagnosis": None,
        "uncertainty": (
            "Descriptions may be affected by angle, lighting and scale; clinical interpretation "
            "requires a qualified clinician."
        ),
    }


def infections(session: Session) -> dict[str, Any]:
    contexts = session.scalars(
        select(ImmuneContext)
        .where(ImmuneContext.verified.is_(True))
        .order_by(ImmuneContext.recorded_at.desc())
    ).all()
    hpv = skin(session)["hpv_lesions"]
    relevant_items = {
        "白细胞",
        "中性粒细胞绝对值",
        "淋巴细胞绝对值",
        "CRP",
        "超敏CRP",
        "血清铁",
        "铁蛋白",
    }
    labs = [row for row in lab_rows(session) if row["item"] in relevant_items]
    return {
        "known": [
            {
                "type": "skin_lesion_history",
                "location": item["location"],
                "hpv_related": item["hpv_related"],
                "status": item["current_status"],
                "source_type": item["source_type"],
            }
            for item in hpv
        ],
        "contexts": [
            {
                "id": item.id,
                "immune_context_id": item.id,
                "infections": item.infections or [],
                "vaccinations": item.vaccinations or [],
                "influencing_factors": item.influencing_factors or {},
                "laboratory_record_ids": item.laboratory_record_ids or [],
                "current_observations": item.current_observations or [],
                "monitoring_items": item.monitoring_items or [],
                "source_type": item.source_type,
            }
            for item in contexts
        ],
        "laboratory_trends": labs,
        "not_established": [
            "Wearable or lifestyle data alone do not establish an immune disorder.",
            "A mildly low white-cell result alone does not establish immune deficiency.",
            "No causal claim is made between lifestyle factors and HPV persistence.",
        ],
        "observe": ["lesion recurrence frequency", "confirmed blood-count trend"],
    }


def timeline(session: Session) -> list[dict[str, Any]]:
    events = session.scalars(
        select(HealthTimelineEvent)
        .where(HealthTimelineEvent.verified.is_(True))
        .order_by(HealthTimelineEvent.event_date, HealthTimelineEvent.recorded_at)
    ).all()
    return [
        {
            "id": item.id,
            "event_id": item.id,
            "date": _iso(item.event_date),
            "event_type": item.event_type,
            "title": item.title,
            "description": item.description,
            "condition_id": item.condition_id,
            "related_record_type": item.related_record_type,
            "related_record_id": item.related_record_id,
            "source_type": item.source_type,
        }
        for item in events
    ]


def risk_factors(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(RiskFactorProfile)
        .where(RiskFactorProfile.verified.is_(True))
        .where(RiskFactorProfile.status == "active")
    ).all()
    return [
        {
            "id": item.id,
            "risk_factor_id": item.id,
            "factor_name": item.factor_name,
            "factor_group": item.factor_group,
            "category": item.category,
            "current_state": item.current_state,
            "evidence": item.evidence or [],
            "management_action": item.management_action,
            "monitoring_metric": item.monitoring_metric,
            "source_type": item.source_type,
        }
        for item in rows
    ]


def priorities(session: Session) -> list[dict[str, Any]]:
    status_rank = {
        "active": 0,
        "recurrent": 1,
        "unknown": 2,
        "stable": 3,
        "improving": 4,
        "resolved": 5,
    }
    items = sorted(
        conditions(session),
        key=lambda item: (status_rank.get(str(item["current_status"]), 9), item["condition_name"]),
    )
    results = []
    for item in items:
        plan = item["monitoring_plan"]
        next_attention = (
            plan.get("next_attention") or plan.get("observe") or "Review recorded changes over time"
        )
        results.append(
            {
                "condition_id": item["id"],
                "focus": item["condition_name"],
                "status": item["current_status"],
                "next_attention": next_attention,
                "source_type": item["source_type"],
            }
        )
    for factor in risk_factors(session):
        if factor["factor_group"] != "modifiable":
            continue
        results.append(
            {
                "risk_factor_id": factor["id"],
                "focus": factor["factor_name"],
                "status": factor["current_state"] or "unknown",
                "next_attention": factor["management_action"]
                or factor["monitoring_metric"]
                or "Review modifiable trend",
                "source_type": factor["source_type"],
            }
        )
    return results[:3]


def profile_config() -> dict[str, Any]:
    path = ROOT / "config/personal_profile.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "conditions": raw.get("conditions", []),
        "monitoring": raw.get("monitoring", {}),
        "care_departments": raw.get("care_departments", []),
        "followup_preferences": raw.get("followup_preferences", {}),
        "risk_factors": raw.get("risk_factors", []),
        "goals": raw.get("goals", []),
    }


def monitoring(session: Session) -> dict[str, Any]:
    return {
        "condition_plans": [
            {
                "condition_id": item["id"],
                "condition_name": item["condition_name"],
                "current_status": item["current_status"],
                "monitoring_plan": item["monitoring_plan"],
            }
            for item in conditions(session)
        ],
        "preferences": profile_config(),
    }


def summary(session: Session) -> dict[str, Any]:
    return {
        "current_long_term_priorities": priorities(session),
        "known_conditions": conditions(session),
        "skin_overview": skin(session),
        "infection_and_laboratory_context": infections(session),
        "risk_factors": risk_factors(session),
        "monitoring": monitoring(session),
        "medical_boundary": (
            "This profile organizes known problems, changes, treatment and monitoring. It does not "
            "diagnose disease, calculate cancer probability, or generate immune/inflammation "
            "scores."
        ),
    }
