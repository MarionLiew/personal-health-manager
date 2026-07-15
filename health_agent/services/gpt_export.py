from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.cli.followup import row as followup_row
from health_agent.cli.symptoms import _episode_row
from health_agent.database.models import (
    Appointment,
    Diagnosis,
    FollowUpPlan,
    ImagingReport,
    ImportSession,
    Medication,
    Procedure,
    RecordCandidate,
    SourceDocument,
    SymptomEpisode,
    Treatment,
)
from health_agent.services.laboratory_trends import lab_rows
from health_agent.services.lesion_tracker import active_lesions, measurement_rows
from health_agent.services.personal_profile import summary as profile_summary
from health_agent.services.personal_profile import timeline as profile_timeline
from health_agent.services.radiation_ledger import active_exposures, exposure_row

EXPORT_FORMAT = "personal-health-agent-gpt-bundle"
EXPORT_VERSION = "1"

_DROP_KEYS = {
    "accession_number",
    "acquisition_uid",
    "device_identifier",
    "filename",
    "healthkit_uuid",
    "image_hash",
    "irradiation_event_uid",
    "local_path",
    "original_filename",
    "original_text",
    "patient_id",
    "sha256",
    "sha256_prefix",
    "sop_instance_uid",
    "series_instance_uid",
    "study_instance_uid",
}
_LABELLED_IDENTIFIER = re.compile(
    r"(?P<label>姓名|身份证(?:号)?|电话|手机号|微信(?:号|ID)?|登记号|检查号|住院号|门诊号|"
    r"病案号|就诊卡号|申请单号|出生日期)\s*[:：]?\s*[^\s,，;；]+",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PRC_ID = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\w)")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)")


def _redact_text(value: str) -> str:
    value = _LABELLED_IDENTIFIER.sub(lambda match: f"{match.group('label')}：[REDACTED]", value)
    value = _PHONE.sub("[REDACTED_PHONE]", value)
    value = _PRC_ID.sub("[REDACTED_ID]", value)
    return _EMAIL.sub("[REDACTED_EMAIL]", value)


