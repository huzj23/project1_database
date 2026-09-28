"""V5.5 stage 03 section 5: map which (dynamic shape, static shape) pairs actually collide.

Established by measurement, not assumption:

  * a static GEOM_MESH is CONVEX-HULLED unless FLAGGED concave. Proof: the tray's own floor is
    at z = 0.510600 (raycast) and its rim at 0.522260, and a probe box on the unflagged mesh
    rests at z = 0.523247 -- the rim -- while on the flagged mesh it rests at 0.510590, the
    floor (bias -0.0104 mm). Candidate B (concave) is therefore the exact authored collider.
  * a DYNAMIC GEOM_MESH does not collide with GEOM_PLANE (a control GEOM_BOX does), while the
    same mesh DOES rest on a GEOM_BOX floor and on the unflagged (hulled) tray.
  * but a dynamic GEOM_MESH planted perfectly on the FLAGGED tray falls straight through.

So the failures are not "the solver misses the contact" and not engine parameters -- 36
parameter combinations all reproduced them. They depend on the SHAPE PAIR. This file measures
the whole matrix in isolated worlds so the solver's collider configuration can be chosen from
evidence:

  dynamic x static, for
    dynamic in {mesh via vertices/indices, mesh via fileName, concave-flagged mesh}
    static  in {plane, box floor, flagged concave tray, unflagged hulled tray}

Each cell reports the settled height and the contact count, and whether the body rests at the
tray floor. A cell is usable only if the body RESTS; the flags it needs are then recorded so the
solver can reproduce it exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pybullet as pb

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"

DT = 1.0 / 480.0
FLOOR_Z = 0.510600
RIM_Z = 0.522260
PROP = "bottle_assembly"
PROP_MASS = 0.77


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def write_obj(path: Path, v, f):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as h:
        for p in v:
            h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
        for t in f:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 numSubSteps=1, enableConeFriction=1,
                                 physicsClientId=cid)
    return cid


def make_static(cid, kind: str, tray_path: Path, cx: float, cy: float):
    """Return (body_ids, support_reference_z) for the chosen static support."""
    if kind == "plane":
        s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                    physicsClientId=cid)
        return [pb.createMultiBody(0, s, basePosition=(0.0, 0.0, FLOOR_Z),
                                   physicsClientId=cid)], FLOOR_Z
    if kind == "box_floor":
        s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.5, 0.5, 0.05],
                                    physicsClientId=cid)
        return [pb.createMultiBody(0, s, basePosition=(cx, cy, FLOOR_Z - 0.05),
                                   physicsClientId=cid)], FLOOR_Z
    if kind == "tray_concave":
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tray_path),
                                    flags=pb.GEOM_FORCE_CONCAVE_TRIMESH,
                                    physicsClientId=cid)
        return [pb.createMultiBody(0, s, basePosition=(0, 0, 0),
                                   physicsClientId=cid)], FLOOR_Z
    if kind == "tray_hull":
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tray_path),
                                    physicsClientId=cid)
        return [pb.createMultiBody(0, s, basePosition=(0, 0, 0),
                                   physicsClientId=cid)], RIM_Z
    raise ValueError(kind)


def make_dynamic(cid, kind: str, V, F, obj_path: Path, spawn, mass):
    if kind == "mesh_indices":
        s = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                    indices=F.ravel().tolist(), physicsClientId=cid)
    elif kind == "mesh_filename":
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj_path),
                                    physicsClientId=cid)
    elif kind == "mesh_concave":
        s = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                    indices=F.ravel().tolist(),
                                    flags=pb.GEOM_FORCE_CONCAVE_TRIMESH,
                                    physicsClientId=cid)
    else:
        raise ValueError(kind)
    if s < 0:
        raise RuntimeError(f"dynamic shape {kind} failed")
    b = pb.createMultiBody(mass, s, basePosition=list(spawn), physicsClientId=cid)
    pb.changeDynamics(b, -1, lateralFriction=0.6, restitution=0.0, physicsClientId=cid)
    return b


def main() -> int:
    tray = RUNTIME / "static_Vassoio.obj"
    props = SCENES / "props" / PROP / "vhacd"
    files = sorted(props.glob("part*.obj"))
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    V = np.vstack(vs)
    F = np.vstack(fs)
    decision = json.loads((SCENES / "props" / "proxy_decision.json").read_text(
        encoding="utf-8"))
    restore = -np.asarray(decision[PROP]["recentre_offset_m"], float)
    world_lo = V.min(axis=0) + restore
    cx = float(0.5 * (world_lo[0] + (V.max(axis=0) + restore)[0]))
    cy = float(0.5 * (world_lo[1] + (V.max(axis=0) + restore)[1]))
    base_z = FLOOR_Z - world_lo[2]
    spawn = restore + np.array([0.0, 0.0, base_z])
    merged_obj = props.parent / "vhacd_merged_translated.obj"
    write_obj(merged_obj, V, F)
    print(f"prop {PROP}: {len(files)} parts, {len(F)} tri, centre ({cx:.4f}, {cy:.4f}), "
          f"base_z offset {base_z:.6f}")

    dyn_kinds = ["mesh_indices", "mesh_filename", "mesh_concave"]
    static_kinds = ["plane", "box_floor", "tray_concave", "tray_hull"]

    report: dict = {"floor_z": FLOOR_Z, "rim_z": RIM_Z, "prop": PROP, "cells": []}
    print("\n" + "=" * 96)
    print(f"{'dynamic':14s} {'static support':14s} {'rests':>6s} {'settled_bottom_z':>17s} "
          f"{'vs floor mm':>12s} {'contacts':>9s}")
    print("-" * 96)
    for dk in dyn_kinds:
        for sk in static_kinds:
            cid = new_world()
            cell = {"dynamic": dk, "static": sk}
            try:
                statics, ref_z = make_static(cid, sk, tray, cx, cy)
                try:
                    body = make_dynamic(cid, dk, V, F, merged_obj, spawn, PROP_MASS)
                except Exception as exc:
                    print(f"{dk:14s} {sk:14s} {'ERROR':>6s}  {type(exc).__name__}: {exc}")
                    cell.update({"error": f"{type(exc).__name__}: {exc}"})
                    report["cells"].append(cell)
                    continue
                for _ in range(int(1.5 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
                speed, spin = float(np.linalg.norm(lin)), float(np.linalg.norm(ang))
                n = sum(len(pb.getContactPoints(bodyA=body, bodyB=b,
                                                physicsClientId=cid)) for b in statics)
                bottom = float(pos[2]) + float(V.min(axis=0)[2])
                rests = bool(n > 0 and speed < 1e-3 and spin < 1e-3)
                cell.update({"rests": rests, "settled_origin_z": float(pos[2]),
                             "settled_bottom_z": bottom,
                             "bias_vs_floor_m": bottom - FLOOR_Z,
                             "contacts": n, "speed_m_s": speed, "spin_rad_s": spin})
                print(f"{dk:14s} {sk:14s} {('YES' if rests else 'no'):>6s} "
                      f"{bottom:17.6f} {(bottom-FLOOR_Z)*1000:12.3f} {n:9d}")
            finally:
                pb.disconnect(cid)
            report["cells"].append(cell)

    working = [c for c in report["cells"] if c.get("rests")]
    print("-" * 96)
    print(f"cells where the body RESTS: {len(working)} of {len(report['cells'])}")
    for c in working:
        print(f"  {c['dynamic']:14s} on {c['static']:14s} "
              f"bias={(c['bias_vs_floor_m'] or 0)*1000:+8.3f} mm")
    # A configuration usable by the solver needs the dynamic body to rest, and the static
    # support to be at the true floor rather than at the rim.
    usable = [c for c in working if abs(c["bias_vs_floor_m"]) <= 0.002]
    report["usable"] = [{"dynamic": c["dynamic"], "static": c["static"],
                         "bias_m": c["bias_vs_floor_m"]} for c in usable]
    print(f"\nusable (rests AND at the true floor within 2 mm): {len(usable)}")
    for c in usable:
        print(f"  -> dynamic={c['dynamic']} static={c['static']} "
              f"bias={c['bias_vs_floor_m']*1000:+.3f} mm")

    out = SCENES / "shape_pair_matrix.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
