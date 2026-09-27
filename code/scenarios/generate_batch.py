"""Batch driver: generate a grid of single-object physics simulation assets.

Runs ``run_single_object.py`` through Blender once per configuration.  Each job is
an independent, seeded process, so a failed job never poisons the others and the
whole batch is reproducible from the manifest written at the end.

Usage (from the project root)::

    python code/scenarios/generate_batch.py --preset smoke
    python code/scenarios/generate_batch.py --preset circular
    python code/scenarios/generate_batch.py --preset damped  --limit 4
    python code/scenarios/generate_batch.py --preset full    --workers 2

The script only needs a stock CPython (stdlib); Blender does the real work.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
RUNNER = os.path.join(HERE, "run_single_object.py")
OUTCOMES = os.path.join(PROJECT_ROOT, "outcomes")
LOG_DIR = os.path.join(PROJECT_ROOT, "log")


def _find_blender() -> str:
    """Locate the Blender runtime, preferring an explicit env override.

    The same script drives both the Windows dev box and the Linux GPU server, so
    the binary name is resolved per platform instead of hard-coded.
    """
    env = os.environ.get("PHYCO_BLENDER")
    if env and os.path.isfile(env):
        return env
    runtime = os.path.join(PROJECT_ROOT, "tools", "runtime")
    candidates = (
        "blender-3.4.1-linux-x64/blender",
        "blender-3.4.1-windows-x64/blender.exe",
        "blender-3.4.1-windows-x64/blender",
    )
    for rel in candidates:
        p = os.path.join(runtime, rel)
        if os.path.isfile(p):
            return p
    return os.path.join(runtime, candidates[0])


def _find_python() -> str | None:
    """A plain interpreter that already has ``bpy`` available.

    When bpy is installed as a wheel (the server's conda env), the scenario runs
    under that interpreter directly and no Blender executable is involved -- which
    removes the ``--background --python ... --`` wrapper and its argument quirks.
    """
    env = os.environ.get("PHYCO_PYTHON")
    if env and os.path.isfile(env):
        return env
    for rel in ("tools/conda_env/bin/python",
                "tools/conda_env/Scripts/python.exe"):
        p = os.path.join(PROJECT_ROOT, rel)
        if os.path.isfile(p):
            return p
    return None


BLENDER = _find_blender()
PYTHON = _find_python()


# --------------------------------------------------------------------------------------
# Scenario grid definition
# --------------------------------------------------------------------------------------
# Each entry is (name, fixed_args, grid) where grid maps a CLI flag to a list of values.
# The cartesian product of the grid is enumerated.

PRESETS: dict[str, list[dict]] = {
    # quick end-to-end check: one job per motion family, tiny and fast
    "smoke": [
        {"name": "circular_smoke",
         "fixed": {"--motion": "circular", "--object": "ball", "--frame_end": 23},
         "grid": {}},
        {"name": "damped_smoke",
         "fixed": {"--motion": "damped", "--object": "ball", "--frame_end": 23},
         "grid": {}},
    ],

    # fixed circular motion: vary radius / period / object
    "circular": [
        {"name": "circular",
         "fixed": {"--motion": "circular", "--frame_end": 95},
         "grid": {"--object": ["ball", "brick_box", "jenga"],
                  "--radius": [0.8, 1.2],
                  "--period": [2.0, 3.0]}},
    ],

    # damped motion: vary initial speed / decay rate / object
    "damped": [
        {"name": "damped",
         "fixed": {"--motion": "damped", "--frame_end": 95},
         "grid": {"--object": ["ball", "brick_box", "jenga"],
                  "--speed": [2.0, 3.5],
                  "--linear_damping": [0.8, 1.6]}},
    ],

    # pure rotation: only non-spherical bodies -- a spinning sphere is visually
    # indistinguishable from a static one, so it would carry no motion signal
    "rotation": [
        {"name": "rotation",
         "fixed": {"--motion": "rotation", "--frame_end": 95},
         "grid": {"--object": ["brick_box", "brick", "jenga"],
                  "--spin_axis": ["z", "y"],
                  "--spin_period": [2.0, 4.0]}},
    ],

    # confirmed phase-1 delivery: 12 + 12 + 12
    "phase1": [
        {"name": "circular",
         "fixed": {"--motion": "circular", "--frame_end": 95},
         "grid": {"--object": ["ball", "brick_box", "jenga"],
                  "--radius": [0.8, 1.2],
                  "--period": [2.0, 3.0]}},
        {"name": "damped",
         "fixed": {"--motion": "damped", "--frame_end": 95},
         "grid": {"--object": ["ball", "brick_box", "jenga"],
                  "--speed": [2.0, 3.5],
                  "--linear_damping": [0.8, 1.6]}},
        {"name": "rotation",
         "fixed": {"--motion": "rotation", "--frame_end": 95},
         "grid": {"--object": ["brick_box", "brick", "jenga"],
                  "--spin_axis": ["z", "y"],
                  "--spin_period": [2.0, 4.0]}},
    ],

    # Track B1 showcase: same motions, ReplicaCAD interior backdrops.
    # The stage is rotated across jobs by the driver.
    "interior": [
        {"name": "interior_circular",
         "fixed": {"--motion": "circular", "--frame_end": 95},
         "grid": {"--object": ["ball", "brick_box"],
                  "--radius": [0.8, 1.2],
                  "--period": [2.0, 3.0]}},
        {"name": "interior_damped",
         "fixed": {"--motion": "damped", "--frame_end": 95},
         "grid": {"--object": ["ball", "brick_box"],
                  "--speed": [2.0, 3.5],
                  "--linear_damping": [0.8, 1.6]}},
    ],

    # the full production grid
    "full": [
        {"name": "circular",
         "fixed": {"--motion": "circular", "--frame_end": 95},
         "grid": {"--object": ["ball", "ball_small", "brick_box", "brick", "jenga"],
                  "--radius": [0.8, 1.2, 1.6],
                  "--period": [2.0, 3.0],
                  "--plane": ["z"]}},
        {"name": "damped",
         "fixed": {"--motion": "damped", "--frame_end": 95},
         "grid": {"--object": ["ball", "ball_small", "brick_box", "brick", "jenga"],
                  "--speed": [2.0, 3.5],
                  "--linear_damping": [0.8, 1.6]}},
        {"name": "rotation",
         "fixed": {"--motion": "rotation", "--frame_end": 95},
         "grid": {"--object": ["brick_box", "brick", "brick_tall", "jenga", "wall"],
                  "--spin_axis": ["z", "y", "x"],
                  "--spin_period": [2.0, 4.0]}},
    ],
}


def enumerate_jobs(preset: str, limit: int | None = None) -> list[dict]:
    jobs: list[dict] = []
    for block in PRESETS[preset]:
        keys = list(block["grid"].keys())
        value_lists = [block["grid"][k] for k in keys]
        combos = list(itertools.product(*value_lists)) if keys else [()]
        for combo in combos:
            args = dict(block["fixed"])
            label_parts = [block["name"]]
            for k, v in zip(keys, combo):
                args[k] = v
                label_parts.append(f"{k.lstrip('-')}{v}")
            jobs.append({"label": "_".join(str(p) for p in label_parts), "args": args})
    if limit:
        jobs = jobs[:limit]
    return jobs


def build_command(job: dict, common: dict) -> list[str]:
    """Assemble the argv for one scenario run.

    With a bpy-capable interpreter available the script is executed directly;
    otherwise it is launched through the Blender binary, which requires the
    ``--`` separator so Blender forwards the remaining flags to the script.
    """
    if PYTHON:
        cmd = [PYTHON, RUNNER]
        tail_sep = []
    else:
        cmd = [BLENDER, "--background", "--factory-startup", "--python", RUNNER, "--"]
        tail_sep = []
    for k, v in job["args"].items():
        cmd += [str(k), str(v)]
    for k, v in common.items():
        if v is True:
            cmd.append(str(k))
        elif v is not None:
            cmd += [str(k), str(v)]
    cmd += ["--video_id", job["label"]]
    return cmd + tail_sep


def run_job(job: dict, common: dict, out_dir: str) -> dict:
    cmd = build_command(job, common)
    env = dict(os.environ)
    # GPU selection is honoured by Kubric's Blender renderer.
    env.setdefault("KUBRIC_USE_GPU", "true")
    env.setdefault("PYTHONUNBUFFERED", "1")
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                          cwd=PROJECT_ROOT, errors="replace")
    el = time.time() - t0
    vid_dir = os.path.join(out_dir, "single_object", job["label"])
    ok = proc.returncode == 0 and os.path.isfile(
        os.path.join(vid_dir, "metadata.json"))
    tail = (proc.stdout or "")[-600:]
    return {
        "label": job["label"], "args": {k: str(v) for k, v in job["args"].items()},
        "returncode": proc.returncode, "seconds": round(el, 1), "ok": bool(ok),
        "output_dir": vid_dir, "stdout_tail": tail,
        "stderr_tail": (proc.stderr or "")[-600:],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Batch-generate physics assets.")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="smoke")
    ap.add_argument("--limit", type=int, default=None,
                    help="only run the first N jobs (for a quick trial)")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel Blender processes (CPU rendering; 1-2 recommended)")
    ap.add_argument("--resolution", default="768x432")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--threads", type=int, default=0,
                    help="Cycles threads per worker (0 = auto). Use cores/workers.")
    ap.add_argument("--frame_rate", type=int, default=24)
    ap.add_argument("--output_dir", default=os.path.join(OUTCOMES, "dataset"))
    ap.add_argument("--save_mp4", action="store_true", default=True)
    ap.add_argument("--qa_sheet", action="store_true", default=True)
    ap.add_argument("--hdri_random", action="store_true", default=True,
                    help="ignored when --look studio/interior (they pin an HDRI)")
    ap.add_argument("--no_hdri", action="store_true",
                    help="fall back to analytic lighting (only affects --look plain)")
    ap.add_argument("--look", default="studio", choices=["studio", "interior", "plain"],
                    help="backdrop family: studio cyclorama / ReplicaCAD interior / plain")
    ap.add_argument("--floor_material", default="concrete_floor_worn_001")
    ap.add_argument("--stage", default="frl_apartment_stage")
    ap.add_argument("--frame_format", default="png", choices=["png", "jpg"])
    ap.add_argument("--motion_blur", type=float, default=0.25)
    ap.add_argument("--focal_length", type=float, default=55.0)
    ap.add_argument("--stage_cycle", action="store_true", default=True,
                    help="rotate ReplicaCAD stages across jobs for backdrop variety")
    ap.add_argument("--dry_run", "--dry-run", action="store_true", dest="dry_run")
    args = ap.parse_args(argv)

    if not os.path.isfile(RUNNER):
        print(f"[batch] runner not found: {RUNNER}", file=sys.stderr)
        return 2
    if PYTHON:
        print(f"[batch] interpreter : {PYTHON}  (bpy wheel)")
    elif os.path.isfile(BLENDER):
        print(f"[batch] blender     : {BLENDER}")
    else:
        print(f"[batch] neither bpy interpreter nor Blender found", file=sys.stderr)
        return 2
    jobs = enumerate_jobs(args.preset, args.limit)

    # For the interior look, spread jobs across the available ReplicaCAD stages so
    # the batch is not 36 copies of the same room.  Falls back silently if the
    # stages have not been fetched yet.
    stage_cycle = []
    if args.look == "interior" and args.stage_cycle:
        try:
            sys.path.insert(0, HERE)
            import phyco_backdrops as _pb
            stage_cycle = _pb.list_replicad_stages()
        except Exception:
            stage_cycle = []
        if stage_cycle:
            print(f"[batch] replicad stages: {', '.join(stage_cycle)}")

    common = {
        "--resolution": args.resolution,
        "--samples": args.samples,
        "--frame_rate": args.frame_rate,
        "--threads": args.threads if args.threads else None,
        "--output_dir": os.path.join(args.output_dir, "single_object"),
        "--save_mp4": True if args.save_mp4 else None,
        "--qa_sheet": True if args.qa_sheet else None,
        "--look": args.look,
        "--frame_format": args.frame_format,
        "--motion_blur": args.motion_blur,
        "--focal_length": args.focal_length,
        "--floor_material": args.floor_material if args.look == "studio" else None,
        "--stage": (stage_cycle[0] if (stage_cycle and args.look == "interior") else None),
        "--hdri_random": True if (args.look == "plain" and args.hdri_random
                                  and not args.no_hdri) else None,
    }
    if stage_cycle and args.look == "interior":
        for i, j in enumerate(jobs):
            j["args"]["--stage"] = stage_cycle[i % len(stage_cycle)]

    print(f"[batch] preset={args.preset} jobs={len(jobs)} workers={args.workers}")
    print(f"[batch] output={common['--output_dir']}")
    if args.dry_run:
        for j in jobs:
            print("  " + " ".join(build_command(j, common)))
        return 0

    os.makedirs(LOG_DIR, exist_ok=True)
    results = []
    t0 = time.time()
    if args.workers <= 1:
        for i, job in enumerate(jobs, 1):
            r = run_job(job, common, args.output_dir)
            results.append(r)
            print(f"[batch] [{i}/{len(jobs)}] {r['label']}: "
                  f"{'OK' if r['ok'] else 'FAIL'} in {r['seconds']}s", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run_job, j, common, args.output_dir): j for j in jobs}
            for i, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                results.append(r)
                print(f"[batch] [{i}/{len(jobs)}] {r['label']}: "
                      f"{'OK' if r['ok'] else 'FAIL'} in {r['seconds']}s", flush=True)

    total = time.time() - t0
    n_ok = sum(1 for r in results if r["ok"])
    manifest = {
        "preset": args.preset,
        "created": datetime.now().isoformat(timespec="seconds"),
        "common_args": {k: str(v) for k, v in common.items()},
        "jobs_total": len(results),
        "jobs_ok": n_ok,
        "jobs_failed": len(results) - n_ok,
        "wall_seconds": round(total, 1),
        "results": sorted(results, key=lambda r: r["label"]),
    }
    stamp = datetime.now().strftime("%Y%m%d")
    man_path = os.path.join(LOG_DIR, f"batch_manifest_{args.preset}_{stamp}.json")
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[batch] {n_ok}/{len(results)} ok in {total:.1f}s")
    print(f"[batch] manifest -> {man_path}")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
