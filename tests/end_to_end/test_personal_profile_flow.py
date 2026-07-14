from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy import func, select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.models import AuditLog, LesionImage, PersonalCondition
from health_agent.database.session import session_scope
from tests.integration.test_structured_records import candidates, import_fixture

runner = CliRunner()


def invoke(arguments: list[str]) -> dict:
    result = runner.invoke(app, [*arguments, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["data"]


def add_condition(name: str, category: str, status: str, monitoring: str) -> str:
    preview = invoke(
        [
            "profile",
            "condition-add",
            "--name",
            name,
            "--category",
            category,
            "--status",
            status,
            "--monitoring-json",
            monitoring,
            "--dry-run",
        ]
    )
    assert "id" not in preview
    confirmed = invoke(
        [
            "profile",
            "condition-add",
            "--name",
            name,
            "--category",
            category,
            "--status",
            status,
            "--monitoring-json",
            monitoring,
            "--confirm",
        ]
    )
    return str(confirmed["id"])


def test_fictional_long_term_profile_prioritizes_management_not_diagnosis(
    isolated_env: Path,
) -> None:
    staged: list[Path] = []
    try:
        scar_condition = add_condition(
            "下颌角瘢痕管理",
            "scar_disorder",
            "recurrent",
            '{"next_attention":"观察是否继续增生及疼痛瘙痒变化"}',
        )
        hpv_condition = add_condition(
            "HPV相关皮损随访",
            "viral_infection",
            "active",
            '{"next_attention":"观察治疗后新生长、出血、颜色改变和持续复发"}',
        )

        scar = invoke(
            [
                "profile",
                "scar-add",
                "--condition-id",
                scar_condition,
                "--location",
                "左下颌角",
                "--scar-type",
                "瘢痕疙瘩/增生性瘢痕候选",
                "--previous-treatment",
                "第一次同位素治疗,第二次同位素治疗",
                "--recurrence",
                "--size-change",
                "治疗后缩小后再次增大",
                "--color-change",
                "稳定",
                "--hardness-change",
                "较硬",
                "--symptoms",
                "瘙痒,轻度疼痛",
                "--dry-run",
            ]
        )
        assert "id" not in scar
        scar = invoke(
            [
                "profile",
                "scar-add",
                "--condition-id",
                scar_condition,
                "--location",
                "左下颌角",
                "--scar-type",
                "瘢痕疙瘩/增生性瘢痕候选",
                "--previous-treatment",
                "第一次同位素治疗,第二次同位素治疗",
                "--recurrence",
                "--size-change",
                "治疗后缩小后再次增大",
                "--color-change",
                "稳定",
                "--hardness-change",
                "较硬",
                "--symptoms",
                "瘙痒,轻度疼痛",
                "--confirm",
            ]
        )
        for treatment_date in ("2025-03-10", "2025-10-12"):
            invoke(
                [
                    "profile",
                    "treatment-add",
                    "--condition-id",
                    scar_condition,
                    "--target-type",
                    "scar",
                    "--target-id",
                    str(scar["id"]),
                    "--type",
                    "同位素治疗",
                    "--date",
                    treatment_date,
                    "--response",
                    "治疗后进入观察",
                    "--confirm",
                ]
            )

        hpv_lesions: list[str] = []
        for location, relation in (
            ("腋窝", "confirmed"),
            ("颈部", "suspected"),
            ("眼睑", "uncertain"),
        ):
            lesion = invoke(
                [
                    "profile",
                    "hpv-add",
                    "--condition-id",
                    hpv_condition,
                    "--location",
                    location,
                    "--lesion-type",
                    "疣样皮损" if location != "眼睑" else "疑似疣样皮损",
                    "--hpv-related",
                    relation,
                    "--recurrence",
                    "observing",
                    "--status",
                    "improving",
                    "--confirm",
                ]
            )
            hpv_lesions.append(str(lesion["id"]))
        for date in ("2026-04-18", "2026-06-28"):
            invoke(
                [
                    "profile",
                    "treatment-add",
                    "--condition-id",
                    hpv_condition,
                    "--target-type",
                    "hpv",
                    "--target-id",
                    hpv_lesions[0],
                    "--type",
                    "激光治疗",
                    "--date",
                    date,
                    "--response",
                    "治疗后恢复期观察",
                    "--confirm",
                ]
            )

        for index, date in enumerate(("2026-04-17", "2026-07-28", "2026-12-28"), start=1):
            path = ROOT / "data/imports" / f"fictional-lesion-{uuid.uuid4()}.png"
            path.write_bytes(b"fictional-png-content-" + bytes([index]))
            staged.append(path)
            image = invoke(
                [
                    "profile",
                    "image-add",
                    str(path),
                    "--condition-id",
                    hpv_condition,
                    "--lesion-type",
                    "hpv",
                    "--lesion-id",
                    hpv_lesions[0],
                    "--taken-date",
                    date,
                    "--body-location",
                    "腋窝",
                    "--comparison-group",
                    "fictional-axilla-followup",
                    "--size-description",
                    f"虚构大小记录{index}",
                    "--count-description",
                    f"虚构数量记录{index}",
                    "--appearance-description",
                    f"虚构外观记录{index}",
                    "--confirm",
                ]
            )
            staged.append(
                ROOT / "data/reports/profile-images" / f"{image['image_hash']}{path.suffix}"
            )

        lab_path, lab_import = import_fixture("fictional_lab_1.txt")
        staged.append(lab_path)
        wbc = next(
            item
            for item in candidates(lab_import["data"]["import_id"])
            if item["payload"].get("item_name") == "白细胞"
        )
        invoke(
            [
                "record",
                "confirm-candidates",
                lab_import["data"]["import_id"],
                "--candidate-ids",
                wbc["id"],
            ]
        )
        invoke(
            [
                "profile",
                "immune-add",
                "--infections-json",
                '[{"name":"HPV相关皮损治疗史","source_type":"user_report"}]',
                "--laboratory-ids",
                str(wbc["formal_record_id"] or "confirmed-by-import"),
                "--observations",
                "未记录持续严重感染证据",
                "--monitoring-items",
                "皮损复发频率,血常规趋势",
                "--confirm",
            ]
        )
        invoke(
            [
                "profile",
                "risk-add",
                "--name",
                "体重与力量训练",
                "--group",
                "modifiable",
                "--category",
                "weight_and_strength",
                "--current-state",
                "需要长期趋势数据",
                "--management-action",
                "按周观察体重并规律力量训练",
                "--monitoring-metric",
                "体重长期趋势与训练频率",
                "--confirm",
            ]
        )

        conditions_data = invoke(["profile", "conditions"])["conditions"]
        skin = invoke(["profile", "skin"])["skin"]
        timeline = invoke(["profile", "timeline"])["events"]
        image_comparison = invoke(
            ["profile", "image-compare", "--group", "fictional-axilla-followup"]
        )["comparison"]
        infections = invoke(["profile", "infections"])["infection_context"]
        priorities = invoke(["profile", "priorities"])["priorities"]
        profile = invoke(["profile", "summary"])["profile"]

        assert len(conditions_data) == 2
        assert len(skin["scar_lesions"]) == 1
        assert len(skin["hpv_lesions"]) == 3
        assert skin["hpv_lesions"][0]["photos_available"] is True
        assert len(skin["treatments"]) == 4
        assert skin["hpv_lesions"][0]["laser_dates"] == ["2026-04-18", "2026-06-28"]
        assert len(skin["images"]) == 3
        assert all(image["diagnostic_interpretation"] is None for image in skin["images"])
        assert len(image_comparison["images"]) == 3
        assert image_comparison["automatic_diagnosis"] is None
        assert any(event["date"].startswith("2026-06-28") for event in timeline)
        assert infections["laboratory_trends"][0]["item"] == "白细胞"
        assert priorities[0]["focus"] == "HPV相关皮损随访"
        assert len(priorities) == 3
        assert priorities[2]["focus"] == "体重与力量训练"
        serialized = json.dumps(profile, ensure_ascii=False)
        assert "癌症概率" not in serialized
        assert "免疫力评分" not in serialized
        assert "炎症评分" not in serialized

        with session_scope() as session:
            assert session.scalar(select(func.count()).select_from(PersonalCondition)) == 2
            assert session.scalar(select(func.count()).select_from(LesionImage)) == 3
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.operation.like("profile.%"))
                )
                >= 15
            )
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
