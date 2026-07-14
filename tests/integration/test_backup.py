from __future__ import annotations

from cryptography.fernet import Fernet

from health_agent.database.migrations import migrate
from health_agent.database.session import build_engine
from health_agent.services.backup import create_backup, read_backup, restore_to_new_file


def test_encrypted_backup_verifies_and_restore_never_overwrites(isolated_env) -> None:
    engine = build_engine(isolated_env)
    migrate(engine)
    key = Fernet.generate_key().decode()
    backup = create_backup(isolated_env, isolated_env.parent, key)
    manifest, database = read_backup(backup, key)
    assert manifest["schema_version"] == 3
    assert database
    restored = isolated_env.parent / "restored.sqlite3"
    restore_to_new_file(backup, restored, key)
    assert restored.exists()
