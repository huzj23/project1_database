"""V5.5 stage 03/04: CORRECTED root cause -- the GEOM_MESH creation ROUTE, not the shape pair.

An earlier conclusion in this work ("GEOM_MESH does not collide with GEOM_PLANE in this pybullet
build") was WRONG, and the shape-pair matrix exposed it. Reading that matrix by route:

    dynamic mesh via vertices/indices  vs plane         -> FELL
    dynamic mesh via vertices/indices  vs tray_concave  -> FELL
    dynamic mesh via vertices/indices  vs box_floor     -> RESTS
    dynamic mesh via fileName          vs plane         -> RESTS (+0.978 mm)
    dynamic mesh via fileName          vs box_floor     -> RESTS (+0.978 mm)
    dynamic mesh via fileName          vs tray_concave  -> touches, +0.975 mm
    dynamic mesh via fileName          vs tray_hull     -> RESTS (+13.636 mm = hulled)

So the variable is NOT GEOM_PLANE, and not the mesh quality: `fileName=` collides with the
plane perfectly well. The failure follows `vertices=`/`indices=`, which builds a non-functional
collider against PLANE and against a concave trimesh while still working against a convex box.
Every one of the 36 engine-parameter combinations failed because they all used that same route,
and the control BOX/SPHERE rested because primitives never use it.

This file proves the route is the variable with the STRONGEST possible control: the SAME cube,
the SAME plane, changing only how the collision shape is created. It then re-validates the real
props on the real static environment using the route that works, and corrects the record.

  P1 identical cube mesh, fileName vs vertices/indices, on the identical plane;
  P2 the real prop proxies via fileName on the real concave tray collider, settled long enough
     to distinguish "slow creep" from "at rest";
  P3 zero-penetration placement, with the penetration measured by the engine.
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
PEN_TOL_M = 1e-4
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


def write_obj(path: Path, v, f):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as h:
        for p in v:
            h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
        for t in f:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")


def merged(files):
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 numSubSteps=1, enableConeFriction=1,
                                 physicsClientId=cid)
    return cid


def main() -> int:
    report: dict = {"floor_z": FLOOR_Z, "rim_z": RIM_Z}
    tmp = SCENES / "route_test"
    tmp.mkdir(parents=True, exist_ok=True)

    # ---------------- P1: identical mesh, identical plane, route is the only variable ----
    print("=" * 84)
    print("=== P1: the SAME cube mesh and the SAME plane, only the creation route differs ===")
    half = 0.01
    cv = np.array([[a, b, c] for a in (-half, half) for b in (-half, half)
                   for c in (-half, half)], float)
    cf = np.array([[0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7], [0, 5, 1], [0, 4, 5],
                   [2, 3, 7], [2, 7, 6], [0, 6, 2], [0, 4, 6], [1, 5, 7], [1, 7, 3]],
                  np.int64)
    cube_obj = tmp / "cube.obj"
    write_obj(cube_obj, cv, cf)

    p1 = {}
    for route in ("vertices_indices", "fileName", "vertices_indices_with_filename_arg"):
        cid = new_world()
        try:
            ps = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                         physicsClientId=cid)
            pl = pb.createMultiBody(0, ps, basePosition=(0.0, 0.0, 0.5),
                                    physicsClientId=cid)
            if route == "vertices_indices":
                cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=cv.tolist(),
                                             indices=cf.ravel().tolist(),
                                             physicsClientId=cid)
            elif route == "fileName":
                cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(cube_obj),
                                             physicsClientId=cid)
            else:
                cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(cube_obj),
                                             vertices=cv.tolist(),
                                             indices=cf.ravel().tolist(),
                                             physicsClientId=cid)
            b = pb.createMultiBody(0.05, cs, basePosition=(0.0, 0.0, 0.52),
                                   physicsClientId=cid)
            for _ in range(int(1.5 / DT)):
                pb.stepSimulation(physicsClientId=cid)
            pos, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
            n = len(pb.getContactPoints(bodyA=b, bodyB=pl, physicsClientId=cid))
            rests = bool(n > 0 and abs(pos[2] - 0.51) < 0.002)
            p1[route] = {"shape_id": int(cs), "settled_z": round(float(pos[2]), 6),
                         "contacts": n, "rests": rests}
            print(f"  {route:34s} shape_id={cs:4d} settled_z={pos[2]:10.6f} "
                  f"contacts={n} -> {'RESTS' if rests else 'FELL THROUGH'}")
        finally:
            pb.disconnect(cid)
    report["P1_cube_on_plane_by_route"] = p1
    route_is_the_variable = (p1["fileName"]["rests"] and not p1["vertices_indices"]["rests"])
    print(f"\n  ROUTE IS THE VARIABLE: {route_is_the_variable}")
    report["route_is_the_root_cause"] = bool(route_is_the_variable)
    print("  -> the earlier claim that 'GEOM_MESH does not collide with GEOM_PLANE' was a")
    print("     misdiagnosis: the mesh collides with the plane fine when loaded from a file.")

    # ---------------- P2: real props via fileName on the real concave tray ---------------
    print("\n" + "=" * 84)
    print("=== P2: real prop proxies via fileName on the real concave tray collider ===")
    print("  NOTE the prop mesh stays RECENTRED (small local coordinates) and the BODY ORIGIN is")
    print("  placed at the prop's world position. Writing world coordinates into the mesh")
    print("  instead puts the geometry ~7.4 m from its body origin, which breaks contact")
    print("  generation for a concave trimesh in this build -- measured, not assumed.")
    tray = RUNTIME / "static_Vassoio.obj"
    decision = json.loads((SCENES / "props" / "proxy_decision.json").read_text(
        encoding="utf-8"))
    p2: dict = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        d = decision.get(name, {})
        restore = -np.asarray(d.get("recentre_offset_m", [0.0] * 3), float)
        p2[name] = {}
        for label in ("vhacd", "hull", "visual"):
            files = sorted((SCENES / "props" / name / label).glob("*.obj"))
            if not files:
                continue
            V, F = merged(files)
            obj_path = tmp / f"{name}_{label}_local.obj"
            write_obj(obj_path, V, F)
            world_lo = V.min(axis=0) + restore

            cid = new_world()
            try:
                ts = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tray),
                                             flags=pb.GEOM_FORCE_CONCAVE_TRIMESH,
                                             physicsClientId=cid)
                tb = pb.createMultiBody(0, ts, basePosition=(0, 0, 0),
                                        physicsClientId=cid)
                pb.changeDynamics(tb, -1, lateralFriction=0.6, restitution=0.0,
                                  physicsClientId=cid)
                cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj_path),
                                             physicsClientId=cid)
                base_z = FLOOR_Z - world_lo[2]

                # Placement: raise until pybullet's own narrowphase reports no penetration.
                #
                # SIGN: `getContactPoints()[8]` is the SEPARATION distance, so penetration is
                # `max(0, -min(separation))`. Taking `max(-separation)` directly yields a
                # NEGATIVE "penetration" whenever the nearest contact is merely close, which
                # made the original loop break on its first iteration and record a bogus
                # negative value.
                def penetration(cid_, body_):
                    cps = pb.getContactPoints(bodyA=body_, physicsClientId=cid_)
                    dists = [float(c[8]) for c in cps]
                    return max(0.0, -min(dists)) if dists else 0.0, len(cps)

                trace = []
                pen0 = 0.0
                n0 = 0
                body = None
                for _ in range(50):
                    if body is not None:
                        pb.removeBody(body, physicsClientId=cid)
                    spawn = (restore + np.array([0.0, 0.0, base_z])).tolist()
                    body = pb.createMultiBody(PROP_MASS[name], cs, basePosition=spawn,
                                              physicsClientId=cid)
                    pb.changeDynamics(body, -1, lateralFriction=0.6, restitution=0.0,
                                      physicsClientId=cid)
                    pb.performCollisionDetection(physicsClientId=cid)
                    pen0, n0 = penetration(cid, body)
                    trace.append(round(float(pen0), 9))
                    if pen0 <= PEN_TOL_M:
                        break
                    base_z += pen0 * 1.05
                # Settle for 3 s so slow creep is distinguishable from rest.
                for _ in range(int(3.0 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
                speed, spin = float(np.linalg.norm(lin)), float(np.linalg.norm(ang))
                pen_final, n = penetration(cid, body)
                bottom = float(pos[2]) + float(V.min(axis=0)[2])
                rec = {
                    "triangles": int(len(F)),
                    "planted_bottom_z": round(float(world_lo[2] + base_z), 9),
                    "initial_penetration_m": round(float(pen0), 9),
                    "contacts_at_placement": n0,
                    "placement_iterations": len(trace),
                    "penetration_trace_m": trace,
                    "settled_origin_z": round(float(pos[2]), 9),
                    "settled_bottom_z": round(bottom, 9),
                    "settled_speed_m_s": round(speed, 9),
                    "settled_spin_rad_s": round(spin, 9),
                    "final_penetration_m": round(float(pen_final), 9),
                    "bias_vs_floor_m": round(bottom - FLOOR_Z, 9),
                    "contacts": n,
                    "at_rest": bool(n > 0 and speed < 1e-3 and spin < 1e-3),
                    "zero_initial_penetration": bool(pen0 <= PEN_TOL_M),
                    "rests_on_floor": bool(n > 0 and abs(bottom - FLOOR_Z) <= 0.002),
                }
            finally:
                pb.disconnect(cid)
            p2[name][label] = rec
            print(f"  {name:18s} {label:6s} tri={len(F):6d} plant_z={rec['planted_bottom_z']:.6f} "
                  f"init_pen={pen0*1000:7.4f} mm ({len(trace)} iter) "
                  f"settled_bottom={bottom:.6f} bias={(bottom-FLOOR_Z)*1000:+7.3f} mm "
                  f"contacts={n:3d} speed={speed:.2e} spin={spin:.2e} "
                  f"at_rest={rec['at_rest']}")
    report["P2_props_via_filename"] = p2

    # ---------------- verdict ----------------------------------------------------------
    print("\n" + "=" * 84)
    print("=== VERDICT ===")
    print(f"  route is the root cause of the free fall: {route_is_the_variable}")
    allok = True
    for name, entry in p2.items():
        for label, r in entry.items():
            allok &= r["zero_initial_penetration"] and r["at_rest"] and r["rests_on_floor"]
            print(f"  {name:18s} {label:6s} init_pen={r['initial_penetration_m']*1000:7.4f} mm "
                  f"bias={r['bias_vs_floor_m']*1000:+7.3f} mm "
                  f"at_rest={r['at_rest']} on_floor={r['rests_on_floor']}")
    report["all_props_valid"] = bool(allok)
    out = SCENES / "route_root_cause.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    print(f"\nPROXY VALIDATION ON THE REAL ENVIRONMENT: {'PASS' if allok else 'FAIL'}")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
