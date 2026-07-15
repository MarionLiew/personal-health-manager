from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

LAB_ALIASES = {
    "凝血酶原时间": ("凝血酶原时间", "PT"),
    "凝血酶原活动度": ("凝血酶原活动度", "PTA", "PT(%)"),
    "国际标准化比值": ("国际标准化比值", "INR值", "INR"),
    "活化部分凝血活酶时间": ("活化部分凝血活酶时间", "APTT"),
    "凝血酶时间": ("凝血酶时间", "TT"),
    "纤维蛋白原": ("纤维蛋白原", "FIB"),
    "中性粒细胞比例": ("中性分叶粒细胞比例", "中性粒细胞比例", "NEUT%"),
    "淋巴细胞比例": ("淋巴细胞比例", "LYMPH%", "LY%"),
    "单核细胞比例": ("单核细胞比例", "MONO%", "MO%"),
    "嗜酸粒细胞比例": ("嗜酸细胞比例", "嗜酸粒细胞比例", "EO%"),
    "嗜碱粒细胞比例": ("嗜碱细胞比例", "嗜碱粒细胞比例", "BASO%"),
    "白细胞": ("白细胞", "WBC"),
    "中性粒细胞绝对值": (
        "中性粒细胞绝对值",
        "中性分叶粒细胞计数",
        "中性粒细胞计数",
        "NEUT#",
        "ANC",
    ),
    "淋巴细胞绝对值": ("淋巴细胞绝对值", "淋巴细胞计数", "LYMPH#", "LY#"),
    "单核细胞绝对值": ("单核细胞计数", "MONO#", "MO#"),
    "嗜酸粒细胞绝对值": ("嗜酸细胞计数", "嗜酸粒细胞计数", "EO#"),
    "嗜碱粒细胞绝对值": ("嗜碱细胞计数", "嗜碱粒细胞计数", "BASO#"),
    "红细胞比积": ("红细胞比积", "HCT", "Ht"),
    "平均红细胞血红蛋白浓度": ("平均红细胞血红蛋白浓度", "MCHC"),
    "平均红细胞血红蛋白含量": ("平均红细胞血红蛋白含量", "MCH"),
    "平均红细胞体积": ("平均红细胞体积", "MCV"),
    "红细胞分布宽度CV": ("RBC分布宽度CV", "RDW-CV"),
    "红细胞分布宽度SD": ("RBC分布宽度SD", "RDW-SD"),
    "血红蛋白": ("血红蛋白", "HGB", "Hb"),
    "红细胞": ("红细胞", "RBC"),
    "血小板": ("血小板", "PLT"),
    "血小板压积": ("血小板压积", "PCT"),
    "平均血小板体积": ("平均血小板体积", "MPV"),
    "血小板分布宽度": ("血小板分布宽度", "PDW"),
    "大血小板百分率": ("大血小板百分率", "P-LCR"),
    "有核红细胞比例": ("有核红细胞%", "NRBC%"),
    "有核红细胞绝对值": ("有核红细胞#", "NRBC#"),
    "网织红细胞比例": ("网织红细胞比例", "RET%"),
    "网织红细胞绝对值": ("网织红细胞#", "RET#"),
    "高荧光网织红细胞": ("高荧光网织红细胞", "HFR"),
    "中荧光网织红细胞": ("中荧光网织红细胞", "MFR"),
    "低荧光网织红细胞": ("低荧光网织红细胞", "LFR"),
    "未成熟网织红细胞": ("未成熟网织红细胞", "IRF"),
    "超敏CRP": ("超敏C反应蛋白", "超敏CRP", "hs-CRP", "hsCRP"),
    "CRP": ("C反应蛋白", "CRP"),
    "血沉": ("红细胞沉降率", "血沉", "ESR"),
    "血清铁": ("血清铁", "Serum Iron", "SI"),
    "铁蛋白": ("铁蛋白", "Ferritin"),
    "转铁蛋白饱和度": ("转铁蛋白饱和度", "TSAT"),
    "转铁蛋白": ("转铁蛋白", "TRF"),
    "总铁结合力": ("总铁结合力", "TIBC"),
    "丙氨酸氨基转移酶": ("丙氨酸氨基转移酶", "谷丙转氨酶", "ALT", "GPT"),
    "天门冬氨酸氨基转移酶": ("天门冬氨酸氨基转移酶", "谷草转氨酶", "AST", "GOT"),
    "碱性磷酸酶": ("碱性磷酸酶", "ALP"),
    "γ-谷氨酰转移酶": ("γ-谷氨酰转移酶", "谷氨酰转肽酶", "GGT", "γ-GT"),
    "总胆红素": ("总胆红素", "TBIL", "Total Bilirubin"),
    "直接胆红素": ("直接胆红素", "DBIL", "Direct Bilirubin"),
    "总蛋白": ("总蛋白", "TP", "Total Protein"),
    "白蛋白": ("白蛋白", "ALB", "Albumin"),
    "球蛋白": ("球蛋白", "GLB", "Globulin"),
    "肌酐": ("肌酐", "CREA", "Creatinine"),
    "尿素": ("尿素", "尿素氮", "UREA", "BUN"),
    "尿酸": ("尿酸", "UA", "Uric Acid"),
    "估算肾小球滤过率": ("估算肾小球滤过率", "eGFR"),
    "胱抑素C": ("胱抑素C", "Cystatin C", "CysC"),
    "促甲状腺激素": ("促甲状腺激素", "TSH"),
    "游离三碘甲状腺原氨酸": ("游离三碘甲状腺原氨酸", "FT3", "Free T3"),
    "游离甲状腺素": ("游离甲状腺素", "FT4", "Free T4"),
    "总三碘甲状腺原氨酸": ("总三碘甲状腺原氨酸", "总T3", "TT3", "T3"),
    "总甲状腺素": ("总甲状腺素", "总T4", "TT4", "T4"),
    "甲状腺过氧化物酶抗体": ("甲状腺过氧化物酶抗体", "TPOAb", "TPO-Ab"),
    "甲状腺球蛋白抗体": ("甲状腺球蛋白抗体", "TgAb", "Tg-Ab"),
    "促甲状腺激素受体抗体": ("促甲状腺激素受体抗体", "TRAb", "TR-Ab"),
    "降钙素原": ("降钙素原", "PCT", "Procalcitonin"),
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
    dates: dict[str, Any]
    institution: str | None
    body_region: str | None
    title: str | None
    candidates: list[dict[str, Any]]
    unrecognized_text: list[str]
    uncertainties: list[str]


def _candidate_id(document_hash: str, kind: str, offset: int, payload: dict[str, Any]) -> str:
    fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return str(uuid5(NAMESPACE_URL, f"{document_hash}:{kind}:{offset}:{fingerprint}"))


def _alias_span(text: str, alias: str) -> tuple[int, int] | None:
    if re.search(r"[A-Za-z0-9]", alias):
        match = re.search(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        )
    else:
        match = re.search(re.escape(alias), text, re.IGNORECASE)
    return match.span() if match else None


def _date(text: str) -> str | None:
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", text)
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3])).date().isoformat()
    except ValueError:
        return None


