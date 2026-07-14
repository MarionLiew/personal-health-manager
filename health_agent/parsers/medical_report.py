from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

LAB_ALIASES = {
    "白细胞": ("白细胞", "WBC"),
    "中性粒细胞绝对值": ("中性粒细胞绝对值", "中性粒细胞计数", "NEUT#", "ANC"),
    "淋巴细胞绝对值": ("淋巴细胞绝对值", "淋巴细胞计数", "LYMPH#"),
    "血红蛋白": ("血红蛋白", "HGB", "Hb"),
    "红细胞": ("红细胞", "RBC"),
    "血小板": ("血小板", "PLT"),
    "超敏CRP": ("超敏C反应蛋白", "超敏CRP", "hs-CRP", "hsCRP"),
    "CRP": ("C反应蛋白", "CRP"),
    "血沉": ("红细胞沉降率", "血沉", "ESR"),
    "血清铁": ("血清铁", "Serum Iron", "SI"),
    "铁蛋白": ("铁蛋白", "Ferritin"),
    "转铁蛋白饱和度": ("转铁蛋白饱和度", "TSAT"),
    "转铁蛋白": ("转铁蛋白", "TRF"),
    "总铁结合力": ("总铁结合力", "TIBC"),
}

REPORT_RULES = (
    ("pet_ct", ("PET/CT", "PET-CT")),
    ("pathology", ("病理报告", "病理诊断")),
    ("ultrasound", ("超声", "彩超")),
    ("mri", ("MRI", "磁共振")),
    ("ct", ("CT", "计算机断层")),
    (
        "laboratory",
        tuple(alias for aliases in LAB_ALIASES.values() for alias in aliases)
        + ("血常规", "铁代谢", "肝功能", "肾功能", "甲状腺功能", "甲功"),
    ),
    ("clinician_note", ("门诊诊断", "医生意见", "处理意见")),
)


@dataclass(frozen=True)
class ParsedReport:
    report_type: str
    classification_confidence: float
    examination_date: str | None
    institution: str | None
    body_region: str | None
    title: str | None
    candidates: list[dict[str, Any]]
    unrecognized_text: list[str]
    uncertainties: list[str]


def _candidate_id(document_hash: str, kind: str, offset: int, payload: dict[str, Any]) -> str:
    fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return str(uuid5(NAMESPACE_URL, f"{document_hash}:{kind}:{offset}:{fingerprint}"))


def _date(text: str) -> str | None:
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", text)
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3])).date().isoformat()
    except ValueError:
        return None


def _classify(text: str) -> tuple[str, float]:
    upper = text.upper()
    for kind, words in REPORT_RULES:
        hits = sum(1 for word in words if word.upper() in upper)
        if hits:
            return kind, min(0.98, 0.72 + hits * 0.06)
    return "unknown", 0.2


