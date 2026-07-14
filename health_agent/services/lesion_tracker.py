from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.database.models import Lesion, LesionMeasurement, SourceDocument


def active_lesions(session: Session) -> list[Lesion]:
    lesions = session.scalars(select(Lesion).where(Lesion.verified.is_(True))).all()
    return [
        lesion
        for lesion in lesions
        if (source := session.get(SourceDocument, lesion.source_document_id)) is not None
        and not source.revoked
    ]


def measurement_rows(session: Session, lesion_id: str) -> list[dict[str, Any]]:
    measurements = session.scalars(
        select(LesionMeasurement).where(LesionMeasurement.verified.is_(True))
    ).all()
    rows = []
    for measurement in measurements:
        if measurement.details.get("lesion_id") != lesion_id:
            continue
        source = session.get(SourceDocument, measurement.source_document_id)
        if source is None or source.revoked:
            continue
        rows.append(
            {
                "id": measurement.id,
                "date": measurement.occurred_at.date().isoformat()
                if measurement.occurred_at
                else None,
                "size": measurement.details.get("size"),
                "unit": measurement.details.get("unit"),
                "modality": measurement.details.get("modality"),
                "laterality": measurement.details.get("laterality"),
                "anatomical_location": measurement.details.get("anatomical_location"),
                "original_text": measurement.original_text,
                "source_document_id": measurement.source_document_id,
                "follow_up_advice": measurement.details.get("follow_up_advice"),
            }
        )
    return sorted(rows, key=lambda row: (row["date"] or "", row["id"]))


def comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"comparable": False, "reason": "No confirmed measurements"}
    first, latest = rows[0], rows[-1]
    comparable = all(
        first.get(key) == latest.get(key)
        for key in ("unit", "modality", "laterality", "anatomical_location")
    )
    delta = None
    possible_error = True
    if comparable and first.get("size") is not None and latest.get("size") is not None:
        delta = float(latest["size"]) - float(first["size"])
        possible_error = abs(delta) <= max(
            1.0 if first["unit"] == "mm" else 0.1, float(first["size"]) * 0.1
        )
    return {
        "first": first,
        "latest": latest,
        "measurements": rows,
        "comparable": comparable,
        "size_change": delta,
        "measurement_error_possible": possible_error,
        "uncertainty": (
            "Small differences may reflect technique, slice selection, reader, or "
            "measurement error."
        ),
    }
