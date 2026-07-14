from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.database.models import RadiationAcquisition, RadiationExposure, SourceDocument


def active_exposures(session: Session) -> list[RadiationExposure]:
    exposures = session.scalars(
        select(RadiationExposure).where(RadiationExposure.verified.is_(True))
    ).all()
    return [
        exposure
        for exposure in exposures
        if (source := session.get(SourceDocument, exposure.source_document_id)) is not None
        and not source.revoked
    ]


def exposure_row(exposure: RadiationExposure) -> dict[str, Any]:
    return {
        "id": exposure.id,
        "date": exposure.examination_date.isoformat() if exposure.examination_date else None,
        "modality": exposure.modality,
        "examination_name": exposure.examination_name,
        "body_region": exposure.body_region,
        "protocol_name": exposure.protocol_name,
        "acquisition_count": exposure.acquisition_count,
        "dose_data_source": exposure.dose_data_source,
        "data_quality": exposure.data_quality,
        "total_dlp_mgy_cm": exposure.details.get("total_dlp_mgy_cm"),
        "event_dlp_sum_mgy_cm": exposure.details.get("event_dlp_sum_mgy_cm"),
        "dlp_difference_mgy_cm": exposure.details.get("dlp_difference_mgy_cm"),
        "dlp_difference_ratio": exposure.details.get("dlp_difference_ratio"),
        "dlp_consistency_warning": exposure.details.get("dlp_consistency_warning"),
        "study_instance_uid": exposure.details.get("study_instance_uid"),
        "source_document_id": exposure.source_document_id,
    }


def acquisition_rows(session: Session, exposure_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(RadiationAcquisition).where(RadiationAcquisition.exposure_id == exposure_id)
    ).all()
    return [
        {
            "id": row.id,
            "irradiation_event_uid": row.irradiation_event_uid,
            "acquisition_type": row.acquisition_type,
            "body_region": row.body_region,
            "scan_length_cm": row.scan_length_cm,
            "ctdi_vol_mgy": row.ctdi_vol_mgy,
            "dlp_mgy_cm": row.dlp_mgy_cm,
            "tube_voltage_kvp": row.tube_voltage_kvp,
            "tube_current_mas": row.tube_current_mas,
            "exposure_time": row.exposure_time,
            "pitch": row.pitch,
            "repeat_reason": row.repeat_reason,
            "additional_rdsr_fields": row.original_text,
        }
        for row in rows
    ]


def possible_duplicates(exposures: list[RadiationExposure]) -> list[dict[str, Any]]:
    alerts = []
    ordered = sorted(exposures, key=lambda item: item.examination_date or datetime.min)
    for index, current in enumerate(ordered):
        for prior in ordered[:index]:
            if not current.examination_date or not prior.examination_date:
                continue
            same_study = bool(
                current.details.get("study_instance_uid")
                and current.details.get("study_instance_uid")
                == prior.details.get("study_instance_uid")
            )
            interval = abs((current.examination_date - prior.examination_date).days)
            same_region = bool(current.body_region and current.body_region == prior.body_region)
            if same_study:
                kind = "same_examination_different_source"
            elif same_region and interval <= 30:
                kind = "possible_short_interval_repeat"
            else:
                continue
            alerts.append(
                {
                    "kind": kind,
                    "exposure_ids": [prior.id, current.id],
                    "interval_days": interval,
                    "requires_review": True,
                    "not_automatic_duplicate_radiation": True,
                }
            )
    return alerts


def summary(exposures: list[RadiationExposure]) -> dict[str, Any]:
    sources = Counter(item.dose_data_source for item in exposures)
    regions = Counter(item.body_region or "unknown" for item in exposures)
    exact_total_dlp = sum(
        float(item.details["total_dlp_mgy_cm"])
        for item in exposures
        if item.details.get("total_dlp_mgy_cm") is not None
        and item.data_quality == "exact_machine_record"
    )
    return {
        "examination_count": len(exposures),
        "by_region": dict(regions),
        "source_counts": dict(sources),
        "rdsr_count": sources.get("dicom_rdsr", 0),
        "dose_screen_count": sources.get("scanner_dose_page", 0),
        "report_only_count": sources.get("radiology_report", 0),
        "documented_total_dlp_mgy_cm": exact_total_dlp,
        "effective_dose_estimate": None,
        "effective_dose_note": (
            "No conversion is performed without a versioned region/age coefficient and uncertainty."
        ),
        "missing_dose_records": sum(item.data_quality == "insufficient_data" for item in exposures),
        "data_completeness": {
            "with_machine_record": sum(
                item.data_quality == "exact_machine_record" for item in exposures
            ),
            "total": len(exposures),
        },
        "medical_boundary": (
            "CTDIvol and DLP are scanner output indices, not organ absorbed dose; cumulative data "
            "must not be converted into an individual cancer probability, and no dose quota is "
            "calculated."
        ),
    }
