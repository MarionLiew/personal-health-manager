from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from health_agent.errors import ConfigurationError

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    root: Path
    database_path: Path
    data_root: Path
    allowed_import_roots: tuple[Path, ...]
    max_import_bytes: int
    zip_max_files: int
    zip_max_uncompressed_bytes: int
    zip_max_compression_ratio: int


def load_settings(path: str | Path | None = None) -> Settings:
    config_path = Path(path or os.getenv("HEALTH_AGENT_CONFIG", ROOT / "config/default.yaml"))
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Cannot load configuration: {config_path}") from exc
    root = ROOT.resolve()
    db_override = os.getenv("HEALTH_AGENT_DATABASE")

    def under_root(value: str) -> Path:
        candidate = Path(value)
        resolved = (
            (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        )
        if not resolved.is_relative_to(root):
            raise ConfigurationError(f"Configured path is outside project root: {resolved}")
        return resolved

    limits = raw.get("zip_limits", {})
    return Settings(
        root=root,
        database_path=under_root(db_override or raw["database_path"]),
        data_root=under_root(raw.get("data_root", "data")),
        allowed_import_roots=tuple(under_root(p) for p in raw.get("allowed_import_roots", [])),
        max_import_bytes=int(raw.get("max_import_bytes", 1_073_741_824)),
        zip_max_files=int(limits.get("max_files", 10_000)),
        zip_max_uncompressed_bytes=int(limits.get("max_uncompressed_bytes", 2_147_483_648)),
        zip_max_compression_ratio=int(limits.get("max_compression_ratio", 200)),
    )
