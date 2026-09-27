"""Launch a shared server-simulation scene in the local Blender GUI."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import yaml

from check_blender import load_blender_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/local.yaml"))
    parser.add_argument("--scenario", default="rolling")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--save-blend", type=Path)
    parser.add_argument("--sample-root", type=Path)
    parser.add_argument(
        "--background",
        action="store_true",
        help="Build, validate, and save the preview without opening a GUI.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    config_path = args.config
    if not config_path.is_absolute():
        config_path = project_root / config_path
    config_path = config_path.resolve()
    with config_path.open("r", encoding="utf-8") as stream:
        environment_config = yaml.safe_load(stream)

    blender_path = load_blender_path(config_path, project_root)
    seed = int(
        environment_config["project"]["seed"] if args.seed is None else args.seed
    )
    runtime_root = Path(environment_config["paths"]["blender_python_packages"])
    if not runtime_root.is_absolute():
        runtime_root = project_root / runtime_root
    if not runtime_root.is_dir():
        raise FileNotFoundError(
            f"Missing Blender preview runtime {runtime_root}; "
            "run scripts/setup_blender_preview.py first"
        )

    save_blend = args.save_blend
    if save_blend is None:
        template = environment_config["preview"]["save_blend"]
        save_blend = Path(template.format(seed=seed, scenario=args.scenario))
    if not save_blend.is_absolute():
        save_blend = project_root / save_blend
    save_blend = save_blend.resolve()

    sample_root = args.sample_root
    if sample_root is None:
        template = environment_config["preview"]["sample_root"]
        sample_root = Path(template.format(seed=seed, scenario=args.scenario))
    if not sample_root.is_absolute():
        sample_root = project_root / sample_root
    sample_root = sample_root.resolve()
    trajectory_path = sample_root / "trajectory.json"
    if not trajectory_path.is_file():
        raise FileNotFoundError(
            f"Missing server simulation {trajectory_path}; sync the validated sample first"
        )

    command = [str(blender_path), "--factory-startup"]
    if args.background:
        command.append("--background")
    command.extend(
        [
            "--python",
            str(project_root / "scripts" / "blender_preview_scene.py"),
            "--",
            "--config",
            str(config_path),
            "--scenario",
            args.scenario,
            "--seed",
            str(seed),
            "--save-blend",
            str(save_blend),
            "--sample-root",
            str(sample_root),
        ]
    )
    env = os.environ.copy()
    python_paths = [str(project_root / "src"), str(runtime_root)]
    if env.get("PYTHONPATH"):
        python_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    return subprocess.run(command, cwd=project_root, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
