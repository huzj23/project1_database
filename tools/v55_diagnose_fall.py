"""V5.5 stage 05: find why every body ends ~240 m below the floor.

The recorded facts that do not fit together:

  * `bodies.json` shows the striker at z = 1.103582 and the props at their correct floor heights,
    so the bodies ARE built correctly;
  * but `trajectory.json` frame 0 shows the bottle at z = -240.4151 and the striker at
    z = -239.3129 -- everything is hundreds of metres down, including props that should be
    resting on the tray.

A fall of that size takes about 7 s, well beyond the 2 s settle plus 3 s of video, so this is not
ordinary free fall. Two candidates are checked directly:

  C1 did the STATIC colliders actually get created? `_create_static` returns None when the URI is
     unusable, and `load` then simply omits the collider -- so a wrong path produces a world with
     NO support at all, silently. The layer report stores WINDOWS paths, so the basename
     resolution has to be verified rather than assumed.
  C2 is the settle stage itself running far longer than requested, or is the recorded frame 0 the
     state after some other stepping?

The script rebuilds the world exactly as the solve does, asserts the static count, then steps
frame by frame and prints the first frames, so the onset is visible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

CODE = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/"
            "physics-video-sim-main/src")
sys.path.insert(0, str(CODE))

import pybullet as pb  # noqa: E402
from physim.contracts import BodySpec, StaticCollider  # noqa: E402
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T040000"

FLOOR_Z = 0.510600


def main() -> int:
    # ---- C1: do the static collider files exist where the solve looked? ----------------
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    print("=" * 86)
    print("=== C1: static collider resolution ===")
    missing = []
    for name, info in layer["static_collision_per_object"].items():
        raw = info["uri"]
        base = raw.replace("\\", "/").rsplit("/", 1)[-1]
        p = RUNTIME / base
        ok = p.is_file()
        print(f"  {name:38s} raw='{raw.split('/')[-1]:44s}' -> {base:44s} "
              f"exists={ok}")
        if not ok:
            missing.append(base)
    print(f"  missing: {missing}")

    bodies = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
    provenance = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))

    settings = SolverSettings(physics_fps=480)
    solver = MultibodySolver(settings)
    specs = []
    for b in bodies:
        row = dict(b)
        row.pop("is_dynamic", None)
        row.pop("visual_to_body_4x4", None)
        row.pop("collision_to_body_4x4", None)
        for k in ("position_m", "quaternion_xyzw", "linear_velocity_m_s",
                  "angular_velocity_rad_s", "com_local_m"):
            if row.get(k) is not None:
                row[k] = tuple(row[k])
        if row.get("inertia_diagonal_kg_m2"):
            row["inertia_diagonal_kg_m2"] = tuple(row["inertia_diagonal_kg_m2"])
        else:
            row["inertia_diagonal_kg_m2"] = None
        if row.get("mass_range_kg"):
            row["mass_range_kg"] = tuple(row["mass_range_kg"])
        row.setdefault("collider_type", "mesh")
        specs.append(BodySpec(**row))
    statics = []
    for name, info in layer["static_collision_per_object"].items():
        uri = RUNTIME / info["uri"].replace("\\", "/").rsplit("/", 1)[-1]
        statics.append(StaticCollider(
            collider_id=name, collider_type="mesh", uri=str(uri),
            concave=str(name).lower().startswith("vassoio"),
            support_z_m=FLOOR_Z if str(name).lower().startswith("vassoio") else None,
            triangles=info["triangles"]))
    solver.load(specs, statics)
    cid = solver.connect()
    print(f"\n  requested static colliders: {len(statics)}")
    print(f"  ACTUALLY created          : {len(solver._static_ids)}  "
          f"-> {sorted(solver._static_ids)}")
    print(f"  dynamic bodies            : {len(solver._body_ids)}")
    if len(solver._static_ids) != len(statics):
        print("  !! a static collider was silently skipped -- the world then has NO support")
        for s in statics:
            if s.collider_id not in solver._static_ids:
                print(f"     skipped: {s.collider_id}  uri={s.uri}  "
                      f"exists={Path(s.uri).is_file() if s.uri else None}")

    # ---- C2: step and watch the onset ---------------------------------------------------
    print("\n=== C2: step and print the onset (no settle) ===")
    watch = ["bottle_assembly", "striker_box"]
    ids = {k: v for k, v in solver._body_ids.items()}
    for step in range(0, 481):
        if step in (0, 1, 2, 5, 10, 24, 48, 96, 240, 480):
            row = []
            for w in watch:
                p, _ = pb.getBasePositionAndOrientation(ids[w], physicsClientId=cid)
                row.append(f"{w}={p[2]:+.5f}")
            print(f"  step {step:4d} t={step/480:.4f}s  " + "  ".join(row))
        pb.stepSimulation(physicsClientId=cid)

    print("\n=== contacts during those 480 steps ===")
    total = 0
    for i in range(len(solver._body_ids)):
        for j in range(i, len(solver._body_ids)):
            pass
    a = list(solver._body_ids.values()) + list(solver._static_ids.values())
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            n = len(pb.getContactPoints(bodyA=a[i], bodyB=a[j], physicsClientId=cid))
            total += n
            if n:
                na = {v: k for k, v in solver._body_ids.items()}.get(a[i], str(a[i]))
                nb = {v: k for k, v in solver._body_ids.items()}.get(a[j], str(a[j]))
                ns = {v: k for k, v in solver._static_ids.items()}
                print(f"  {ns.get(a[i], na)} <-> {ns.get(a[j], nb)}: {n} contact points")
    print(f"  total contact points at the end: {total}")
    solver.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
