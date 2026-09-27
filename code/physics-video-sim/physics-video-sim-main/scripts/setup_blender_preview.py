"""Install Blender 3.6 preview dependencies into a project-local cache."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


REQUIREMENTS = (
    "absl-py==2.1.0",
    "etils==1.9.4",
    "imageio==2.37.0",
    "importlib-resources==6.5.2",
    "joblib==1.4.2",
    "munch==4.0.0",
    "OpenEXR==3.3.2",
    "packaging==24.2",
    "pillow==11.1.0",
    "pypng==0.20220715.0",
    "pyquaternion==0.9.9",
    "PyYAML==6.0.2",
    "scikit-learn==1.3.2",
    "scipy==1.10.1",
    "threadpoolctl==3.5.0",
    "traitlets==5.14.3",
    "trimesh==4.6.1",
    "typing-extensions==4.12.2",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/local.yaml"))
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config_path = args.config if args.config.is_absolute() else project_root / args.config
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    target = Path(config["paths"]["blender_python_packages"])
    if not target.is_absolute():
        target = project_root / target
    target.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        raise RuntimeError("The local Blender 3.6 preview bootstrap currently targets Windows x64")
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(target),
        "--platform",
        "win_amd64",
        "--python-version",
        "3.10",
        "--implementation",
        "cp",
        "--abi",
        "cp310",
        "--only-binary=:all:",
        "--no-deps",
        *REQUIREMENTS,
    ]
    return subprocess.run(command, cwd=project_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
