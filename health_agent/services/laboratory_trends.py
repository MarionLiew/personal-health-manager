from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_agent.database.models import LaboratoryResult, SourceDocument

UNIT_ALIASES = {
    "×10⁹/L": "10^9/L",
    "10^9/L": "10^9/L",
    "10⁹/L": "10^9/L",
    "umol/L": "µmol/L",
}


def normalize_unit(unit: str | None) -> str | None:
    return UNIT_ALIASES.get(unit or "", unit)


def _convert(item: str, value: float, unit: str | None) -> tuple[float, str | None, str | None]:
    normalized = normalize_unit(unit)
    if item == "血清铁" and normalized == "µg/dL":
        return value / 5.585, "µmol/L", "1 µmol/L iron = 5.585 µg/dL"
    return value, normalized, None


def lab_rows(session: Session, item_name: str | None = None) -> list[dict[str, Any]]:
    results = session.scalars(
        select(LaboratoryResult).where(LaboratoryResult.verified.is_(True))
    ).all()
    rows = []
    for result in results:
        details = result.details
        if item_name and details.get("item_name") != item_name:
            continue
        source = session.get(SourceDocument, result.source_document_id)
        if source is None or source.revoked:
            continue
        converted, converted_unit, method = _convert(
            str(details.get("item_name")), float(details["value"]), details.get("unit")
        )
        rows.append(
            {
                "id": result.id,
                "date": result.occurred_at.date().isoformat() if result.occurred_at else None,
                "item": details.get("item_name"),
                "original_item": details.get("original_item_name"),
                "value": details.get("value"),
                "unit": details.get("unit"),
                "reference_low": details.get("reference_low"),
                "reference_high": details.get("reference_high"),
                "abnormal_flag": details.get("abnormal_flag"),
                "normalized_value": converted,
                "normalized_unit": converted_unit,
                "conversion_method": method,
                "report_id": details.get("laboratory_report_id"),
                "source_document_id": result.source_document_id,
                "source_type": result.source_type,
            }
        )
    return sorted(rows, key=lambda row: (row["date"] or "", row["id"]))


def trend_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["normalized_unit"] or "unknown")].append(row)
    flags = [row["abnormal_flag"] for row in rows if row["abnormal_flag"]]
    persistence = (
        "repeated_abnormality_needs_review"
        if len(flags) >= 2 and len(set(flags[-2:])) == 1
        else "single_abnormality"
        if flags
        else "no_flagged_abnormality"
    )
    return {
        "groups": [{"unit": unit, "results": values} for unit, values in groups.items()],
        "persistence": persistence,
        "uncertainty": (
            "Different units or reference intervals are not directly compared without a "
            "documented conversion."
        ),
        "medical_boundary": (
            "A low white-cell result alone does not establish immune deficiency or cancer."
        ),
    }
