"""V5.5 stage 03 section 5: the static tray collider -- root cause and final form.

Two independent measurements disagree for the ORIGINAL tray mesh, and that disagreement is the
whole story:

  * a downward RAYCAST against `static_Vassoio.obj` finds its surface at z = 0.510600, i.e. the
    tray floor, exactly where stage 05 section 1 measured the props to stand;
  * but PHYSICS disagrees: a 20 mm probe box dropped on the same mesh comes to rest with its
    bottom at z = 0.523247, which is the tray's RIM plane (0.522260) plus ~1 mm.

The tray is a shallow open dish (floor 0.510600, rim 0.522260). Its convex hull is a solid
block whose top is the rim plane. So the reading is that pybullet is colliding against the
HULL, not the mesh: a static `GEOM_MESH` is hulled unless it is explicitly flagged concave.

That is tested here directly, and it decides the final collider, because if the flag works then
the EXACT authored tray can be used as the static collider -- far better than a 71-part
approximation, and with no bias at all.

  T1 probe on the tray mesh, no flags              -> expected to rest at the rim (hull)
  T2 the same mesh with GEOM_FORCE_CONCAVE_TRIMESH -> expected to rest at the floor
  T3 the 71-part V-HACD compound                   -> measured for comparison
  T4 re-confirm the dynamic GEOM_MESH vs GEOM_PLANE failure in a CLEAN world

Then props are planted with ZERO initial penetration by solving the spawn height against
pybullet's own narrowphase: raise, re-query, repeat until no penetration remains. That is a
geometric placement correction verified by the engine, not a physics patch -- no velocity,
force or constraint is ever applied to a body, and the body still settles purely under gravity.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pybullet as pb

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
STATIC_PROXIES = SCENES / "static_proxies" / "vassoio_default"

DT = 1.0 / 480.0
VISUAL_FLOOR_Z = 0.510600
RIM_Z = 0.522260
CONTACT_FACE_TOL_M = 0.002
PEN_TOL_M = 1e-4               # 04 cap is min(1 mm, t_min*5%); 0.1 mm is far inside it

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


def probe_support(cid, shapes: list, lo, hi, label):
    """Drop small boxes across the footprint and report the resting bottom height."""
    half = 0.008
    bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3,
                                 physicsClientId=cid)
    xs = np.linspace(lo[0] + 0.25 * (hi[0] - lo[0]), hi[0] - 0.25 * (hi[0] - lo[0]), 3)
    ys = np.linspace(lo[1] + 0.25 * (hi[1] - lo[1]), hi[1] - 0.25 * (hi[1] - lo[1]), 3)
    bottoms = []
    for x in xs:
        for y in ys:
            pr = pb.createMultiBody(0.05, bs,
                                    basePosition=(float(x), float(y), hi[2] + 0.03),
                                    physicsClientId=cid)
            for _ in range(int(2.0 / DT)):
                pb.stepSimulation(physicsClientId=cid)
            p, _ = pb.getBasePositionAndOrientation(pr, physicsClientId=cid)
            n = sum(len(pb.getContactPoints(bodyA=pr, bodyB=b, physicsClientId=cid))
                    for b in shapes)
            if n > 0:
                bottoms.append(float(p[2] - half))
            pb.removeBody(pr, physicsClientId=cid)
    med = float(np.median(bottoms)) if bottoms else float("nan")
    print(f"  {label:34s} support={med:.6f}  vs floor {(med-VISUAL_FLOOR_Z)*1000:+8.3f} mm "
          f" vs rim {(med-RIM_Z)*1000:+8.3f} mm  ({len(bottoms)}/9 probes)")
    return med


def main() -> int:
    report: dict = {"visual_floor_z": VISUAL_FLOOR_Z, "rim_z": RIM_Z}
    shell = RUNTIME / "static_Vassoio.obj"
    sv, sf = load_obj(shell)
    slo, shi = sv.min(axis=0), sv.max(axis=0)

    print("=" * 78)
    print("=== T4: dynamic GEOM_MESH vs GEOM_PLANE, re-confirmed in a CLEAN world ===")
    cid = new_world()
    try:
        s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                    physicsClientId=cid)
        pl = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, 0.5), physicsClientId=cid)
        v = np.array([[a, b, c] for a in (-0.01, 0.01) for b in (-0.01, 0.01)
                      for c in (-0.01, 0.01)], float)
        f = np.array([[0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7], [0, 5, 1], [0, 4, 5],
                      [2, 3, 7], [2, 7, 6], [0, 6, 2], [0, 4, 6], [1, 5, 7], [1, 7, 3]],
                     np.int64)
        cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=v.tolist(),
                                     indices=f.ravel().tolist(), physicsClientId=cid)
        b = pb.createMultiBody(0.05, cs, basePosition=(0.0, 0.0, 0.52),
                               physicsClientId=cid)
        for _ in range(int(1.0 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        n = len(pb.getContactPoints(bodyA=b, bodyB=pl, physicsClientId=cid))
        fell = p[2] < 0.4
        print(f"  cube GEOM_MESH on GEOM_PLANE: z={p[2]:9.5f} contacts={n} "
              f"-> {'FELL (limitation CONFIRMED)' if fell else 'RESTS'}")
        report["mesh_vs_plane_fell"] = bool(fell)
        # And the same cube on the tray mesh, to show mesh-vs-mesh is fine.
        ts = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(shell),
                                     physicsClientId=cid)
        tb = pb.createMultiBody(0, ts, basePosition=(0, 0, 0), physicsClientId=cid)
        b2 = pb.createMultiBody(0.05, cs,
                                basePosition=(float(np.mean([slo[0], shi[0]])),
                                              float(np.mean([slo[1], shi[1]])),
                                              shi[2] + 0.03), physicsClientId=cid)
        for _ in range(int(2.0 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p2, _ = pb.getBasePositionAndOrientation(b2, physicsClientId=cid)
        n2 = len(pb.getContactPoints(bodyA=b2, bodyB=tb, physicsClientId=cid))
        print(f"  same cube GEOM_MESH on the tray GEOM_MESH: z={p2[2]:.6f} contacts={n2} "
              f"-> mesh-vs-mesh works")
        report["mesh_vs_mesh_rests"] = bool(n2 > 0)
    finally:
        pb.disconnect(cid)

    print("\n=== T1/T2/T3: what does the tray collider actually support? ===")
    cid = new_world()
    try:
        # T1: original mesh, no flags.
        s1 = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(shell),
                                     physicsClientId=cid)
        t1 = pb.createMultiBody(0, s1, basePosition=(0, 0, 0), physicsClientId=cid)
        med1 = probe_support(cid, [t1], slo, shi, "T1 tray mesh, no flags")

        # T2: the same mesh, flagged concave.
        s2 = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(shell),
                                     flags=pb.GEOM_FORCE_CONCAVE_TRIMESH,
                                     physicsClientId=cid)
        t2 = pb.createMultiBody(0, s2, basePosition=(0, 0, 0), physicsClientId=cid)
        med2 = probe_support(cid, [t2], slo, shi, "T2 tray mesh FORCE_CONCAVE")

        # T3: the V-HACD compound.
        parts = sorted(STATIC_PROXIES.glob("part*.obj"))
        shapes = [pb.createCollisionShape(pb.GEOM_MESH, fileName=str(p),
                                          physicsClientId=cid) for p in parts]
        t3 = [pb.createMultiBody(0, s, basePosition=(0, 0, 0), physicsClientId=cid)
              for s in shapes]
        vv = np.vstack([load_obj(p)[0] for p in parts])
        med3 = probe_support(cid, t3, vv.min(axis=0), vv.max(axis=0),
                             f"T3 vhacd compound ({len(parts)} parts)")

        report["T1_mesh_no_flags_support_z"] = med1
        report["T2_mesh_concave_support_z"] = med2
        report["T3_vhacd_compound_support_z"] = med3
        report["hull_hypothesis_supported"] = bool(
            abs(med1 - RIM_Z) < 0.002 and abs(med2 - VISUAL_FLOOR_Z) < 0.002)

        # Choose the most faithful collider that is inside the 03 contact-face bound.
        cands = []
        if abs(med2 - VISUAL_FLOOR_Z) <= CONTACT_FACE_TOL_M:
            cands.append(("mesh_concave_exact", med2, [str(shell)],
                          pb.GEOM_FORCE_CONCAVE_TRIMESH, "the exact authored tray mesh"))
        if abs(med3 - VISUAL_FLOOR_Z) <= CONTACT_FACE_TOL_M:
            cands.append(("vhacd_compound", med3, [str(p) for p in parts], 0,
                          f"{len(parts)} convex parts"))
        cands.sort(key=lambda c: abs(c[1] - VISUAL_FLOOR_Z))
        chosen = cands[0] if cands else None
        report["candidates"] = [
            {"name": c[0], "support_z": c[1], "n_files": len(c[2]),
             "bias_m": c[1] - VISUAL_FLOOR_Z, "note": c[4]} for c in cands]
        print(f"\n  candidate colliders within the {CONTACT_FACE_TOL_M*1000:.0f} mm bound: "
              f"{[c[0] for c in cands]}")
        if chosen:
            print(f"  CHOSEN: {chosen[0]} (bias {(chosen[1]-VISUAL_FLOOR_Z)*1000:+.4f} mm, "
                  f"{chosen[4]})")
            report["chosen_tray_collider"] = chosen[0]
            report["chosen_bias_m"] = chosen[1] - VISUAL_FLOOR_Z

            # ---- zero-penetration prop planting against the chosen collider --------
            print("\n=== prop placement: solve spawn height for ZERO initial penetration ===")
            pb.removeBody(t1, physicsClientId=cid)
            pb.removeBody(t2, physicsClientId=cid)
            keep = t3 if chosen[0] == "vhacd_compound" else (
                [t2] if chosen[0] == "mesh_concave_exact" else [])
            for b in ([t1, t2] if chosen[0] == "mesh_concave_exact" else t3):
                if b not in keep:
                    pb.removeBody(b, physicsClientId=cid)

            decision = json.loads((SCENES / "props" / "proxy_decision.json").read_text(
                encoding="utf-8"))
            placement: dict = {}
            for name in ("bottle_assembly", "glass_a", "glass_b"):
                d = decision.get(name, {})
                restore = -np.asarray(d.get("recentre_offset_m", [0.0] * 3), float)
                entry = {}
                for label in ("vhacd", "hull"):
                    files = sorted((SCENES / "props" / name / label).glob("*.obj"))
                    if not files:
                        continue
                    V, F = merged(files)
                    world_lo = V.min(axis=0) + restore
                    base_z = VISUAL_FLOOR_Z - world_lo[2]
                    cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                                 indices=F.ravel().tolist(),
                                                 physicsClientId=cid)
                    body = None
                    pen = None
                    tries = []
                    for _ in range(40):
                        if body is not None:
                            pb.removeBody(body, physicsClientId=cid)
                        spawn = restore + np.array([0.0, 0.0, base_z])
                        body = pb.createMultiBody(PROP_MASS[name], cs,
                                                  basePosition=spawn.tolist(),
                                                  physicsClientId=cid)
                        pb.changeDynamics(body, -1, lateralFriction=0.6, restitution=0.0,
                                          physicsClientId=cid)
                        pb.performCollisionDetection(physicsClientId=cid)
                        cps = pb.getContactPoints(bodyA=body, physicsClientId=cid)
                        pen = max((-float(c[8]) for c in cps), default=0.0)
                        tries.append(round(pen, 9))
                        if pen <= PEN_TOL_M:
                            break
                        base_z += pen * 1.05
                    if body is None:
                        continue
                    # Settle under gravity only -- no force, velocity or constraint is applied.
                    pb.performCollisionDetection(physicsClientId=cid)
                    cps0 = pb.getContactPoints(bodyA=body, physicsClientId=cid)
                    pen0 = max((-float(c[8]) for c in cps0), default=0.0)
                    for _ in range(int(1.2 / DT)):
                        pb.stepSimulation(physicsClientId=cid)
                    pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                    lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
                    speed, spin = float(np.linalg.norm(lin)), float(np.linalg.norm(ang))
                    n = len(pb.getContactPoints(bodyA=body, physicsClientId=cid))
                    rec = {
                        "triangles": int(len(F)),
                        "planted_bottom_z": round(
                            float(world_lo[2] + base_z), 9),
                        "initial_penetration_m": round(float(pen0), 9),
                        "placement_iterations": len(tries),
                        "penetration_trace_m": tries,
                        "settled_origin_z": round(float(pos[2]), 9),
                        "settled_speed_m_s": round(speed, 9),
                        "settled_spin_rad_s": round(spin, 9),
                        "contacts": n,
                        "at_rest": bool(n > 0 and speed < 1e-3 and spin < 1e-3),
                        "zero_initial_penetration": bool(pen0 <= PEN_TOL_M),
                    }
                    entry[label] = rec
                    print(f"  {name:18s} {label:6s} planted_z={rec['planted_bottom_z']:.6f} "
                          f"init_pen={pen0*1000:7.4f} mm ({len(tries)} iter) "
                          f"contacts={n:3d} speed={speed:.1e} at_rest={rec['at_rest']}")
                    pb.removeBody(body, physicsClientId=cid)
                placement[name] = entry
            report["placement"] = placement
    finally:
        pb.disconnect(cid)

    print("\n" + "=" * 78)
    print("=== VERDICT ===")
    print(f"  hull hypothesis (mesh hulled unless flagged concave): "
          f"{report.get('hull_hypothesis_supported')}")
    print(f"  mesh-vs-mesh works: {report.get('mesh_vs_mesh_rests')}, "
          f"mesh-vs-plane fell: {report.get('mesh_vs_plane_fell')}")
    ch = report.get("chosen_tray_collider")
    print(f"  chosen tray collider: {ch} "
          f"(bias {report.get('chosen_bias_m', float('nan'))*1000:+.4f} mm)")
    allz = True
    for name, entry in report.get("placement", {}).items():
        for label, r in entry.items():
            allz &= r["zero_initial_penetration"] and r["at_rest"]
            print(f"  {name:18s} {label:6s} init_pen={r['initial_penetration_m']*1000:7.4f} mm "
                  f"at_rest={r['at_rest']}")
    ok = bool(ch) and allz
    out = SCENES / "tray_collider_final.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    print(f"\nSTATIC SUPPORT + ZERO-PENETRATION PLACEMENT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
