"""V5.5 stage 05: monitor the release from step 0, with NO pre-settle.

The previous trace measured the box's AABB only AFTER a 960-step (2 s) settle, by which time the
box had already struck something, bounced, slid off the table and fallen several metres -- and the
scene has no ground plane, so a miss falls forever. Every number in that trace described the
aftermath, not the approach, which is why the box appeared to start 300 mm from the bottle at a
negative height.

Here the bodies are released and every single step is monitored from step 1. For each step the box's
bottom height, its y-overlap with the bottle, and the number of box-bottle contact points are
recorded, so the exact moment of first contact is visible and a genuine miss can be told apart from
a collision that happens during a settle window.
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
from physim.contracts import (  # noqa: E402
    ROLE_PASSIVE, ROLE_TARGET, ROLE_TRIGGER, BodySpec, StaticCollider, box_inertia_diagonal,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
DESIGN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"
WORK = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/trace"
BUILD = ROOT / "models/gso/Big_Dot_Aqua_Pencil_Case"
FLOOR_Z = 0.510600


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


def write_obj(path: Path, V, F) -> None:
    with path.open("w", encoding="utf-8") as h:
        for q in V:
            h.write(f"v {q[0]:.9f} {q[1]:.9f} {q[2]:.9f}\n")
        for t in F:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")


def main() -> int:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)

    mesh_path, body_origin, local_min = {}, {}, {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        d = decision[name]
        vs, fs, off = [], [], 0
        for f in sorted((PROPS / name / d["chosen"]).glob("*.obj")):
            v, fc = load_obj(f)
            vs.append(v)
            fs.append(fc + off)
            off += len(v)
        V, F = np.vstack(vs), np.vstack(fs)
        p = WORK / f"{name}_collision.obj"
        write_obj(p, V, F)
        mesh_path[name] = p
        local_min[name] = V.min(axis=0)
        restore = -np.asarray(d["recentre_offset_m"], float)
        body_origin[name] = np.array([restore[0], restore[1], FLOOR_Z - V.min(axis=0)[2]])

    bv, bf = load_obj(BUILD / "collision_geometry.obj")
    blo, bhi = bv.min(axis=0), bv.max(axis=0)
    box_dims = (bhi - blo).tolist()
    box_obj = WORK / "striker_box_collision.obj"
    write_obj(box_obj, bv - 0.5 * (blo + bhi), bf)

    statics = []
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    for name, info in layer["static_collision_per_object"].items():
        uri = RUNTIME / info["uri"].replace("\\", "/").rsplit("/", 1)[-1]
        low = str(name).lower()
        statics.append(StaticCollider(
            collider_id=name, collider_type="mesh", uri=str(uri),
            concave=low.startswith("vassoio"),
            support_z_m=FLOOR_Z if low.startswith("vassoio") else None,
            triangles=info["triangles"]))

    axis = np.asarray(design["bottle_axis_xy"], float)
    top = float(design["bottle_top_z"])
    half_y = box_dims[1] / 2

    print("=" * 100)
    print("=== release geometry ===")
    print(f"  bottle axis ({axis[0]:.6f}, {axis[1]:.6f}); top z {top:.6f}; "
          f"bottle body origin {np.round(body_origin['bottle_assembly'],6)}")
    print(f"  bottle local z {local_min['bottle_assembly'][2]:+.6f} -> world bottom "
          f"{FLOOR_Z:.6f}")
    print(f"  box dims {[round(v,6) for v in box_dims]}; y half-extent {half_y*1000:.3f} mm")

    out = {"cases": []}
    for nf in (0.045, 0.035, 0.025, 0.015, 0.005, -0.005):
        centre = np.array([axis[0], axis[1] + nf + half_y, top + 0.25 + box_dims[2] / 2])
        solver = MultibodySolver(SolverSettings(physics_fps=480))
        bodies = []
        for name in ("bottle_assembly", "glass_a", "glass_b"):
            bodies.append(BodySpec(
                instance_id=name, asset_id=name,
                role=ROLE_TARGET if name == "bottle_assembly" else ROLE_PASSIVE,
                mass_kg={"bottle_assembly": 0.77, "glass_a": 0.113, "glass_b": 0.157}[name],
                mass_basis="estimated", collider_type="mesh",
                position_m=tuple(float(v) for v in body_origin[name]),
                quaternion_xyzw=(0.0, 0.0, 0.0, 1.0), friction=0.6, restitution=0.0,
                collision_uri=str(mesh_path[name])))
        bodies.append(BodySpec(
            instance_id="striker_box", asset_id="small_box", role=ROLE_TRIGGER,
            mass_kg=0.1016, mass_basis="estimated", collider_type="mesh",
            position_m=tuple(float(v) for v in centre), quaternion_xyzw=(0.0, 0.0, 0.0, 1.0),
            friction=0.6, restitution=0.0, collision_uri=str(box_obj),
            inertia_diagonal_kg_m2=box_inertia_diagonal(0.1016, box_dims)))
        solver.load(bodies, statics)
        cid = solver.client
        sid = solver._body_ids["striker_box"]
        bid = solver._body_ids["bottle_assembly"]

        smin, smax = pb.getAABB(sid, physicsClientId=cid)
        bmin, bmax = pb.getAABB(bid, physicsClientId=cid)
        ov_y = min(smax[1], bmax[1]) - max(smin[1], bmin[1])
        ov_x = min(smax[0], bmax[0]) - max(smin[0], bmin[0])
        print("\n" + "=" * 100)
        print(f"=== near face {nf*1000:+6.1f} mm -> box centre y {centre[1]:.6f} ===")
        print(f"  box AABB t=0  x {smin[0]:.5f}..{smax[0]:.5f}  y {smin[1]:.5f}..{smax[1]:.5f}  "
              f"z {smin[2]:.5f}..{smax[2]:.5f}")
        print(f"  bottle AABB   x {bmin[0]:.5f}..{bmax[0]:.5f}  y {bmin[1]:.5f}..{bmax[1]:.5f}  "
              f"z {bmin[2]:.5f}..{bmax[2]:.5f}")
        print(f"  t=0 overlap: x {ov_x*1000:+.3f} mm  y {ov_y*1000:+.3f} mm   "
              f"({'OVERLAP' if ov_x > 0 and ov_y > 0 else 'NO OVERLAP'})")

        first = None
        trace = []
        for step in range(1, 1441):
            pb.stepSimulation(physicsClientId=cid)
            n = len(pb.getContactPoints(bodyA=sid, bodyB=bid, physicsClientId=cid))
            if n and first is None:
                first = step
            if step <= 400 and (step % 20 == 0 or n):
                smin2, _ = pb.getAABB(sid, physicsClientId=cid)
                pp, _ = pb.getBasePositionAndOrientation(sid, physicsClientId=cid)
                trace.append({"step": step, "box_z": float(pp[2]),
                              "bottom": float(smin2[2]), "contacts": n})
        print(f"  FIRST CONTACT STEP: {first}"
              + (f"  (t = {first/480:.4f} s)" if first else "  <- never contacted"))
        for r in trace[:14]:
            print(f"    step {r['step']:4d} box_z={r['box_z']:8.5f} bottom={r['bottom']:8.5f} "
                  f"contacts={r['contacts']}")

        bp, bq = pb.getBasePositionAndOrientation(bid, physicsClientId=cid)
        sp, sq = pb.getBasePositionAndOrientation(sid, physicsClientId=cid)
        bstart = body_origin["bottle_assembly"]
        trans = float(np.linalg.norm((np.array(bp) - bstart)[:2]))
        d = abs(float(np.dot(np.array(bq), np.array([0.0, 0.0, 0.0, 1.0]))))
        tilt = float(np.degrees(2 * np.arccos(min(1.0, d))))
        print(f"  bottle response: translation {trans*1000:.3f} mm, tilt {tilt:.2f} deg")
        print(f"  box final z {sp[2]:.5f}")
        out["cases"].append({"near_face_m": nf, "first_contact_step": first,
                             "bottle_translation_m": trans, "bottle_tilt_deg": tilt,
                             "box_start_centre": [float(v) for v in centre],
                             "t0_overlap_xy_m": [float(ov_x), float(ov_y)],
                             "box_final_z": float(sp[2]), "trace": trace})
        solver.disconnect()

    passing = [c for c in out["cases"]
               if c["first_contact_step"] and (c["bottle_translation_m"] >= 0.030
                                               or c["bottle_tilt_deg"] >= 20.0)]
    out["passing"] = passing
    out["chosen"] = passing[0] if passing else None
    (WORK.parent / "trace_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n" + "=" * 100)
    print(f"=== cases: {len(out['cases'])}, passing: {len(passing)} ===")
    for c in out["cases"]:
        print(f"  near face {c['near_face_m']*1000:+6.1f} mm  hit={str(bool(c['first_contact_step'])):5s} "
              f"trans={c['bottle_translation_m']*1000:8.3f} mm tilt={c['bottle_tilt_deg']:6.2f} deg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
