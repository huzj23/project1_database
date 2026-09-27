"""Configuration loading and deterministic deep merge."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_run_config(
    environment_path: str | Path, scenario: str | None = None
) -> dict[str, Any]:
    environment_path = Path(environment_path).resolve()
    environment = load_yaml(environment_path)
    project_root = environment_path.parent.parent
    scenario_value = (
        Path("configs") / "scenarios" / f"{scenario}.yaml"
        if scenario is not None
        else Path(environment["project"]["scenario_config"])
    )
    scenario_path = Path(scenario_value)
    if not scenario_path.is_absolute():
        scenario_path = project_root / scenario_path
    return deep_merge(load_yaml(scenario_path), environment)
