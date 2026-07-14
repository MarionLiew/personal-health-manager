from __future__ import annotations

from pathlib import Path

import yaml

from health_agent.config import ROOT


def safety_policy() -> dict[str, object]:
    path = Path(ROOT, "config", "medical_safety.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def fixed_boundaries() -> tuple[str, ...]:
    return tuple(str(value) for value in safety_policy()["fixed_boundaries"])