def _lab_candidates(
    text: str, document_hash: str, examination_date: str | None
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    number = r"[-+]?\d+(?:\.\d+)?"
    for line in text.splitlines():
        stripped = line.strip()
        for normalized, aliases in LAB_ALIASES.items():
            alias = next((item for item in aliases if item.lower() in stripped.lower()), None)
            if not alias:
                continue
            tail = stripped[stripped.lower().find(alias.lower()) + len(alias) :]
            values = list(re.finditer(number, tail))
            if not values:
                continue
            value = float(values[0].group())
            range_match = re.search(rf"({number})\s*[-~–—]\s*({number})", tail[values[0].end() :])
            unit_match = re.search(
                r"(10\^?9/L|10\^?12/L|×10[⁹¹²]/L|g/L|mg/L|mg/dL|µg/dL|mmol/L|µmol/L|umol/L|ng/mL|%|mm/h)",
                tail,
                re.IGNORECASE,
            )
            flag = "high" if any(mark in stripped for mark in ("↑", " H", "高")) else None
            if any(mark in stripped for mark in ("↓", " L", "低")):
                flag = "low"
            payload = {
                "item_name": normalized,
                "original_item_name": alias,
                "value": value,
                "unit": unit_match.group(1) if unit_match else None,
                "reference_low": float(range_match.group(1)) if range_match else None,
                "reference_high": float(range_match.group(2)) if range_match else None,
                "abnormal_flag": flag,
                "examination_date": examination_date,
                "specimen_type": "血液" if "血" in text else None,
            }
            offset = text.find(line)
            confidence = 0.96 if unit_match and range_match and examination_date else 0.82
            candidates.append(
                {
                    "id": _candidate_id(document_hash, "laboratory_result", offset, payload),
                    "candidate_type": "laboratory_result",
                    "payload": payload,
                    "original_text": stripped,
                    "original_offset": offset,
                    "confidence": confidence,
                }
            )
            break
    return candidates


def _imaging_candidates(
    text: str, document_hash: str, report_type: str, examination_date: str | None
) -> list[dict[str, Any]]:
    modality = {"ct": "CT", "pet_ct": "PET/CT", "mri": "MRI", "ultrasound": "US"}.get(report_type)
    if modality is None:
        return []
    findings_match = re.search(
        r"(?:检查所见|影像所见|所见)[:：]?\s*(.*?)(?=(?:诊断提示|诊断意见|印象|结论)[:：]|$)",
        text,
        re.DOTALL,
    )
    impression_match = re.search(r"(?:诊断提示|诊断意见|印象|结论)[:：]?\s*(.*)", text, re.DOTALL)
    body = next((part for part in ("胸部", "颈部", "腹部", "头颅", "肺") if part in text), None)
    payload = {
        "examination_date": examination_date,
        "modality": modality,
        "body_region": body,
        "protocol": (
            "CTA"
            if "CTA" in text.upper()
            else "enhanced"
            if "增强" in text
            else "low_dose"
            if "低剂量" in text
            else "noncontrast"
        ),
        "findings_text": findings_match.group(1).strip() if findings_match else None,
        "impression_text": impression_match.group(1).strip() if impression_match else None,
        "has_3d_reconstruction": any(word in text for word in ("三维重建", "3D重建", "VR")),
        "contains_dose_information": any(word in text for word in ("CTDIvol", "DLP")),
    }
    candidates = [
        {
            "id": _candidate_id(document_hash, "imaging_report", 0, payload),
            "candidate_type": "imaging_report",
            "payload": payload,
            "original_text": text,
            "original_offset": 0,
            "confidence": 0.94
            if examination_date and (findings_match or impression_match)
            else 0.75,
        }
    ]
    lesion_pattern = re.compile(
        r"(?P<nature>结节|淋巴结|肿块|病灶)[^。；\n]{0,30}?"
        r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm)",
        re.IGNORECASE,
    )
    for match in lesion_pattern.finditer(text):
        prefix = text[max(0, match.start() - 40) : match.start()]
        location_match = re.search(
            r"(?P<side>左|右)?(?P<location>[上中下]叶|肺门|颈部|甲状腺)", prefix
        )
        lesion = {
            "lesion_kind": match.group("nature"),
            "laterality": location_match.group("side") if location_match else None,
            "anatomical_location": location_match.group("location") if location_match else body,
            "size": float(match.group("size")),
            "unit": match.group("unit").lower(),
            "modality": modality,
            "examination_date": examination_date,
            "follow_up_advice": impression_match.group(1).strip() if impression_match else None,
        }
        candidates.append(
            {
                "id": _candidate_id(document_hash, "lesion", match.start(), lesion),
                "candidate_type": "lesion",
                "payload": lesion,
                "original_text": match.group(0),
                "original_offset": match.start(),
                "confidence": 0.9 if location_match and examination_date else 0.76,
            }
        )
    return candidates


def parse_medical_report(text: str, document_hash: str) -> ParsedReport:
    report_type, confidence = _classify(text)
    examination_date = _date(text)
    institution_match = re.search(r"^\s*([^\n]{2,40}(?:医院|医学中心|检验所))", text, re.MULTILINE)
    title = next((line.strip() for line in text.splitlines() if line.strip()), None)
    candidates = _lab_candidates(text, document_hash, examination_date)
    candidates.extend(_imaging_candidates(text, document_hash, report_type, examination_date))
    recognized_lines = {
        item["original_text"] for item in candidates if "\n" not in item["original_text"]
    }
    unrecognized = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and line.strip() not in recognized_lines
    ]
    uncertainties = []
    if examination_date is None:
        uncertainties.append("未可靠识别检查日期")
    if confidence < 0.7:
        uncertainties.append("报告分类置信度低，不得自动写入医疗事实")
    return ParsedReport(
        report_type=report_type,
        classification_confidence=confidence,
        examination_date=examination_date,
        institution=institution_match.group(1).strip() if institution_match else None,
        body_region=next(
            (part for part in ("胸部", "颈部", "腹部", "头颅", "甲状腺") if part in text),
            None,
        ),
        title=title,
        candidates=candidates,
        unrecognized_text=unrecognized[:50],
        uncertainties=uncertainties,
    )
