from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.cli.followup import row as followup_row
from health_agent.cli.symptoms import _episode_row
from health_agent.database.models import (
    Appointment,
    Diagnosis,
    FollowUpPlan,
    SourceDocument,
    SymptomEpisode,
    Treatment,
)
from health_agent.services.laboratory_trends import lab_rows
from health_agent.services.lesion_tracker import active_lesions, measurement_rows
from health_agent.services.radiation_ledger import active_exposures, exposure_row

DEPARTMENT_TERMS = {
    "耳鼻喉科": ("耳", "鼻", "咽", "喉", "颈", "neck", "throat"),
    "呼吸科": ("胸", "肺", "气道", "上叶", "中叶", "下叶", "chest", "lung"),
    "胸外科": ("胸", "肺", "上叶", "中叶", "下叶", "chest", "lung"),
    "内分泌科": ("甲状腺", "thyroid", "血糖"),
}


def _relevant(department: str, value: object) -> bool:
    terms = DEPARTMENT_TERMS.get(department)
    if not terms:
        return True
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(term.lower() in text for term in terms)


def build_visit_summary(session: Session, department: str) -> dict[str, Any]:
    symptoms = session.scalars(
        select(SymptomEpisode)
        .where(SymptomEpisode.verified.is_(True))
        .order_by(SymptomEpisode.started_at.desc())
    ).all()
    symptom_rows = [
        _episode_row(item) for item in symptoms if _relevant(department, _episode_row(item))
    ]
    lesions = active_lesions(session)
    lesion_rows = []
    for lesion in lesions:
        lesion_row = {
            "id": lesion.id,
            **lesion.details,
            "measurements": measurement_rows(session, lesion.id),
        }
        if _relevant(department, lesion_row):
            lesion_rows.append(lesion_row)
    diagnoses = session.scalars(select(Diagnosis).where(Diagnosis.verified.is_(True))).all()
    opinion_rows = [
        {
            "id": item.id,
            "source_type": item.source_type,
            "details": item.details,
            "source_document_id": item.source_document_id,
        }
        for item in diagnoses
        if item.source_type == "clinician_opinion" and _relevant(department, item.details)
    ]
    pathology_rows = [
        {
            "id": item.id,
            "source_type": item.source_type,
            "details": item.details,
            "source_document_id": item.source_document_id,
        }
        for item in diagnoses
        if item.source_type == "source_fact"
        and "malignancy_status" in item.details
        and _relevant(department, item.details)
    ]
    treatments = session.scalars(select(Treatment).where(Treatment.verified.is_(True))).all()
    treatment_rows = [
        {"id": item.id, "details": item.details, "source_document_id": item.source_document_id}
        for item in treatments
        if _relevant(department, item.details)
    ]
    followups = session.scalars(select(FollowUpPlan).where(FollowUpPlan.verified.is_(True))).all()
    followup_rows = [
        row for item in followups if _relevant(department, (row := followup_row(item)))
    ]
    appointments = session.scalars(select(Appointment).where(Appointment.verified.is_(True))).all()
    appointment_rows = [
        {
            "id": item.id,
            "department": item.department,
            "scheduled_start": item.scheduled_start.isoformat() if item.scheduled_start else None,
            "purpose": item.purpose,
            "status": item.status,
        }
        for item in appointments
        if item.department == department
    ]
    labs = lab_rows(session)
    normal_labs = [row for row in labs if not row["abnormal_flag"]]
    abnormal_labs = [row for row in labs if row["abnormal_flag"]]
    radiation_rows = [
        exposure_row(item)
        for item in active_exposures(session)
        if _relevant(department, exposure_row(item))
    ]
    data_gaps = []
    if not symptom_rows:
        data_gaps.append("No department-relevant symptom timeline has been confirmed.")
    if not opinion_rows:
        data_gaps.append("No department-relevant clinician opinion has been confirmed.")
    if not lesion_rows and not labs:
        data_gaps.append("No department-relevant objective result is available.")
    if any(
        item["data_quality"] == "insufficient_data" or item["dose_incomplete"]
        for item in radiation_rows
    ):
        data_gaps.append("At least one ionizing examination has incomplete dose data.")
    source_ids = {
        str(value)
        for value in [
            *(row.get("source_document_id") for row in labs),
            *(row.get("source_document_id") for row in opinion_rows),
            *(row.get("source_document_id") for row in pathology_rows),
            *(row.get("source_document_id") for row in treatment_rows),
            *(row.get("source_document_id") for row in radiation_rows),
        ]
        if value
    }
    sources = []
    for source_id in sorted(source_ids):
        source = session.get(SourceDocument, source_id)
        if source is not None and not source.revoked:
            sources.append(
                {
                    "id": source.id,
                    "filename": source.original_filename,
                    "sha256_prefix": source.sha256[:12],
                    "parser": source.parser_name,
                }
            )
    active_symptoms = [row for row in symptom_rows if row["status"] != "resolved"]
    red_flags = [
        flag
        for item in symptoms
        for flag in (item.details or {}).get("red_flags", [])
        if _relevant(department, _episode_row(item))
    ]
    return {
        "department": department,
        "visit_purpose": appointment_rows[0]["purpose"] if appointment_rows else None,
        "red_flags": red_flags,
        "current_priority_symptoms": active_symptoms,
        "symptom_timeline": symptom_rows,
        "completed_examinations": {"laboratory": labs, "radiation_imaging": radiation_rows},
        "key_normal_results": normal_labs,
        "key_abnormal_results": abnormal_labs,
        "lesions": lesion_rows,
        "clinician_opinions": opinion_rows,
        "confirmed_pathology": pathology_rows,
        "completed_treatments_and_effects": treatment_rows,
        "unresolved_questions": data_gaps,
        "followup_plans": followup_rows,
        "appointments": appointment_rows,
        "radiation_examinations": radiation_rows,
        "data_gaps": data_gaps,
        "source_index": sources,
        # Compatibility for the 0.2 CLI contract.
        "confirmed_laboratory_results": labs,
        "evidence_note": (
            "Only confirmed facts and user reports are included. System inference remains "
            "separate; this summary does not diagnose or replace clinician review."
        ),
    }


def questions_from_summary(summary: dict[str, Any]) -> list[str]:
    questions: list[str] = []
    if summary["current_priority_symptoms"]:
        questions.append("现有症状更可能来自哪个解剖结构，哪些变化需要提前就诊？")
    if summary["lesions"]:
        questions.append("现有病灶是否需要复查，最合适的方式和时间范围是什么？")
    if summary["completed_examinations"]["radiation_imaging"]:
        questions.append("已有影像是否覆盖关注部位，新检查结果会如何改变处理？")
    if any("dose data" in gap for gap in summary["data_gaps"]):
        questions.append("是否可取得原检查的剂量页或RDSR以补全剂量记录？")
    if summary["followup_plans"]:
        questions.append("当前复查计划的时间范围是否仍适用，出现什么变化应提前？")
    if not summary["clinician_opinions"]:
        questions.append("请记录本次医生的判断、确定程度和后续建议，可以吗？")
    if summary["key_abnormal_results"]:
        questions.append("这些持续或异常结果中，哪些真正需要进一步处理？")
    return questions[:8]
