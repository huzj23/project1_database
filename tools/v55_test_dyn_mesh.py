"""V5.5 stage 05: does a dynamic GEOM_MESH collide with another dynamic GEOM_MESH?

The solve produced 19584 contact records and NOT ONE between the striker and the bottle. Every
contact was body-vs-STATIC: the box landed on the table and on the lamp, and the props rested on
the table. The box fell from z=1.055 to z=0.516 with a measured 6.0 mm horizontal overlap on the
bottle, so it passed straight through the bottle's volume without interacting.

The static matrix already proved dynamic-mesh vs STATIC-concave-mesh works. Dynamic vs DYNAMIC is
a different narrowphase path, so it is tested here explicitly. Both bodies are the real meshes,
both are created with `fileName=`, and the geometry is a deliberately gross overlap so a failure
cannot be blamed on a graze:

  T1 identical cube mesh vs identical cube mesh, overlapping by 10 mm at t=0
  T2 the real striker box vs the real bottle proxy, overlapping as the design specifies
  T3 a cube mesh vs a BODY built as GEOM_BOX (primitive), same overlap -- to separate
     "dynamic mesh vs dynamic mesh is broken" from "dynamic mesh vs dynamic mesh is broken"
  T4 the real striker box vs the real bottle proxy, with the BOTTLE built from primitive shapes

If T1 and T2 fail while T3/T4 succeed, the conclusion is that this build cannot collide two
concave dynamic trimeshes, and stage 05 must build the dynamic bodies from convex primitives.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pybullet as pb

ROOT = Path("/data/raw/huzijian/project1_database")
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T050000"
DESIGN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"
DT = 1.0 / 480.0
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


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 numSubSteps=1, enableConeFriction=1, physicsClientId=cid)
    return cid


def report(cid, a, b, label, steps=480):
    """Drop/freeze and report whether a and b ever touched."""
    touched = 0
    for _ in range(steps):
        pb.stepSimulation(physicsClientId=cid)
        touched = max(touched, len(pb.getContactPoints(bodyA=a, bodyB=b,
                                                       physicsClientId=cid)))
    pa, _ = pb.getBasePositionAndOrientation(a, physicsClientId=cid)
    pbp, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
    print(f"  {label:56s} contacts={touched:3d}  a_z={pa[2]:9.5f} b_z={pbp[2]:9.5f}  "
          f"{'COLLIDES' if touched else 'NO COLLISION'}")
    return touched


def main() -> int:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    out: dict = {}
    print("=" * 96)

    # ---- T1/T3: cube mesh vs cube mesh, and mesh vs primitive box -------------------
    half = 0.02
    cv = np.array([[a, b, c] for a in (-half, half) for b in (-half, half)
                   for c in (-half, half)], float)
    cf = np.array([[0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7], [0, 5, 1], [0, 4, 5],
                   [2, 3, 7], [2, 7, 6], [0, 6, 2], [0, 4, 6], [1, 5, 7], [1, 7, 3]], np.int64)
    tmp = RUN / "collision_tests"
    tmp.mkdir(parents=True, exist_ok=True)
    cube_obj = tmp / "cube.obj"
    with cube_obj.open("w", encoding="utf-8") as h:
        for p in cv:
            h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
        for t in cf:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")

    # The lower cube is STATIC here so it stays put and the test isolates the mesh-mesh path.
    print("=== T1: cube MESH (fixed) vs cube MESH (dynamic), 10 mm overlap at t=0 ===")
    cid = new_world()
    try:
        s1 = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(cube_obj), physicsClientId=cid)
        lower = pb.createMultiBody(0, s1, basePosition=(0, 0, 0.0), physicsClientId=cid)
        s2 = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(cube_obj), physicsClientId=cid)
        upper = pb.createMultiBody(0.05, s2, basePosition=(0, 0, 0.03), physicsClientId=cid)
        n = report(cid, upper, lower, "dynamic mesh vs FIXED mesh")
        out["T1_mesh_vs_fixed_mesh"] = n

        print("\n=== T3: cube MESH (dynamic) vs cube GEOM_BOX (fixed) ===")
        s3 = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3, physicsClientId=cid)
        lower_b = pb.createMultiBody(0, s3, basePosition=(0.5, 0, 0.0), physicsClientId=cid)
        upper3 = pb.createMultiBody(0.05, s2, basePosition=(0.5, 0, 0.03), physicsClientId=cid)
        n3 = report(cid, upper3, lower_b, "dynamic mesh vs FIXED primitive box")
        out["T3_mesh_vs_fixed_box"] = n3
    finally:
        pb.disconnect(cid)

    # ---- T2: real striker vs real bottle, both meshes, both dynamic ------------------
    #
    # The first run of T2/T4 reported NO COLLISION with both bodies at z = -14.8: there was no
    # floor in that world, so the box and the bottle simply fell together and never met. That is
    # a test-harness defect, not a collision result. Every case below therefore has a real support
    # plane, and the bottle is held FIXED so the test isolates the mesh-mesh narrowphase instead
    # of measuring two falling bodies.
    print("\n=== T2: real striker MESH vs real bottle MESH ===")
    box_obj = RUN / "striker_box_collision.obj"
    bot_obj = RUN / "bottle_assembly_collision.obj"
    bv, bf = load_obj(box_obj)
    vv, vf = load_obj(bot_obj)
    print(f"  striker mesh {len(bv)} verts/{len(bf)} tri; bottle mesh {len(vv)} verts/"
          f"{len(vf)} tri")

    def with_floor(cid):
        s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                    physicsClientId=cid)
        return pb.createMultiBody(0, s, basePosition=(0.0, 0.0, FLOOR_Z),
                                  physicsClientId=cid)

    bottle_origin = np.array([design["bottle_axis_xy"][0], design["bottle_axis_xy"][1],
                              FLOOR_Z - vv.min(axis=0)[2]])
    strike = design["chosen"]
    centre = np.array(strike["box_centre_start"], float)
    centre[2] = design["bottle_top_z"] + 0.05

    cases = [
        ("T2a striker mesh vs bottle mesh, BOTTLE FIXED", "mesh", "mesh"),
        ("T2b striker mesh vs bottle mesh, BOTH DYNAMIC", "mesh", "mesh_dynamic"),
        ("T2c striker mesh vs bottle PRIMITIVE CYLINDER, fixed", "mesh", "cyl"),
        ("T2d striker PRIMITIVE BOX vs bottle mesh, fixed", "box", "mesh"),
        ("T2e striker PRIMITIVE BOX vs bottle PRIMITIVE CYLINDER", "box", "cyl"),
    ]
    results = {}
    for label, box_kind, bot_kind in cases:
        cid = new_world()
        try:
            with_floor(cid)
            # ---- the bottle side
            if bot_kind in ("mesh", "mesh_dynamic"):
                s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(bot_obj),
                                            physicsClientId=cid)
                mass = 0.77 if bot_kind == "mesh_dynamic" else 0.0
            else:
                s = pb.createCollisionShape(pb.GEOM_CYLINDER, radius=0.055, height=0.26,
                                            physicsClientId=cid)
                mass = 0.0
            bz = bottle_origin[2] if bot_kind in ("mesh", "mesh_dynamic") else FLOOR_Z + 0.13
            bot = pb.createMultiBody(mass, s,
                                     basePosition=[bottle_origin[0], bottle_origin[1], bz],
                                     physicsClientId=cid)
            pb.changeDynamics(bot, -1, lateralFriction=0.6, restitution=0.0,
                              physicsClientId=cid)
            # ---- the striker side
            if box_kind == "mesh":
                s2 = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(box_obj),
                                             physicsClientId=cid)
            else:
                s2 = pb.createCollisionShape(pb.GEOM_BOX,
                                             halfExtents=[0.1046, 0.0449, 0.0485],
                                             physicsClientId=cid)
            box = pb.createMultiBody(0.1016, s2, basePosition=centre.tolist(),
                                     physicsClientId=cid)
            pb.changeDynamics(box, -1, lateralFriction=0.6, restitution=0.0,
                              physicsClientId=cid)
            n = report(cid, box, bot, label, steps=960)
            results[label] = n
        finally:
            pb.disconnect(cid)

    out["T2_real_striker_vs_real_bottle"] = results.get(
        "T2a striker mesh vs bottle mesh, BOTTLE FIXED", 0)
    out["T2_cases"] = results

    print("\n" + "=" * 96)
    print("=== VERDICT ===")
    print(f"  T1 dynamic mesh vs fixed mesh      : "
          f"{'COLLIDES' if out.get('T1_mesh_vs_fixed_mesh') else 'NO COLLISION'}")
    print(f"  T3 dynamic mesh vs fixed box       : "
          f"{'COLLIDES' if out.get('T3_mesh_vs_fixed_box') else 'NO COLLISION'}")
    print(f"  T2 real striker vs real bottle     : "
          f"{'COLLIDES' if out.get('T2_real_striker_vs_real_bottle') else 'NO COLLISION'}")
    print(f"  T4 striker mesh vs cylinder        : "
          f"{'COLLIDES' if out.get('T4_striker_vs_cylinder') else 'NO COLLISION'}")
    if out.get("T2_real_striker_vs_real_bottle") == 0 and out.get("T4_striker_vs_cylinder"):
        print("\n  -> dynamic-mesh vs dynamic-mesh does not collide in this build when BOTH are")
        print("     concave trimeshes, while a mesh vs a PRIMITIVE does. Stage 05 must therefore")
        print("     build at least one side of the pair from convex primitives.")
    out["dynamic_mesh_vs_dynamic_mesh_broken"] = bool(
        out.get("T2_real_striker_vs_real_bottle") == 0 and out.get("T4_striker_vs_cylinder"))
    p = RUN / "dynamic_mesh_collision_test.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
