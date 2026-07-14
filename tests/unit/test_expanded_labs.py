from health_agent.parsers.medical_report import parse_medical_report


def items(text: str) -> dict[str, dict[str, object]]:
    parsed = parse_medical_report(text, "fictional-expanded-labs")
    return {
        item["payload"]["item_name"]: item["payload"]
        for item in parsed.candidates
        if item["candidate_type"] == "laboratory_result"
    }


def test_liver_and_kidney_aliases_preserve_units_and_ranges() -> None:
    result = items(
        "检查日期 2026-07-01\n"
        "ALT 32 U/L 7-40\nAST 25 U/L 13-35\n总胆红素 12.5 µmol/L 5-21\n"
        "肌酐 68 µmol/L 45-84\neGFR 105 mL/min/1.73m2 90-200\n胱抑素C 0.72 mg/L 0.5-1.1"
    )
    assert result["丙氨酸氨基转移酶"]["unit"] == "U/L"
    assert result["总胆红素"]["reference_high"] == 21.0
    assert result["估算肾小球滤过率"]["unit"] == "mL/min/1.73m2"
    assert result["胱抑素C"]["value"] == 0.72


def test_thyroid_and_inflammation_aliases_do_not_conflate_items() -> None:
    result = items(
        "检查日期 2026-07-02\n"
        "TSH 2.1 mIU/L 0.27-4.2\nFT3 4.8 pmol/L 3.1-6.8\nFT4 16.2 pmol/L 12-22\n"
        "TPOAb 12 IU/L 0-34\n超敏CRP 0.8 mg/L 0-3\n降钙素原 0.03 ng/mL 0-0.05"
    )
    assert result["促甲状腺激素"]["value"] == 2.1
    assert result["游离三碘甲状腺原氨酸"]["value"] == 4.8
    assert result["游离甲状腺素"]["value"] == 16.2
    assert result["超敏CRP"]["value"] == 0.8
    assert result["降钙素原"]["reference_high"] == 0.05
