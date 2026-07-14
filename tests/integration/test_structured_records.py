from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.models import (
    LaboratoryResult,
    Lesion,
    LesionMeasurement,
    RecordCandidate,
)
from health_agent.database.session import build_engine, session_scope

runner = CliRunner()


def stage_fixture(name: str) -> Path:
    destination = ROOT / "data/imports" / f"{uuid.uuid4()}-{name}"
    shutil.copy2(ROOT / "tests/fixtures" / name, destination)
    return destination


def import_fixture(name: str) -> tuple[Path, dict]:
    path = stage_fixture(name)
    result = runner.invoke(app, ["record", "import", str(path), "--confirm", "--json"])
    assert result.exit_code == 0, result.output
    return path, json.loads(result.output)


def candidates(import_id: str) -> list[dict]:
    result = runner.invoke(app, ["record", "candidates", import_id, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["data"]["candidates"]


def test_lab_candidates_require_partial_confirmation_and_trend_uses_only_confirmed(
    isolated_env: Path,
) -> None:
    path, imported = import_fixture("fictional_lab_1.txt")
    try:
        import_id = imported["data"]["import_id"]
        items = candidates(import_id)
        assert {item["source_type"] for item in items} == {"system_inference"}
        assert {item["payload"]["item_name"] for item in items} >= {
            "白细胞",
            "中性粒细胞绝对值",
            "血清铁",
        }
        selected = [
            item["id"]
            for item in items
            if item["payload"]["item_name"] in {"白细胞", "中性粒细胞绝对值"}
        ]
        result = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                import_id,
                "--candidate-ids",
                ",".join(selected),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            assert session.scalar(select(func.count()).select_from(LaboratoryResult)) == 2
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(RecordCandidate)
                    .where(RecordCandidate.status == "pending")
                )
                == len(items) - 2
            )
        trend = runner.invoke(app, ["labs", "trend", "--item", "白细胞", "--json"])
        payload = json.loads(trend.output)
        assert payload["status"] == "success"
        assert len(payload["data"]["groups"][0]["results"]) == 1
        assert "immune deficiency" in payload["data"]["medical_boundary"]
    finally:
        path.unlink(missing_ok=True)


def test_lesion_link_requires_explicit_id_and_rejects_different_side(isolated_env: Path) -> None:
    first_path, first_import = import_fixture("fictional_ct_1.txt")
    second_path, second_import = import_fixture("fictional_ct_2.txt")
    try:
        first_items = candidates(first_import["data"]["import_id"])
        first_lesion = next(item for item in first_items if item["type"] == "lesion")
        confirmed = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                first_import["data"]["import_id"],
                "--candidate-ids",
                first_lesion["id"],
                "--json",
            ],
        )
        assert confirmed.exit_code == 0, confirmed.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            lesion = session.scalar(select(Lesion))
            assert lesion is not None
            lesion_id = lesion.id
        second_items = candidates(second_import["data"]["import_id"])
        second_lesion = next(item for item in second_items if item["type"] == "lesion")
        linked = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                second_import["data"]["import_id"],
                "--candidate-ids",
                second_lesion["id"],
                "--lesion-id",
                lesion_id,
                "--json",
            ],
        )
        assert linked.exit_code == 0, linked.output
        comparison = runner.invoke(app, ["lesions", "compare", lesion_id, "--json"])
        result = json.loads(comparison.output)["data"]
        assert result["comparable"] is True
        assert len(result["measurements"]) == 2
        assert result["measurement_error_possible"] is True
        with session_scope(engine) as session:
            assert session.scalar(select(func.count()).select_from(Lesion)) == 1
            assert session.scalar(select(func.count()).select_from(LesionMeasurement)) == 2
    finally:
        first_path.unlink(missing_ok=True)
        second_path.unlink(missing_ok=True)


def test_different_side_and_anatomy_cannot_link_to_existing_lesion(isolated_env: Path) -> None:
    first_path, first_import = import_fixture("fictional_ct_1.txt")
    left_path, left_import = import_fixture("fictional_ct_left.txt")
    neck_path, neck_import = import_fixture("fictional_neck_us.txt")
    try:
        first_candidate = next(
            item
            for item in candidates(first_import["data"]["import_id"])
            if item["type"] == "lesion"
        )
        created = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                first_import["data"]["import_id"],
                "--candidate-ids",
                first_candidate["id"],
                "--json",
            ],
        )
        assert created.exit_code == 0, created.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            lesion_id = session.scalar(select(Lesion.id))
        assert lesion_id
        for imported in (left_import, neck_import):
            candidate = next(
                item
                for item in candidates(imported["data"]["import_id"])
                if item["type"] == "lesion"
            )
            rejected = runner.invoke(
                app,
                [
                    "record",
                    "confirm-candidates",
                    imported["data"]["import_id"],
                    "--candidate-ids",
                    candidate["id"],
                    "--lesion-id",
                    lesion_id,
                    "--json",
                ],
            )
            assert rejected.exit_code != 0
        with session_scope(engine) as session:
            assert session.scalar(select(func.count()).select_from(Lesion)) == 1
            assert session.scalar(select(func.count()).select_from(LesionMeasurement)) == 1
    finally:
        first_path.unlink(missing_ok=True)
        left_path.unlink(missing_ok=True)
        neck_path.unlink(missing_ok=True)
