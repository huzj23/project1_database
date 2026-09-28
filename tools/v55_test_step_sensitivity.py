"""V5.5 stage 04: step-size sensitivity and same-seed repeatability (04 section 5).

Two claims must be EVIDENCE, not assumptions:

  * same seed, same stack, three runs -> identical event ORDER, with key-moment time
    differences within one video frame;
  * 480 Hz vs 960 Hz -> the same propagation order and the same successful chain length,
    with event-time differences within one video frame, otherwise the step is not
    converged and a finer one must be adopted.

This runs the identical three-box layout at both rates and across repeated seeds and
reports the measured differences.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main")
sys.path.insert(0, str(REPO / "src"))

from physim.contracts import (  # noqa: E402
    ROLE_TARGET,
    ROLE_TRIGGER,
    BodySpec,
    StaticCollider,
    box_inertia_diagonal,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

HALF = (0.05, 0.05, 0.025)
DIMS = tuple(2 * h for h in HALF)
XS = (-0.11, 0.0, 0.11)
VIDEO_FPS = 24.0
ONE_FRAME_S = 1.0 / VIDEO_FPS

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, reason: str) -> None:
    RESULTS.append((name, passed, reason))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {reason}")


def build(instance_ids):
    boxes = []
    for i, iid in enumerate(instance_ids):
        vel = (0.8, 0.0, 0.0) if i == 0 else (0.0, 0.0, 0.0)
        boxes.append(BodySpec(
            instance_id=iid, asset_id="prim",
            role=ROLE_TRIGGER if i == 0 else ROLE_TARGET,
            mass_kg=0.35, mass_basis="estimated", collider_type="box",
            position_m=(XS[i], 0.0, 0.0251), linear_velocity_m_s=vel,
            inertia_diagonal_kg_m2=box_inertia_diagonal(0.35, DIMS),
        ))
    return boxes


def run_case(physics_fps: float, seed: int, frames: int = 72):
    ids = ("box_001", "box_002", "box_003")
    boxes = build(ids)
    prims = {i: {"half_extents_m": HALF} for i in ids}
    settings = SolverSettings(physics_fps=physics_fps, video_fps=VIDEO_FPS)
    with MultibodySolver(settings, seed=seed) as solver:
        solver.load(boxes, [StaticCollider(collider_id="static:ground",
                                          collider_type="plane",
                                          position_m=(0.0, 0.0, 0.0))],
                    primitives=prims)
        result = solver.run(frame_count=frames, run_id=f"{physics_fps:g}Hz-seed{seed}")

    # Onset = first frame each target moved more than 2 mm from its initial position.
    onsets = {}
    for iid in ids:
        traj = result.trajectories[iid]
        for state in traj:
            if math.dist(state.position, traj[0].position) > 0.002:
                onsets[iid] = round(state.time_seconds, 6)
                break
        else:
            onsets[iid] = None
    order = [iid for iid in ids if onsets.get(iid) is not None]
    return {
        "physics_fps": physics_fps,
        "seed": seed,
        "onsets_s": onsets,
        "order": order,
        # UNIQUE pairs, not one entry per contact row: listing every row made this file
        # 3.2 MB and obscured the fact being reported.  Sorted for a stable comparison.
        "contact_pairs": sorted({
            "|".join(sorted((c.instance_a, c.instance_b))) for c in result.contacts
        }),
        "contact_rows": len(result.contacts),
        "substeps": len(result.substeps),
        "frames": result.frame_count,
    }


def main() -> int:
    print("=== V5.5 stage 04: step sensitivity and same-seed repeatability ===")
    print()

    print("--- A. same seed, three runs, identical event order ---")
    reps = [run_case(480.0, seed=550001) for _ in range(3)]
    orders = [r["order"] for r in reps]
    same_order = all(o == orders[0] for o in orders)
    # Compare each target's onset across the three runs, in video frames.
    worst_frame_diff = 0.0
    for iid in ("box_001", "box_002", "box_003"):
        times = [r["onsets_s"][iid] for r in reps if r["onsets_s"][iid] is not None]
        if len(times) == len(reps) and times:
            worst_frame_diff = max(worst_frame_diff, max(times) - min(times))
    record("same_seed_identical_event_order", same_order,
           f"three runs at 480 Hz/seed 550001 gave order {orders[0]} every time "
           f"(identical={same_order}); max onset spread {worst_frame_diff * 1000:.4f} ms")
    record("same_seed_within_one_video_frame", worst_frame_diff <= ONE_FRAME_S,
           f"onset spread {worst_frame_diff * 1000:.4f} ms <= one video frame "
           f"{ONE_FRAME_S * 1000:.1f} ms at 24 fps")
    print(f"      raw repeats: {json.dumps(reps, indent=None)[:400]}")

    print()
    print("--- B. step sensitivity: 480 Hz vs 960 Hz ---")
    r480 = run_case(480.0, seed=550001)
    r960 = run_case(960.0, seed=550001)
    order_match = r480["order"] == r960["order"]
    record("step_size_same_propagation_order", order_match,
           f"480 Hz order {r480['order']} vs 960 Hz order {r960['order']} "
           f"(same={order_match})")
    record("step_size_same_chain_length", len(r480["order"]) == len(r960["order"]),
           f"chain length 480 Hz={len(r480['order'])} vs 960 Hz={len(r960['order'])}")

    diffs = {}
    for iid in ("box_001", "box_002", "box_003"):
        a, b = r480["onsets_s"][iid], r960["onsets_s"][iid]
        diffs[iid] = None if a is None or b is None else round(abs(a - b), 6)
    worst = max((d for d in diffs.values() if d is not None), default=0.0)
    record("step_size_times_within_one_video_frame", worst <= ONE_FRAME_S,
           f"worst onset difference {worst * 1000:.4f} ms <= one video frame "
           f"{ONE_FRAME_S * 1000:.1f} ms; per-target {diffs}")

    print()
    print("--- C. substep coverage scales with the rate (all substeps recorded) ---")
    expect480 = 72 * 20 * 3          # frames x (480/24) x 3 dynamic bodies
    expect960 = 72 * 40 * 3
    record("all_substeps_recorded_at_480", r480["substeps"] == expect480,
           f"480 Hz recorded {r480['substeps']} substep rows, expected {expect480}")
    record("all_substeps_recorded_at_960", r960["substeps"] == expect960,
           f"960 Hz recorded {r960['substeps']} substep rows, expected {expect960}")

    # Written to the workspace root, not next to the checkout: the first version computed
    # this from __file__ and landed in code/outcomes/, outside the outcomes tree.
    out = Path("/data/raw/huzijian/project1_database/outcomes/v55/stage04")
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "repeats_480": reps,
        "run_480": r480,
        "run_960": r960,
        "onset_differences_s": diffs,
        "checks": [{"name": n, "passed": p, "reason": r} for n, p, r in RESULTS],
    }
    (out / "step_sensitivity.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'step_sensitivity.json'}")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n=== SUMMARY: {passed}/{len(RESULTS)} checks passed ===")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