def _sanitize(
    value: Any,
    source_refs: dict[str, str],
    *,
    include_institutions: bool,
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in _DROP_KEYS or normalized.endswith("_uid"):
                continue
            if normalized == "institution" and not include_institutions:
                continue
            if normalized == "source_document_id":
                result["source_ref"] = source_refs.get(str(item)) if item else None
                continue
            result[str(key)] = _sanitize(
                item,
                source_refs,
                include_institutions=include_institutions,
            )
        return result
    if isinstance(value, list):
        return [
            _sanitize(item, source_refs, include_institutions=include_institutions)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            _sanitize(item, source_refs, include_institutions=include_institutions)
            for item in value
        ]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _verified_rows(session: Session, model: Any) -> list[dict[str, Any]]:
    rows = session.scalars(select(model).where(model.verified.is_(True))).all()
    return [
        {
            "id": item.id,
            "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None,
            "source_type": item.source_type,
            "source_document_id": item.source_document_id,
            "details": item.details or {},
        }
        for item in rows
    ]


def build_gpt_bundle(
    session: Session,
    *,
    include_institutions: bool = True,
    include_pending: bool = False,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    sources = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.revoked.is_(False))
        .order_by(SourceDocument.imported_at, SourceDocument.id)
    ).all()
    source_refs = {item.id: f"SRC-{index:03d}" for index, item in enumerate(sources, start=1)}
    source_index = [
        {
            "source_ref": source_refs[item.id],
            "institution": item.institution if include_institutions else None,
            "generated_at": item.generated_at.isoformat() if item.generated_at else None,
            "imported_at": item.imported_at.isoformat(),
            "mime_type": item.mime_type,
            "parser": item.parser_name,
            "parser_version": item.parser_version,
        }
        for item in sources
    ]

    symptoms = session.scalars(
        select(SymptomEpisode).where(SymptomEpisode.verified.is_(True))
    ).all()
    followups = session.scalars(
        select(FollowUpPlan).where(FollowUpPlan.verified.is_(True))
    ).all()
    appointments = session.scalars(
        select(Appointment).where(Appointment.verified.is_(True))
    ).all()
    lesions = [
        {
            "id": item.id,
            "source_type": item.source_type,
            "source_document_id": item.source_document_id,
            "details": item.details,
            "measurements": measurement_rows(session, item.id),
        }
        for item in active_lesions(session)
    ]
    radiation = [
        {
            **exposure_row(item),
            "source_type": item.source_type,
            "institution": item.institution if include_institutions else None,
        }
        for item in active_exposures(session)
    ]
    pending = session.scalars(
        select(RecordCandidate).where(RecordCandidate.status == "pending")
    ).all()
    pending_rows: list[dict[str, Any]] = []
    for item in pending:
        import_session = session.get(ImportSession, item.import_session_id)
        source_id = import_session.source_document_id if import_session else None
        source = session.get(SourceDocument, source_id) if source_id else None
        if source is None or source.revoked:
            continue
        pending_rows.append(
            {
                "id": item.id,
                "candidate_type": item.candidate_type,
                "status": item.status,
                "source_type": "system_inference",
                "source_document_id": source.id,
                "confidence": item.confidence,
                "payload": item.payload,
            }
        )
    pending_counts = dict(Counter(item["candidate_type"] for item in pending_rows))

    raw = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_VERSION,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "language": "zh-CN",
        "privacy": {
            "local_generation_only": True,
            "external_upload_performed": False,
            "direct_identifier_redaction_applied": True,
            "raw_documents_included": False,
            "raw_report_text_included": False,
            "images_included": False,
            "institutions_included": include_institutions,
            "pending_candidates_included": include_pending,
            "warning": (
                "This bundle still contains sensitive health information. Review it locally before "
                "uploading to any external AI service."
            ),
        },
        "analysis_instructions": {
            "role": "个人健康资料整理与就医沟通辅助，不是诊断医生",
            "must_distinguish": [
                "user_report",
                "source_fact",
                "clinician_opinion",
                "guideline_rule",
                "system_inference",
            ],
            "allowed_output": [
                "已知问题",
                "时间变化",
                "已完成治疗",
                "当前状态",
                "风险因素与保护性因素",
                "数据缺口和不确定性",
                "需要观察的变化",
                "下一步管理建议",
                "建议向现实医生询问的问题",
            ],
            "prohibited_output": [
                "自动诊断",
                "个人癌症概率",
                "免疫力评分",
                "炎症评分",
                "辐射剂量换算个人患癌概率",
                "根据单个指标判断疾病",
            ],
            "action_levels": {
                "A": "存在急症信号，建议立即现实就医",
                "B": "建议近期就诊，由医生进一步判断",
                "C": "按照已有计划复查或复诊",
                "D": "记录并观察趋势",
                "E": "现有证据不支持新增检查",
            },
        },
        "source_index": source_index,
        "confirmed_data": {
            "personal_profile": profile_summary(session),
            "health_timeline": profile_timeline(session),
            "symptoms": [_episode_row(item) for item in symptoms],
            "laboratory_results": lab_rows(session),
            "imaging_reports": _verified_rows(session, ImagingReport),
            "lesions": lesions,
            "diagnoses": _verified_rows(session, Diagnosis),
            "procedures": _verified_rows(session, Procedure),
            "treatments": _verified_rows(session, Treatment),
            "medications": _verified_rows(session, Medication),
            "followups": [
                {**followup_row(item), "source_type": item.source_type} for item in followups
            ],
            "appointments": [
                {
                    "id": item.id,
                    "department": item.department,
                    "institution": item.institution if include_institutions else None,
                    "scheduled_start": (
                        item.scheduled_start.isoformat() if item.scheduled_start else None
                    ),
                    "purpose": item.purpose,
                    "status": item.status,
                    "source_type": item.source_type,
                }
                for item in appointments
            ],
            "radiation_exposures": radiation,
        },
        "unconfirmed_data": {
            "parser_candidates": pending_rows if include_pending else [],
            "warning": (
                "Every item in this section is an unconfirmed parser inference. It must not be "
                "presented as a medical fact, clinician opinion or diagnosis."
            ),
        },
        "pending_candidate_summary": {
            "count": len(pending_rows),
            "by_type": pending_counts,
            "included": include_pending,
            "reason": (
                "Included only in the separately labelled unconfirmed_data section."
                if include_pending
                else "Excluded until explicitly requested or human-confirmed."
            ),
        },
    }
    return _sanitize(raw, source_refs, include_institutions=include_institutions)


def bundle_counts(bundle: dict[str, Any]) -> dict[str, int]:
    confirmed = bundle["confirmed_data"]
    return {
        key: len(value)
        for key, value in confirmed.items()
        if isinstance(value, list)
    }
