from health_agent.config import ROOT
from health_agent.parsers.medical_report import parse_medical_report


def test_chinese_lab_report_extracts_provenance_and_ranges() -> None:
    text = (ROOT / "tests/fixtures/fictional_lab_1.txt").read_text(encoding="utf-8")
    parsed = parse_medical_report(text, "a" * 64)
    assert parsed.report_type == "laboratory"
    assert parsed.examination_date == "2026-01-10"
    assert parsed.institution == "虚构市第一医院"
    wbc = next(item for item in parsed.candidates if item["payload"]["item_name"] == "白细胞")
    assert wbc["payload"]["value"] == 3.6
    assert wbc["payload"]["reference_low"] == 3.9
    assert wbc["payload"]["abnormal_flag"] == "low"
    assert wbc["original_offset"] >= 0


def test_ct_report_extracts_lesion_but_does_not_claim_diagnosis() -> None:
    text = (ROOT / "tests/fixtures/fictional_ct_1.txt").read_text(encoding="utf-8")
    parsed = parse_medical_report(text, "b" * 64)
    assert parsed.report_type == "ct"
    lesion = next(item for item in parsed.candidates if item["candidate_type"] == "lesion")
    assert lesion["payload"]["laterality"] == "右"
    assert lesion["payload"]["anatomical_location"] == "上叶"
    assert lesion["payload"]["size"] == 6
    assert "diagnosis" not in lesion["payload"]