def _labeled_date(text: str, labels: tuple[str, ...]) -> str | None:
    values = _labeled_dates(text, labels)
    return values[0] if values else None


def _labeled_dates(text: str, labels: tuple[str, ...]) -> list[str]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    date_pattern = r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?"
    matches = list(
        re.finditer(rf"(?:{label_pattern})[ \t]*[:：]?[ \t]*{date_pattern}", text)
    )
    matches.extend(
        re.finditer(rf"{date_pattern}[ \t]*(?:{label_pattern})[ \t]*[:：]?", text)
    )
    values: list[str] = []
    for match in sorted(matches, key=lambda item: item.start()):
        try:
            value = datetime(int(match[1]), int(match[2]), int(match[3])).date().isoformat()
        except ValueError:
            continue
        if value not in values:
            values.append(value)
    return values


def _date_contexts(text: str) -> dict[str, Any]:
    report_dates = _labeled_dates(text, ("报告日期", "报告时间", "审核日期"))
    explicit_supplement_date = _labeled_date(text, ("补充报告日期", "补充日期"))
    supplement_date = explicit_supplement_date
    if (
        supplement_date is None
        and len(report_dates) > 1
        and any(marker in text for marker in ("补充报告", "补充诊断意见"))
    ):
        supplement_date = report_dates[-1]
    result: dict[str, Any] = {
        "examination_date": _labeled_date(text, ("检查日期", "检查时间")),
        "procedure_date": _labeled_date(text, ("操作日期", "手术日期", "治疗日期")),
        "specimen_date": _labeled_date(text, ("取材日期", "送检日期", "标本日期")),
        "collection_date": _labeled_date(text, ("采集日期", "采集时间")),
        "received_date": _labeled_date(text, ("接收日期", "接收时间", "收到日期")),
        "report_date": report_dates[0] if report_dates else None,
        "supplement_date": supplement_date,
    }
    all_dates = []
    for match in re.finditer(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", text):
        try:
            value = datetime(int(match[1]), int(match[2]), int(match[3])).date().isoformat()
        except ValueError:
            continue
        if value not in all_dates:
            all_dates.append(value)
    assigned = {value for value in result.values() if isinstance(value, str)}
    result["all_dates"] = all_dates
    result["unassigned_dates"] = [value for value in all_dates if value not in assigned]
    return result


def _classify(text: str) -> tuple[str, float]:
    upper = text.upper()
    if any(marker in text for marker in ("喉镜检查报告", "鼻内镜检查报告", "内镜所见", "内镜诊断")):
        return "endoscopy", 0.96
    if any(marker in text for marker in ("医学检验报告", "检验报告", "参考区间")) and any(
        marker in text for marker in ("标本", "检测项目", "检验者", "凝血", "血常规")
    ):
        return "laboratory", 0.97
    if re.search(r"(?:粗针|空芯针|穿刺).{0,8}(?:活检|取材)", text) and any(
        marker in text for marker in ("进针", "取组织", "取得组织", "针")
    ):
        return "procedure", 0.96
    pathology_markers = sum(
        marker in upper
        for marker in (
            "病理报告",
            "病理诊断",
            "病理补充报告",
            "免疫组化",
            "CD20",
            "CD3",
            "KI-67",
        )
    )
    pathology_has_content = bool(re.search(r"病理诊断[ \t]*[:：][ \t]*\S+", text))
    if (
        pathology_markers >= 2
        or "病理报告" in text
        or "病理补充报告" in text
        or pathology_has_content
    ):
        return "pathology", min(0.98, 0.82 + pathology_markers * 0.03)
    if (
        re.search(r"(?:^|[^A-Z0-9])MR(?:I)?(?:[^A-Z0-9]|$)", upper)
        and any(marker in text for marker in ("影像所见", "影像诊断", "检查方法"))
    ):
        return "mri", 0.96
    for kind, words in REPORT_RULES:
        hits = sum(1 for word in words if _alias_span(text, word) is not None)
        if hits:
            return kind, min(0.98, 0.72 + hits * 0.06)
    return "unknown", 0.2


def _lab_candidates(
    text: str,
    document_hash: str,
    examination_date: str | None,
    dates: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    number = r"[-+]?\d+(?:\.\d+)?"
    for line in text.splitlines():
        stripped = line.strip()
        matches = [
            (normalized, alias, span)
            for normalized, aliases in LAB_ALIASES.items()
            for alias in aliases
            if (span := _alias_span(stripped, alias)) is not None
        ]
        if not matches:
            continue
        normalized, alias, span = max(matches, key=lambda item: len(item[1]))
        prefix = stripped[: span[0]]
        tail = stripped[span[1] :]
        prefix_value = re.search(rf"({number})$", prefix)
        values = list(re.finditer(number, tail))
        if prefix_value:
            value = float(prefix_value.group(1))
            range_search_text = tail
        elif values:
            value = float(values[0].group())
            range_search_text = tail[values[0].end() :]
        else:
            continue
        range_match = re.search(
            rf"({number})\s*[-~–—至到]\s*({number})", range_search_text
        )
        unit_match = re.search(
                r"(10\^?9/L|10\^?12/L|x10\^?9/L|x10\^?12/L|×10[⁹¹²]/L|"
                r"U/L|IU/L|g/L|mg/L|mg/dL|µg/dL|mmol/L|µmol/L|umol/L|ng/mL|"
                r"ng/L|pg/mL|mIU/L|µIU/mL|pmol/L|mL/min/1\.73m2|%|mm/h|fL|pg|秒)",
                tail,
                re.IGNORECASE,
            )
        flag = (
            "high"
            if "↑" in tail or re.search(r"(?:^|\s)(?:H|高)(?:\s|$)", tail)
            else "low"
            if "↓" in tail or re.search(r"(?:^|\s)(?:L|低)(?:\s|$)", tail)
            else None
        )
        payload = {
            "item_name": normalized,
            "original_item_name": alias,
            "value": value,
            "unit": unit_match.group(1) if unit_match else None,
            "reference_low": float(range_match.group(1)) if range_match else None,
            "reference_high": float(range_match.group(2)) if range_match else None,
            "abnormal_flag": flag,
            "examination_date": examination_date,
            "collection_date": dates.get("collection_date"),
            "received_date": dates.get("received_date"),
            "report_date": dates.get("report_date"),
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
    return candidates


def _clean_report_section(value: str | None) -> str | None:
    if not value:
        return None
    value = re.split(r"\n\s*\n\s*\n", value, maxsplit=1)[0]
    lines = []
    for line in value.splitlines():
        if any(
            marker in line
            for marker in ("病理编号", "检查者", "报告医生", "审核医生", "检查技师")
        ):
            break
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines) or None


def _imaging_candidates(
    text: str,
    document_hash: str,
    report_type: str,
    examination_date: str | None,
    dates: dict[str, Any],
) -> list[dict[str, Any]]:
    modality = {
        "ct": "CT",
        "pet_ct": "PET/CT",
        "mri": "MRI",
        "ultrasound": "US",
        "endoscopy": "ENDOSCOPY",
    }.get(report_type)
    if modality is None:
        return []
    findings_match = re.search(
        r"(?:检查所见|影像所见|超声所见|超声描述|内镜所见|检查结果|所见)"
        r"[:：]?\s*(.*?)"
        r"(?=(?:影像诊断|内镜诊断|诊断提示|超声提示|检查提示|诊断意见|印象|结论)"
        r"[:：]|病理编号[:：]|$)",
        text,
        re.DOTALL,
    )
    impression_match = re.search(
        r"(?:影像诊断|内镜诊断|诊断提示|超声提示|检查提示|诊断意见|印象|结论)"
        r"[:：]?\s*(.*?)(?=\n\s*(?:建议|建\s*议|病理编号|检查者|报告医生|审核医生|"
        r"检查技师|第\s*\d+\s*页)[:：]?|$)",
        text,
        re.DOTALL,
    )
    body = next(
        (
            part
            for part in ("鼻咽部", "上腹部", "鼻腔", "喉部", "胸部", "颈部", "腹部", "头颅", "肺")
            if part in text
        ),
        None,
    )
    if body is None and report_type == "endoscopy":
        body = "咽喉" if "喉镜" in text else "鼻腔" if "鼻内镜" in text else None
    relevant_sentences = [
        sentence.strip()
        for sentence in re.split(r"[。；;\n]+", text)
        if sentence.strip()
        and any(
            structure in sentence
            for structure in ("淋巴结", "甲状腺", "腮腺", "喉返神经", "肺", "结节")
        )
    ]
    findings_text = _clean_report_section(findings_match.group(1) if findings_match else None)
    if not findings_text and relevant_sentences:
        findings_text = "；".join(relevant_sentences)
    impression_text = _clean_report_section(
        impression_match.group(1) if impression_match else None
    )
    if not impression_text:
        impression_sentences = [
            sentence
            for sentence in relevant_sentences
            if any(marker in sentence for marker in ("考虑", "提示", "未见异常", "建议"))
        ]
        impression_text = "；".join(impression_sentences) or None

    aggregate_measurements: list[dict[str, Any]] = []
    lymph_range_pattern = re.compile(
        r"(?:双侧|两侧)?颈部[^。；\n]{0,30}?(?:多个|多发)?淋巴结[^。；\n]{0,20}?"
        r"(?:直径|大小|长径)?\s*(?:约)?(?P<minimum>\d+(?:\.\d+)?)\s*"
        r"(?P<first_unit>mm|cm)?\s*[-~–—至到]\s*"
        r"(?P<maximum>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm)",
        re.IGNORECASE,
    )
    lymph_ranges = list(lymph_range_pattern.finditer(text))
    for match in lymph_ranges:
        aggregate_measurements.append(
            {
                "structure": "颈部淋巴结",
                "minimum": float(match.group("minimum")),
                "maximum": float(match.group("maximum")),
                "unit": match.group("unit").lower(),
                "scope": (
                    "multiple_bilateral_nodes" if "双侧" in match.group(0) else "multiple_nodes"
                ),
                "individual_lesion_trackable": False,
            }
        )
    payload = {
        "examination_date": examination_date,
        "report_date": dates.get("report_date"),
        "modality": modality,
        "body_region": body,
        "protocol": (
            "diagnostic_endoscopy"
            if report_type == "endoscopy"
            else "CTA"
            if "CTA" in text.upper()
            else "enhanced"
            if "增强" in text
            else "low_dose"
            if "低剂量" in text
            else "noncontrast"
        ),
        "findings_text": findings_text,
        "impression_text": impression_text,
        "aggregate_measurements": aggregate_measurements,
        "endoscopy_type": (
            "laryngoscopy"
            if "喉镜" in text
            else "nasal_endoscopy"
            if "鼻内镜" in text
            else None
        ),
        "endoscopy_scores": {
            key: int(match.group(1))
            for key, match in {
                "RFS": re.search(r"RFS\s*[:：]\s*(\d+)\s*分", text, re.IGNORECASE),
                "RSI": re.search(
                    r"RSI(?:症状评分)?\s*[:：]\s*(\d+)\s*分", text, re.IGNORECASE
                ),
            }.items()
            if match is not None
        },
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
        if match.group("nature") == "淋巴结" and any(
            range_match.start() <= match.start() <= range_match.end()
            for range_match in lymph_ranges
        ):
            continue
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
            "follow_up_advice": impression_text,
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


def _procedure_candidate(
    text: str, document_hash: str, report_type: str, procedure_date: str | None
) -> list[dict[str, Any]]:
    if report_type != "procedure":
        return []
    gauge_match = re.search(r"(\d{1,2})\s*G(?:针)?", text, re.IGNORECASE)
    pass_match = re.search(r"(?:共)?进针\s*(\d+)\s*次", text)
    specimen_match = re.search(
        r"(?:取|取得|获取)[^\d。；]{0,12}(\d+)\s*(?:颗|条|份|块)", text
    )
    payload = {
        "examination_date": procedure_date,
        "procedure_date": procedure_date,
        "procedure_type": "core_needle_biopsy" if "粗针" in text else "needle_biopsy",
        "body_region": "颈部" if "颈部" in text else None,
        "target": "淋巴结" if "淋巴结" in text else None,
        "laterality": "左" if "左侧" in text else "右" if "右侧" in text else None,
        "imaging_guidance": "ultrasound" if "超声" in text else None,
        "needle_gauge": int(gauge_match.group(1)) if gauge_match else None,
        "pass_count": int(pass_match.group(1)) if pass_match else None,
        "specimen_count": int(specimen_match.group(1)) if specimen_match else None,
        "outcome": None,
    }
    return [
        {
            "id": _candidate_id(document_hash, "procedure", 0, payload),
            "candidate_type": "procedure",
            "payload": payload,
            "original_text": text,
            "original_offset": 0,
            "confidence": 0.94 if procedure_date and gauge_match else 0.84,
        }
    ]


def _pathology_candidate(
    text: str,
    document_hash: str,
    report_type: str,
    examination_date: str | None,
    dates: dict[str, Any],
) -> list[dict[str, Any]]:
    if report_type != "pathology":
        return []
    normalized = re.sub(r"\s+", "", text)
    limited_sample = bool(
        re.search(r"(?:组织很少|少量淋巴组织|取材较少|取材少|标本少)", normalized)
    )
    if re.search(r"(?:肿瘤|恶性).{0,8}(?:证据不足|依据不足)", normalized):
        malignancy = "insufficient_evidence"
    elif re.search(r"(?:未见|无|不支持)恶性", normalized):
        malignancy = "negative"
    elif "良性" in normalized:
        malignancy = "benign"
    elif re.search(r"(?:可疑|疑似)恶性", normalized):
        malignancy = "suspicious"
    elif re.search(r"(?:不能排除|性质待定|不确定)", normalized):
        malignancy = "indeterminate"
    elif "恶性" in normalized:
        malignancy = "malignant"
    else:
        malignancy = "not_stated"
    site = next(
        (part for part in ("甲状腺", "肺", "淋巴结", "胃", "肠", "乳腺") if part in text), None
    )
    ki67_match = re.search(
        r"Ki-?67(?P<prefix>[^\d]{0,12})(?P<value>\d+(?:\.\d+)?)"
        r"\s*%?(?P<suffix>[^\s，。；)]{0,4})",
        text,
        re.I,
    )
    def marker_result(marker: str) -> str | None:
        match = re.search(rf"{re.escape(marker)}(.{{0,16}})", text, re.I)
        if not match:
            return None
        result = match.group(1)
        if any(
            term in result
            for term in ("部分阳性", "少数阳性", "少量阳性", "部分+", "部分＋")
        ):
            return "partial_positive"
        if "阳性" in result or "+" in result or "＋" in result:
            return "positive"
        if "阴性" in result or "-" in result or "－" in result:
            return "negative"
        return "mentioned_result_unclear"

    immunohistochemistry = {
        key: value
        for key, value in {
            "CD20": marker_result("CD20"),
            "CD3": marker_result("CD3"),
            "Ki-67": f"{ki67_match.group('value')}%" if ki67_match else None,
        }.items()
        if value is not None
    }
    ki67_details = None
    if ki67_match:
        ki67_details = {
            "value_percent": float(ki67_match.group("value")),
            "qualifier": (
                "approximately"
                if "约" in ki67_match.group("prefix")
                else "exact_not_stated"
            ),
            "reported_positive": any(
                mark in ki67_match.group(0) for mark in ("+", "＋", "阳性")
            ),
            "original_expression": ki67_match.group(0),
        }
    normalized_text = re.sub(r"\s+", "", text)
    recommendations = [
        match.group(0).rstrip("。；")
        for match in re.finditer(r"[^。；]*建议[^。；]*", normalized_text)
        if match.group(0)
    ]
    primary_recommendation = next(
        (item for item in reversed(recommendations) if "再次取材" in item),
        recommendations[-1] if recommendations else None,
    )
    site_detail_match = re.search(r"[（(](?P<site>[左右]侧颈部[ⅠⅡⅢⅣⅤⅥIVX]+区淋巴结)[）)]", text)
    fragment_match = re.search(
        r"(?P<text>送检[^。；\n]{0,30}?(?:碎组织|组织)[^。；\n]{0,20}?直径\s*(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm))",
        text,
        re.IGNORECASE,
    )
    payload = {
        "examination_date": examination_date,
        "specimen_date": dates.get("specimen_date"),
        "report_date": dates.get("report_date"),
        "supplement_date": dates.get("supplement_date"),
        "specimen_type": next(
            (word for word in ("活检", "切除标本", "穿刺") if word in text), None
        ),
        "specimen_site": site,
        "specimen_site_detail": site_detail_match.group("site") if site_detail_match else None,
        "laterality": "左" if "左侧" in text else "右" if "右侧" in text else None,
        "procedure_type": next((word for word in ("穿刺", "活检", "切除") if word in text), None),
        "pathology_description": text,
        "diagnosis_text": text,
        "malignancy_status": malignancy,
        "grade": None,
        "margin_status": None,
        "sample_adequacy": "limited" if limited_sample else "not_stated",
        "immunohistochemistry": immunohistochemistry,
        "immunohistochemistry_details": {"Ki-67": ki67_details} if ki67_details else {},
        "molecular_findings": None,
        "recommendation": primary_recommendation,
        "recommendations": recommendations,
        "specimen_fragment_measurements": (
            [
                {
                    "size": float(fragment_match.group("size")),
                    "unit": fragment_match.group("unit").lower(),
                    "measurement_target": "submitted_tissue_fragment",
                    "not_lesion_size": True,
                    "original_text": fragment_match.group("text"),
                }
            ]
            if fragment_match
            else []
        ),
    }
    return [
        {
            "id": _candidate_id(document_hash, "pathology", 0, payload),
            "candidate_type": "pathology",
            "payload": payload,
            "original_text": text,
            "original_offset": 0,
            "confidence": 0.92 if malignancy != "not_stated" else 0.72,
        }
    ]


def _clinical_opinion_candidate(text: str, document_hash: str) -> list[dict[str, Any]]:
    if not any(word in text for word in ("门诊诊断", "医生意见", "处理意见", "专科意见")):
        return []
    if re.search(r"(?:已|明确)排除", text):
        status = "excluded"
    elif "建议排除" in text:
        status = "unclear"
    elif re.search(r"(?:确诊|明确诊断)", text):
        status = "confirmed"
    elif re.search(r"(?:疑似|怀疑)", text):
        status = "suspected"
    elif "考虑" in text:
        status = "considered"
    elif "可能性小" in text:
        status = "less_likely"
    elif "既往" in text:
        status = "historical"
    else:
        status = "unclear"
    recommendation = next((line.strip() for line in text.splitlines() if "建议" in line), None)
    payload = {
        "clinician_specialty": None,
        "assessment_text": text,
        "diagnosis_status": status,
        "recommendation_text": recommendation,
        "recommended_test": next(
            (
                test
                for test in ("CT", "MRI", "超声", "病理")
                if recommendation and test in recommendation
            ),
            None,
        ),
        "followup_interval": None,
        "medication_or_treatment": None,
        "uncertainty_text": "建议排除并不等于已经排除" if "建议排除" in text else None,
    }
    return [
        {
            "id": _candidate_id(document_hash, "clinical_opinion", 0, payload),
            "candidate_type": "clinical_opinion",
            "payload": payload,
            "original_text": text,
            "original_offset": 0,
            "confidence": 0.88,
        }
    ]


def _followup_candidates(
    text: str, document_hash: str, examination_date: str | None
) -> list[dict[str, Any]]:
    match = re.search(r"建议\s*(\d+)\s*(?:至|到|[-~])\s*(\d+)\s*个?月(?:后)?复查", text)
    if not match:
        match = re.search(r"(\d+)\s*个?月后(?:复查|复诊)", text)
    if not match:
        return []
    minimum, maximum = (
        int(match[1]),
        int(match[2]) if match.lastindex and match.lastindex >= 2 else int(match[1]),
    )
    payload = {
        "title": "报告建议复查",
        "category": "imaging_followup",
        "interval_months_min": minimum,
        "interval_months_max": maximum,
        "base_date": examination_date,
        "original_due_text": match.group(0),
        "recommendation_source_type": "clinician_opinion",
    }
    return [
        {
            "id": _candidate_id(document_hash, "followup_plan", match.start(), payload),
            "candidate_type": "followup_plan",
            "payload": payload,
            "original_text": match.group(0),
            "original_offset": match.start(),
            "confidence": 0.94 if examination_date else 0.78,
        }
    ]


def parse_medical_report(text: str, document_hash: str) -> ParsedReport:
    report_type, confidence = _classify(text)
    dates = _date_contexts(text)
    fallback_date = _date(text)
    if report_type == "procedure":
        examination_date = dates["procedure_date"] or dates["examination_date"] or fallback_date
    elif report_type == "pathology":
        examination_date = (
            dates["report_date"]
            or dates["specimen_date"]
            or dates["examination_date"]
            or fallback_date
        )
    elif report_type == "laboratory":
        examination_date = (
            dates["examination_date"]
            or dates["collection_date"]
            or dates["report_date"]
            or fallback_date
        )
    else:
        examination_date = dates["examination_date"] or dates["report_date"] or fallback_date
    institution_match = re.search(r"^\s*([^\n]{2,40}(?:医院|医学中心|检验所))", text, re.MULTILINE)
    title = next((line.strip() for line in text.splitlines() if line.strip()), None)
    candidates = _lab_candidates(text, document_hash, examination_date, dates)
    candidates.extend(
        _imaging_candidates(text, document_hash, report_type, examination_date, dates)
    )
    candidates.extend(
        _procedure_candidate(
            text, document_hash, report_type, dates["procedure_date"] or examination_date
        )
    )
    candidates.extend(
        _pathology_candidate(text, document_hash, report_type, examination_date, dates)
    )
    candidates.extend(_clinical_opinion_candidate(text, document_hash))
    candidates.extend(_followup_candidates(text, document_hash, examination_date))
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
    if dates["unassigned_dates"]:
        uncertainties.append("存在未能可靠归类为检查、取材、报告或补充报告日期的日期")
    return ParsedReport(
        report_type=report_type,
        classification_confidence=confidence,
        examination_date=examination_date,
        dates=dates,
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
