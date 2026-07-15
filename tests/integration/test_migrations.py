from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, inspect, text

from health_agent.database.migrations import (
    MIGRATIONS,
    Migration,
    current_version,
    pending_migrations,
    upgrade,
    verify_database,
)
from health_agent.database.session import build_engine


def test_empty_database_upgrades_through_every_version(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    assert [item.version for item in pending_migrations(engine)] == [1, 2, 3, 4, 5, 6]
    assert upgrade(engine) == [1, 2, 3, 4, 5, 6]
    assert current_version(engine) == 6
    assert verify_database(engine)["valid"] is True


def test_version_one_upgrades_through_three_and_preserves_records(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    assert upgrade(engine, migrations=MIGRATIONS[:1]) == [1]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs(id, operation, actor, status, metadata_json, occurred_at) "
                "VALUES ('preserved', 'fictional.test', 'pytest', 'success', '{}', "
                "CURRENT_TIMESTAMP)"
            )
        )
    backup = isolated_env.parent / "v1-backup.sqlite3"
    assert upgrade(engine, backup_path=backup) == [2, 3, 4, 5, 6]
    assert "record_candidates" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT operation FROM audit_logs WHERE id='preserved'")
            ).scalar()
            == "fictional.test"
        )


def test_version_two_upgrades_to_three_and_preserves_v2_records(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    assert upgrade(engine, migrations=MIGRATIONS[:2]) == [1, 2]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO symptom_episodes("
                "id, patient_id, source_type, extraction_method, extraction_version, verified, "
                "verification_status, created_by, updated_by, details, recorded_at, updated_at"
                ") VALUES ('symptom-v2', 'local-primary', 'user_report', 'manual', '2', 1, "
                "'user_confirmed', 'pytest', 'pytest', :details, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            ),
            {"details": '{"legacy":true}'},
        )
    backup = isolated_env.parent / "v2-backup.sqlite3"
    assert upgrade(engine, backup_path=backup) == [3, 4, 5, 6]
    inspector = inspect(engine)
    assert "symptom_observations" in inspector.get_table_names()
    assert "normalized_symptom_name" in {
        column["name"] for column in inspector.get_columns("symptom_episodes")
    }
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT details, normalized_symptom_name FROM symptom_episodes WHERE id=:id"),
            {"id": "symptom-v2"},
        ).one()
        assert row[0] == '{"legacy":true}'
        assert row[1] is None


def test_version_three_upgrades_to_profile_schema_and_preserves_records(
    isolated_env: Path,
) -> None:
    engine = build_engine(isolated_env)
    assert upgrade(engine, migrations=MIGRATIONS[:3]) == [1, 2, 3]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO follow_up_plans("
                "id, patient_id, source_type, extraction_method, extraction_version, verified, "
                "verification_status, created_by, updated_by, details, recorded_at, updated_at, "
                "title, status) VALUES ('followup-v3', 'local-primary', 'user_report', 'manual', "
                "'3', 1, 'user_confirmed', 'pytest', 'pytest', '{}', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, 'fictional preserved follow-up', 'pending')"
            )
        )
    backup = isolated_env.parent / "v3-backup.sqlite3"
    assert upgrade(engine, backup_path=backup) == [4, 5, 6]
    assert "personal_conditions" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT title FROM follow_up_plans WHERE id='followup-v3'")
            ).scalar()
            == "fictional preserved follow-up"
        )


def test_repeated_upgrade_has_no_side_effect(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    upgrade(engine)
    with engine.connect() as connection:
        count_before = connection.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar()
    assert upgrade(engine) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar() == count_before


def test_version_four_adds_source_institution_and_preserves_documents(
    isolated_env: Path,
) -> None:
    engine = build_engine(isolated_env)
    assert upgrade(engine, migrations=MIGRATIONS[:4]) == [1, 2, 3, 4]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source_documents("
                "id, patient_id, original_filename, local_path, mime_type, file_size, sha256, "
                "imported_at, data_origin, contains_identity, human_confirmed, revoked, "
                "institution_verified, recorded_at, updated_at"
                ") VALUES ('fictional-source', 'local-primary', 'fictional.pdf', "
                "'/fictional/path', 'application/pdf', 10, :sha256, CURRENT_TIMESTAMP, "
                "'user_document', 0, 1, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"sha256": "f" * 64},
        )
    backup = isolated_env.parent / "v4-backup.sqlite3"

    assert upgrade(engine, backup_path=backup) == [5, 6]
    assert "institution" in {
        column["name"] for column in inspect(engine).get_columns("source_documents")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT original_filename FROM source_documents WHERE id='fictional-source'")
        ).scalar() == "fictional.pdf"


def test_version_five_adds_verified_institution_provenance_and_preserves_value(
    isolated_env: Path,
) -> None:
    engine = build_engine(isolated_env)
    assert upgrade(engine, migrations=MIGRATIONS[:5]) == [1, 2, 3, 4, 5]
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE source_documents DROP COLUMN institution_updated_at"))
        connection.execute(text("ALTER TABLE source_documents DROP COLUMN institution_source_type"))
        connection.execute(text("ALTER TABLE source_documents DROP COLUMN institution_verified"))
        connection.execute(
            text(
                "INSERT INTO source_documents("
                "id, patient_id, original_filename, local_path, mime_type, file_size, sha256, "
                "imported_at, data_origin, contains_identity, human_confirmed, revoked, "
                "institution, recorded_at, updated_at"
                ") VALUES ('fictional-source-v5', 'local-primary', 'fictional.pdf', "
                "'/fictional/path', 'application/pdf', 10, :sha256, CURRENT_TIMESTAMP, "
                "'user_document', 0, 1, 0, '虚构市第一医院', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"sha256": "e" * 64},
        )

    assert upgrade(engine, backup_path=isolated_env.parent / "v5-backup.sqlite3") == [6]
    columns = {column["name"] for column in inspect(engine).get_columns("source_documents")}
    assert {"institution_verified", "institution_source_type", "institution_updated_at"} <= columns
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT institution, institution_verified, institution_source_type "
                "FROM source_documents WHERE id='fictional-source-v5'"
            )
        ).one()
        assert tuple(row) == ("虚构市第一医院", 0, None)


def test_failed_migration_restores_database_and_version(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    upgrade(engine)

    def fail(connection: Connection) -> None:
        connection.execute(text("CREATE TABLE should_not_survive(id INTEGER)"))
        raise RuntimeError("fictional migration failure")

    backup = isolated_env.parent / "pre-failure.sqlite3"
    with pytest.raises(RuntimeError, match="fictional migration failure"):
        upgrade(
            engine,
            migrations=(*MIGRATIONS, Migration(7, "fictional_failure", fail)),
            backup_path=backup,
        )
    replacement = build_engine(isolated_env)
    assert current_version(replacement) == 6
    assert "should_not_survive" not in inspect(replacement).get_table_names()
