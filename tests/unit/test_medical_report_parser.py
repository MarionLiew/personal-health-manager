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


def test_ultrasound_multiple_lymph_node_range_is_not_an_individual_lesion() -> None:
    text = """虚构超声报告
检查日期：2026-04-10
超声所见：双侧颈部多个淋巴结，直径约0.5cm–2.6cm，形态规则。甲状腺未见异常。
超声提示：颈部淋巴结考虑反应性。
"""

    parsed = parse_medical_report(text, "c" * 64)

    assert parsed.report_type == "ultrasound"
    assert not [item for item in parsed.candidates if item["candidate_type"] == "lesion"]
    imaging = next(
        item for item in parsed.candidates if item["candidate_type"] == "imaging_report"
    )
    measurement = imaging["payload"]["aggregate_measurements"][0]
    assert measurement == {
        "structure": "颈部淋巴结",
        "minimum": 0.5,
        "maximum": 2.6,
        "unit": "cm",
        "scope": "multiple_bilateral_nodes",
        "individual_lesion_trackable": False,
    }
    assert "甲状腺未见异常" in imaging["payload"]["findings_text"]
    assert "考虑反应性" in imaging["payload"]["impression_text"]


def test_ultrasound_guided_core_biopsy_is_a_procedure_not_imaging_report() -> None:
    text = """虚构介入超声操作记录
操作日期：2026-04-11
超声引导下右侧颈部II区淋巴结粗针穿刺活检，使用18G针，共进针4次，取得组织4条。
"""

    parsed = parse_medical_report(text, "d" * 64)

    assert parsed.report_type == "procedure"
    assert {item["candidate_type"] for item in parsed.candidates} == {"procedure"}
    payload = parsed.candidates[0]["payload"]
    assert payload["procedure_type"] == "core_needle_biopsy"
    assert payload["needle_gauge"] == 18
    assert payload["pass_count"] == 4
    assert payload["specimen_count"] == 4
    assert payload["laterality"] == "右"


def test_supplemental_pathology_does_not_create_imaging_or_lesion_candidate() -> None:
    text = """虚构病理补充报告
取材日期：2026-04-11
报告日期：2026-04-12
补充报告日期：2026-04-18
右侧颈部淋巴结穿刺组织仅见少量淋巴组织。
免疫组化：CD20部分阳性，CD3部分阳性，Ki-67约20%。
结合形态考虑反应性增生，诊断肿瘤证据不足；因取材较少，必要时再次取材。
"""

    parsed = parse_medical_report(text, "e" * 64)

    assert parsed.report_type == "pathology"
    assert parsed.examination_date == "2026-04-12"
    assert parsed.dates == {
        "examination_date": None,
        "procedure_date": None,
        "specimen_date": "2026-04-11",
        "collection_date": None,
        "received_date": None,
        "report_date": "2026-04-12",
        "supplement_date": "2026-04-18",
        "all_dates": ["2026-04-11", "2026-04-12", "2026-04-18"],
        "unassigned_dates": [],
    }
    assert {item["candidate_type"] for item in parsed.candidates} == {"pathology"}
    payload = parsed.candidates[0]["payload"]
    assert payload["sample_adequacy"] == "limited"
    assert payload["malignancy_status"] == "insufficient_evidence"
    assert payload["immunohistochemistry"]["Ki-67"] == "20%"
    assert payload["specimen_date"] == "2026-04-11"
    assert payload["supplement_date"] == "2026-04-18"


def test_layout_coagulation_report_extracts_six_results_and_dates() -> None:
    text = (ROOT / "tests/fixtures/fictional_coagulation_layout.txt").read_text(
        encoding="utf-8"
    )

    parsed = parse_medical_report(text, "f" * 64)

    assert parsed.report_type == "laboratory"
    assert parsed.dates["collection_date"] == "2026-05-06"
    assert parsed.dates["received_date"] == "2026-05-06"
    assert parsed.dates["report_date"] == "2026-05-06"
    labs = [item for item in parsed.candidates if item["candidate_type"] == "laboratory_result"]
    assert len(labs) == 6
    assert {item["payload"]["item_name"] for item in labs} == {
        "凝血酶原时间",
        "凝血酶原活动度",
        "国际标准化比值",
        "活化部分凝血活酶时间",
        "凝血酶时间",
        "纤维蛋白原",
    }


def test_layout_cbc_uses_result_column_not_sequence_number() -> None:
    text = (ROOT / "tests/fixtures/fictional_cbc_layout.txt").read_text(encoding="utf-8")

    parsed = parse_medical_report(text, "1" * 64)
    values = {
        item["payload"]["item_name"]: item["payload"]["value"]
        for item in parsed.candidates
        if item["candidate_type"] == "laboratory_result"
    }

    assert parsed.report_type == "laboratory"
    assert values["白细胞"] == 4.21
    assert values["淋巴细胞绝对值"] == 1.27
    assert values["红细胞"] == 5.02
    assert values["血小板压积"] == 0.238
    assert not [item for item in parsed.candidates if item["candidate_type"] == "imaging_report"]


def test_endoscopy_blank_pathology_template_and_rsi_do_not_create_false_candidates() -> None:
    text = (ROOT / "tests/fixtures/fictional_endoscopy_template.txt").read_text(
        encoding="utf-8"
    )

    parsed = parse_medical_report(text, "2" * 64)

    assert parsed.report_type == "endoscopy"
    assert {item["candidate_type"] for item in parsed.candidates} == {"imaging_report"}
    payload = parsed.candidates[0]["payload"]
    assert payload["modality"] == "ENDOSCOPY"
    assert payload["endoscopy_type"] == "laryngoscopy"
    assert payload["endoscopy_scores"] == {"RFS": 4, "RSI": 5}
    assert "病理编号" not in payload["findings_text"]


def test_mr_abbreviation_is_mri_and_sections_and_dates_stay_distinct() -> None:
    text = (ROOT / "tests/fixtures/fictional_mr_report.txt").read_text(encoding="utf-8")

    parsed = parse_medical_report(text, "3" * 64)

    assert parsed.report_type == "mri"
    assert parsed.dates["examination_date"] == "2026-05-09"
    assert parsed.dates["report_date"] == "2026-05-10"
    payload = parsed.candidates[0]["payload"]
    assert payload["body_region"] == "鼻咽部"
    assert "未见明确占位" in payload["findings_text"]
    assert payload["impression_text"] == "示例轻微改变，建议结合临床。"


def test_short_lab_aliases_do_not_match_rsi_or_pct_as_ct() -> None:
    parsed = parse_medical_report(
        "虚构喉镜检查报告单 检查日期：2026-05-11\nRSI症状评分：7分。\n内镜诊断：示例。",
        "4" * 64,
    )

    assert parsed.report_type == "endoscopy"
    assert not [item for item in parsed.candidates if item["candidate_type"] == "laboratory_result"]
