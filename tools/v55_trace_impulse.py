"""V5.5 stage 05: why does a 22 N impulse over 16 substeps move the bottle only 1 mm?

The impulse accounting says it should not. For attempt #3 of the last search:

    peak normal force  22.2 N over ~16 substeps at dt = 1/480 s -> impulse ~0.74 N*s
    momentum available 0.2184 kg * 2.80 m/s                 = 0.61 N*s
    so about 0.6 N*s went into the bottle; at 0.77 kg that is 0.79 m/s, and sliding against
    mu = 0.6 would carry it roughly v^2/(2*mu*g) = 53 mm -- comfortably past the 30 mm criterion.

The measurement says 1.0 mm. Two explanations fit, and they need different fixes:

  H1 the bottle receives the velocity and is then STOPPED by the scene -- the tray's 11.66 mm kerb,
     or a penetration against the table/tray that locks it. Then the trajectory shows a real peak
     displacement that decays back, and the fix is the support geometry, not the trigger.
  H2 the bottle never receives the velocity -- the mass or inertia on the body is not what
     bodies.json declares. Then the trajectory is flat throughout, and the fix is in body creation.

This script runs one configuration and prints, per frame, the bottle's position, its linear
velocity from PyBullet, and the contact count, so H1 and H2 are told apart by data. It also reads
back the DYNAMICS PyBullet actually has for each body, which is the direct check on H2.
"""

from __future__ import annotations

import json
import math
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
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
WORK = OUT / "search"
GSO = ROOT / "models/gso"
PHYSICS_FPS = 480
VIDEO_FPS = 24
FLOOR_Z = 0.510600
TARGET = "bottle_assembly"
PROP_MASS = {"bottle_assembly": 0.77, "glass_a": 0.113, "glass_b": 0.157}


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


def main() -> int:
    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    mesh_path, body_origin = {}, {}
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
        with p.open("w", encoding="utf-8") as h:
            for q in V:
                h.write(f"v {q[0]:.9f} {q[1]:.9f} {q[2]:.9f}\n")
            for t in F:
                h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")
        mesh_path[name] = p
        restore = -np.asarray(d["recentre_offset_m"], float)
        body_origin[name] = np.array([restore[0], restore[1], FLOOR_Z - V.min(axis=0)[2]])

    sv, sf = load_obj(GSO / "Creatine_Monohydrate" / "collision_geometry.obj")
    slo, shi = sv.min(axis=0), sv.max(axis=0)
    s_dims = (shi - slo).tolist()
    striker_obj = WORK / "striker_vessel_collision.obj"
    with striker_obj.open("w", encoding="utf-8") as h:
        for q in (sv - 0.5 * (slo + shi)):
            h.write(f"v {q[0]:.9f} {q[1]:.9f} {q[2]:.9f}\n")
        for t in sf:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")

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

    def props(poses=None):
        out = []
        for name in ("bottle_assembly", "glass_a", "glass_b"):
            pos, quat = ((poses[name][0], poses[name][1]) if poses
                         else (tuple(float(v) for v in body_origin[name]),
                               (0.0, 0.0, 0.0, 1.0)))
            out.append(BodySpec(
                instance_id=name, asset_id=name,
                role=ROLE_TARGET if name == TARGET else ROLE_PASSIVE,
                mass_kg=PROP_MASS[name], mass_basis="estimated", collider_type="mesh",
                position_m=tuple(pos), quaternion_xyzw=tuple(quat),
                friction=0.6, restitution=0.0, collision_uri=str(mesh_path[name])))
        return out

    # settle
    s = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
    s.load(props(), statics)
    s.connect()
    for _ in range(int(2.0 * PHYSICS_FPS)):
        pb.stepSimulation(physicsClientId=s.client)
    settled = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        p, q = pb.getBasePositionAndOrientation(s._body_ids[name], physicsClientId=s.client)
        settled[name] = [list(p), list(q)]
    s.disconnect()

    g = json.loads((OUT / "prop_geometry_dense.json").read_text(encoding="utf-8"))[TARGET]
    axis = np.asarray(g["axis_xy"], float)
    cases = [(0.04899, 0.40), (0.040, 0.40), (0.035, 0.35)]
    for nf, drop in cases:
        centre = np.array([axis[0], axis[1] + nf + s_dims[1] / 2,
                           g["top_z"] + drop + s_dims[2] / 2])
        solver = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
        bodies = props(settled)
        bodies.append(BodySpec(
            instance_id="striker_vessel", asset_id="sealed_vessel", role=ROLE_TRIGGER,
            mass_kg=0.2184, mass_basis="estimated", collider_type="mesh",
            position_m=tuple(float(v) for v in centre),
            quaternion_xyzw=(0.0, 0.0, 0.0, 1.0), friction=0.6, restitution=0.0,
            collision_uri=str(striker_obj),
            inertia_diagonal_kg_m2=box_inertia_diagonal(0.2184, s_dims)))
        solver.load(bodies, statics)
        cid = solver.connect()
        bid = solver._body_ids[TARGET]
        sid = solver._body_ids["striker_vessel"]

        print("\n" + "=" * 100)
        print(f"=== near face {nf*1000:.2f} mm, drop {drop:.2f} m ===")
        # H2 check: what dynamics does PyBullet actually hold?
        dyn = pb.getDynamicsInfo(bid, -1, physicsClientId=cid)
        print(f"  BOTTLE dynamics from PyBullet: mass={dyn[0]:.6f} kg  "
              f"lateralFriction={dyn[1]:.4f}  restitution={dyn[5]:.4f}  "
              f"localInertiaDiag={np.round(dyn[2],9)}")
        dyns = pb.getDynamicsInfo(sid, -1, physicsClientId=cid)
        print(f"  STRIKER dynamics:             mass={dyns[0]:.6f} kg  "
              f"lateralFriction={dyns[1]:.4f}  localInertiaDiag={np.round(dyns[2],9)}")
        for st in statics:
            pass

        p0, _ = pb.getBasePositionAndOrientation(bid, physicsClientId=cid)
        p0 = np.array(p0)
        peak = 0.0
        peak_frame = None
        rows = []
        for frame in range(72):
            for _ in range(20):
                pb.stepSimulation(physicsClientId=cid)
            p, q = pb.getBasePositionAndOrientation(bid, physicsClientId=cid)
            lv, av = pb.getBaseVelocity(bid, physicsClientId=cid)
            n = len(pb.getContactPoints(bodyA=sid, bodyB=bid, physicsClientId=cid))
            d = float(np.linalg.norm((np.array(p) - p0)[:2]))
            if d > peak:
                peak, peak_frame = d, frame
            rows.append((frame, d, float(np.linalg.norm(lv)), float(np.linalg.norm(av)), n))
        print(f"  peak horizontal displacement {peak*1000:.3f} mm at frame {peak_frame}, "
              f"final {rows[-1][1]*1000:.3f} mm")
        print(f"  {'frame':>5s} {'disp_mm':>10s} {'|v| m/s':>10s} {'|w| rad/s':>11s} {'contacts':>9s}")
        shown = 0
        for r in rows:
            if r[3] > 1e-6 or r[4] > 0 or r[0] % 12 == 0:
                print(f"  {r[0]:5d} {r[1]*1000:10.4f} {r[2]:10.5f} {r[3]:11.5f} {r[4]:9d}")
                shown += 1
            if shown > 40:
                break
        solver.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
