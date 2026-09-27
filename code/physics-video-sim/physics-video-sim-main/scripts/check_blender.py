"""Run the project's minimal Blender integration check from a YAML config."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


SMOKE_MARKER = "PHYSIM_BLENDER_SMOKE="


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/local.yaml"))
    return parser.parse_args()


def load_blender_path(config_path: Path, project_root: Path) -> Path:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    configured_path = config.get("paths", {}).get("blender_executable")
    if not configured_path:
        raise ValueError(f"Missing paths.blender_executable in {config_path}")

    blender_path = Path(configured_path)
    if not blender_path.is_absolute():
        blender_path = project_root / blender_path
    blender_path = blender_path.resolve()

    if not blender_path.is_file():
        raise FileNotFoundError(f"Configured Blender executable does not exist: {blender_path}")
    return blender_path


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config_path = args.config
    if not config_path.is_absolute():
        config_path = project_root / config_path
    config_path = config_path.resolve()

    blender_path = load_blender_path(config_path, project_root)
    smoke_script = project_root / "scripts" / "blender_smoke_test.py"
    command = [
        str(blender_path),
        "--background",
        "--factory-startup",
        "--python",
        str(smoke_script),
    ]
    completed = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    output = completed.stdout + completed.stderr
    print(output, end="")
    if completed.returncode != 0:
        return completed.returncode
    if SMOKE_MARKER not in output:
        print("Blender exited successfully but did not emit the smoke-test marker.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
