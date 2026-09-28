"""V5.5 stage 03: isolate which physics-engine parameter breaks mesh-plane collision.

Evidence so far:
  * a control BOX rests on the plane, and a control SPHERE rests on the plane;
  * a GEOM_MESH bottle proxy falls straight through the SAME plane with 0 contacts;
  * in an earlier diagnostic the mesh DID collide (4 contact points) -- and the only
    difference is the engine parameters that were set.

This tests the parameters one at a time against a mesh body, so the cause is identified
instead of worked around, and the safe configuration is recorded.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pybullet as pb

DT = 1.0 / 480.0
PROPS = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat/props")
SUPPORT = 0.510600


def load_obj(path: Path):
    verts, faces = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    raw = tok.split("/")[0]
                    if raw:
                        i = int(raw)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return np.asarray(verts, float), np.asarray(faces, np.int64)


def merged(sub: str):
    files = sorted((PROPS / "bottle_assembly" / sub).glob("*.obj"))
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def trial(V, F, mass, *, num_substeps, cone_friction, solver_iters, contact_breaking):
    cid = pb.connect(pb.DIRECT)
    try:
        pb.setGravity(0, 0, -9.81, physicsClientId=cid)
        kw = {"fixedTimeStep": DT}
        if solver_iters is not None:
            kw["numSolverIterations"] = solver_iters
        if num_substeps is not None:
            kw["numSubSteps"] = num_substeps
        if cone_friction is not None:
            kw["enableConeFriction"] = cone_friction
        if contact_breaking is not None:
            kw["contactBreakingThreshold"] = contact_breaking
        pb.setPhysicsEngineParameter(physicsClientId=cid, **kw)

        shape = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                        physicsClientId=cid)
        plane = pb.createMultiBody(0, shape, basePosition=(0.0, 0.0, SUPPORT),
                                   physicsClientId=cid)
        plo = V.min(axis=0)
        shift = SUPPORT - plo[2]
        cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                     indices=F.ravel().tolist(), physicsClientId=cid)
        body = pb.createMultiBody(mass, cs, basePosition=(0.0, 0.0, shift),
                                  physicsClientId=cid)
        for _ in range(int(1.5 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
        cps = pb.getContactPoints(bodyA=body, bodyB=plane, physicsClientId=cid)
        fell = pos[2] < shift - 0.05
        return {"fell": bool(fell), "z": pos[2], "spawn_z": shift,
                "contacts": len(cps), "shape_id": cs}
    finally:
        pb.disconnect(cid)


def main() -> int:
    V, F = merged("vhacd")
    print(f"proxy: {len(F)} tri, height {V[:,2].max()-V[:,2].min():.6f} m")

    print("\n=== full parameter matrix (mesh body vs plane) ===")
    print(f"{'numSub':>7} {'cone':>6} {'iters':>6} {'brk':>8} | {'result':>10} "
          f"{'contacts':>9}")
    good = []
    for ns, cf, it, cb in itertools.product(
            (None, 1, 4), (None, 0, 1), (None, 120), (None, 0.001)):
        r = trial(V, F, 0.77, num_substeps=ns, cone_friction=cf,
                  solver_iters=it, contact_breaking=cb)
        status = "FELL" if r["fell"] else "rests"
        print(f"{str(ns):>7} {str(cf):>6} {str(it):>6} {str(cb):>8} | {status:>10} "
              f"{r['contacts']:>9}")
        if not r["fell"]:
            good.append((ns, cf, it, cb))

    print(f"\n=== configurations where the mesh rests: {len(good)} ===")
    for g in good:
        print(f"  numSubSteps={g[0]} enableConeFriction={g[1]} "
              f"numSolverIterations={g[2]} contactBreakingThreshold={g[3]}")

    # Which single parameter, toggled alone from the minimal config, causes the failure?
    print("\n=== single-parameter effect (baseline = fixedTimeStep only) ===")
    base = trial(V, F, 0.77, num_substeps=None, cone_friction=None,
                 solver_iters=None, contact_breaking=None)
    print(f"  baseline: {'FELL' if base['fell'] else 'rests'} "
          f"contacts={base['contacts']}")
    for label, kw in (
            ("numSolverIterations=120", {"solver_iters": 120}),
            ("numSubSteps=1", {"num_substeps": 1}),
            ("enableConeFriction=1", {"cone_friction": 1}),
            ("contactBreakingThreshold=0.001", {"contact_breaking": 0.001}),
    ):
        full = {"num_substeps": None, "cone_friction": None,
                "solver_iters": None, "contact_breaking": None}
        full.update(kw)
        r = trial(V, F, 0.77, **full)
        print(f"  {label:34s}: {'FELL' if r['fell'] else 'rests':>6} "
              f"contacts={r['contacts']:3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
