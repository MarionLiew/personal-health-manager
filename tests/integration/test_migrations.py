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
    assert [item.version for item in pending_migrations(engine)] == [1, 2]
    assert upgrade(engine) == [1, 2]
    assert current_version(engine) == 2
    assert verify_database(engine)["valid"] is True


def test_version_one_upgrades_to_two_and_preserves_records(isolated_env: Path) -> None:
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
    assert upgrade(engine, backup_path=backup) == [2]
    assert "record_candidates" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT operation FROM audit_logs WHERE id='preserved'")
            ).scalar()
            == "fictional.test"
        )


def test_repeated_upgrade_has_no_side_effect(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    upgrade(engine)
    with engine.connect() as connection:
        count_before = connection.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar()
    assert upgrade(engine) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar() == count_before


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
            migrations=(*MIGRATIONS, Migration(3, "fictional_failure", fail)),
            backup_path=backup,
        )
    replacement = build_engine(isolated_env)
    assert current_version(replacement) == 2
    assert "should_not_survive" not in inspect(replacement).get_table_names()
