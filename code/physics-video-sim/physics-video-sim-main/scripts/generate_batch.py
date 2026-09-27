"""Run isolated Blender jobs for validated controlled-variable sample groups."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import yaml


SCENARIOS = ("rolling", "constant_force", "free_fall")


def _project_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _run_group(
    project_root: Path,
    blender: Path,
    config_path: Path,
    scenario: str,
    seed: int,
    gpu_id: int | None,
    expected_outputs: int,
) -> dict[str, Any]:
    log_path = project_root / "logs" / "batch" / scenario / f"seed-{seed:06d}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python",
        str(project_root / "scripts" / "generate.py"),
        "--",
        "--config",
        str(config_path),
        "--scenario",
        scenario,
        "--seed",
        str(seed),
        "--all-variants",
    ]
    environment = os.environ.copy()
    if gpu_id is not None:
        environment["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
        environment["KUBRIC_USE_GPU"] = "1"
    completed = subprocess.run(
        command,
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    log_path.write_text(
        completed.stdout + "\n--- STDERR ---\n" + completed.stderr,
        encoding="utf-8",
    )
    outputs = [
        line.partition("=")[2]
        for line in completed.stdout.splitlines()
        if line.startswith("SAMPLE_OUTPUT=")
    ]
    passed = completed.returncode == 0 and len(outputs) == expected_outputs
    return {
        "scenario": scenario,
        "seed": seed,
        "gpu_id": gpu_id,
        "passed": passed,
        "returncode": completed.returncode,
        "expected_outputs": expected_outputs,
        "outputs": outputs,
        "log": str(log_path),
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/server.yaml"))
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=SCENARIOS)
    parser.add_argument("--groups-per-scenario", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=1000)
    parser.add_argument("--max-attempts-per-scenario", type=int, default=40)
    parser.add_argument("--gpu-ids", type=int, nargs="*")
    parser.add_argument("--report", type=Path, default=Path("outputs/batch-report.json"))
    args = parser.parse_args()
    if args.groups_per_scenario <= 0:
        raise ValueError("--groups-per-scenario must be positive")

    project_root = Path(__file__).resolve().parent.parent
    config_path = args.config
    if not config_path.is_absolute():
        config_path = project_root / config_path
    environment_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    blender = _project_path(
        project_root, environment_config["paths"]["blender_executable"]
    )
    configured_gpus = tuple(environment_config["execution"].get("gpu_ids", ()))
    gpu_ids = tuple(args.gpu_ids) if args.gpu_ids is not None else configured_gpus
    slots: tuple[int | None, ...] = gpu_ids or (None,)
    rows: list[dict[str, Any]] = []

    for scenario_index, scenario in enumerate(args.scenarios):
        scenario_config = yaml.safe_load(
            (project_root / "configs" / "scenarios" / f"{scenario}.yaml").read_text(
                encoding="utf-8"
            )
        )
        expected_outputs = len(
            scenario_config["controlled_variants"]["multipliers"]
        )
        accepted = 0
        attempts = 0
        next_seed = args.seed_start + scenario_index * 1000
        while accepted < args.groups_per_scenario:
            remaining_attempts = args.max_attempts_per_scenario - attempts
            if remaining_attempts <= 0:
                raise RuntimeError(
                    f"{scenario} produced only {accepted}/{args.groups_per_scenario} "
                    "valid groups before the attempt limit"
                )
            wave_size = min(
                len(slots),
                args.groups_per_scenario - accepted,
                remaining_attempts,
            )
            jobs = [
                (next_seed + index, slots[index % len(slots)])
                for index in range(wave_size)
            ]
            next_seed += wave_size
            attempts += wave_size
            with ThreadPoolExecutor(max_workers=wave_size) as executor:
                futures = {
                    executor.submit(
                        _run_group,
                        project_root,
                        blender,
                        config_path,
                        scenario,
                        seed,
                        gpu_id,
                        expected_outputs,
                    ): seed
                    for seed, gpu_id in jobs
                }
                for future in as_completed(futures):
                    row = future.result()
                    rows.append(row)
                    if row["passed"]:
                        accepted += 1
                    print(
                        f"{'PASS' if row['passed'] else 'FAIL'} "
                        f"scenario={scenario} seed={row['seed']} gpu={row['gpu_id']}"
                    )

    report = {
        "schema_version": 1,
        "groups_per_scenario": args.groups_per_scenario,
        "scenarios": list(args.scenarios),
        "rows": rows,
    }
    report_path = args.report
    if not report_path.is_absolute():
        report_path = project_root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"BATCH_REPORT={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
