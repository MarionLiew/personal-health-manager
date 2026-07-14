from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from health_agent.cli.main import app
from tests.integration.test_structured_records import candidates, import_fixture

runner = CliRunner()


def invoke(arguments: list[str]) -> dict:
    result = runner.invoke(app, [*arguments, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["data"]


def test_fictional_symptom_followup_and_visit_workflow(isolated_env: Path) -> None:
    staged: list[Path] = []
    try:
        preview = invoke(
            [
                "symptoms",
                "add",
                "--name",
                "咽喉疼痛",
                "--location",
                "咽喉",
                "--side",
                "右",
                "--started",
                "2026-07-01",
                "--severity",
                "4",
                "--dry-run",
            ]
        )
        assert "id" not in preview
        symptom = invoke(
            [
                "symptoms",
                "add",
                "--name",
                "咽喉疼痛",
                "--location",
                "咽喉",
                "--side",
                "右",
                "--started",
                "2026-07-01",
                "--severity",
                "4",
                "--confirm",
            ]
        )
        symptom_id = symptom["id"]
        invoke(
            [
                "symptoms",
                "update",
                symptom_id,
                "--status",
                "improving",
                "--observed",
                "2026-07-04",
                "--severity",
                "2",
                "--confirm",
            ]
        )
        invoke(["symptoms", "reopen", symptom_id, "--confirm"])
        timeline = invoke(["symptoms", "timeline", "--location", "咽喉"])
        assert timeline["episodes"][0]["status"] == "recurrent"

        chinese_due = invoke(
            [
                "followup",
                "add",
                "--title",
                "虚构复诊",
                "--due",
                "三个月后",
                "--base-date",
                "2026-07-01",
                "--dry-run",
            ]
        )
        assert chinese_due["due_date"].startswith("2026-10-01")

        followup_path, imported = import_fixture("fictional_ent_followup.txt")
        staged.append(followup_path)
        followup_candidate = next(
            item
            for item in candidates(imported["data"]["import_id"])
            if item["type"] == "followup_plan"
        )
        confirmed = invoke(
            [
                "record",
                "confirm-candidates",
                imported["data"]["import_id"],
                "--candidate-ids",
                followup_candidate["id"],
            ]
        )
        followup_id = confirmed["formal_record_ids"][0]
        plan = invoke(["followup", "show", followup_id])
        assert plan["due_date"] is None
        assert plan["due_date_start"].startswith("2027-01-01")
        assert plan["due_date_end"].startswith("2027-07-01")
        invoke(
            [
                "followup",
                "postpone",
                followup_id,
                "--date",
                "2027-08-01",
                "--reason",
                "等待复诊安排",
                "--confirm",
            ]
        )
        invoke(
            [
                "followup",
                "complete",
                followup_id,
                "--record-id",
                imported["data"]["source_document_id"],
                "--confirm",
            ]
        )
        assert invoke(["followup", "show", followup_id])["status"] == "completed"

        appointment_preview = invoke(
            [
                "appointments",
                "add",
                "--department",
                "耳鼻喉科",
                "--start",
                "2027-08-02T09:00:00+08:00",
                "--purpose",
                "复查右侧咽喉症状",
                "--followup-ids",
                followup_id,
                "--dry-run",
            ]
        )
        assert "id" not in appointment_preview
        appointment = invoke(
            [
                "appointments",
                "add",
                "--department",
                "耳鼻喉科",
                "--start",
                "2027-08-02T09:00:00+08:00",
                "--purpose",
                "复查右侧咽喉症状",
                "--followup-ids",
                followup_id,
                "--confirm",
            ]
        )
        assert invoke(["appointments", "show", appointment["id"]])["status"] == "scheduled"
        assert invoke(["appointments", "upcoming"])["appointments"][0]["id"] == appointment["id"]

        opinion_path, opinion_import = import_fixture("fictional_clinician_opinion.txt")
        pathology_path, pathology_import = import_fixture("fictional_pathology_negative.txt")
        staged.extend([opinion_path, pathology_path])
        opinion = next(
            item
            for item in candidates(opinion_import["data"]["import_id"])
            if item["type"] == "clinical_opinion"
        )
        pathology = next(
            item
            for item in candidates(pathology_import["data"]["import_id"])
            if item["type"] == "pathology"
        )
        assert opinion["payload"]["diagnosis_status"] == "unclear"
        assert pathology["payload"]["malignancy_status"] == "negative"
        for imported_data, candidate in (
            (opinion_import, opinion),
            (pathology_import, pathology),
        ):
            invoke(
                [
                    "record",
                    "confirm-candidates",
                    imported_data["data"]["import_id"],
                    "--candidate-ids",
                    candidate["id"],
                ]
            )
        visit = invoke(["visit-summary", "--department", "耳鼻喉科"])
        assert visit["current_priority_symptoms"][0]["id"] == symptom_id
        assert visit["clinician_opinions"][0]["source_type"] == "clinician_opinion"
        assert visit["confirmed_pathology"][0]["details"]["malignancy_status"] == "negative"
        questions = invoke(["doctor-questions", "--department", "耳鼻喉科"])
        assert 0 < len(questions["questions"]) <= 8
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
