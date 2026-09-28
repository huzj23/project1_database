"""V5.5 stage 03 sections 4-5: FINAL proxy acceptance on the real static environment.

This closes the collision chain with the configuration the evidence selects:

  ROUTE      dynamic and static meshes are both created with `fileName=`. The
             `vertices=`/`indices=` route is broken in this pybullet build and was the true
             cause of the free fall: the identical cube mesh on the identical plane FELL via
             vertices/indices and RESTED via fileName (P1 in route_root_cause.json). Every one
             of the 36 engine-parameter combinations failed because they all used that route.
  SUPPORT    the static tray is the EXACT authored mesh flagged
             `GEOM_FORCE_CONCAVE_TRIMESH`. An unflagged static GEOM_MESH is silently
             convex-hulled -- a probe rested at the tray RIM (0.523247) instead of its floor
             (0.510590) -- and the flag removes that 12.65 mm error entirely.
  STANDING   props stand on the tray FLOOR z = 0.510600, measured by mesh raycast.
  PLACEMENT  each prop's spawn height is solved against pybullet's own narrowphase until the
             initial penetration is <= 0.1 mm. This is a geometric placement correction that
             the engine verifies; no velocity, force, or constraint is ever applied, and every
             body settles under gravity alone.

Rest is judged from the SETTLED STATE rather than from a single velocity sample: a body is at
rest when it has both stopped translating and stopped rotating, measured over a window with the
drift and the velocity trend recorded. That distinction matters because a spherical or
cylindrical proxy can creep indefinitely on a discretised concave floor, and calling a 3 mm/s
creep "at rest" would misrepresent the scene.

Output: proxy_acceptance_final.json, plus the chosen proxy per prop and the disclosure record.
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
TOL_M = 0.002                 # 03 contact-face bound: min(2 mm, thinnest*5%)
PEN_TOL_M = 1e-4
SETTLE_S = 6.0
WINDOW_S = 1.0

PROPS = {
    "bottle_assembly": {"mass_kg": 0.77, "sealed": True,
                        "allowed": ["vhacd", "hull"],
                        "why": "capped/sealed bottle: 03 permits ONE closed convex proxy"},
    "glass_a": {"mass_kg": 0.113, "sealed": False, "allowed": ["vhacd"],
                "why": "open cup: 03 forbids a single closed hull (a body could rest on the "
                       "mouth instead of entering), so only the decomposition is allowed"},
    "glass_b": {"mass_kg": 0.157, "sealed": False, "allowed": ["vhacd"],
                "why": "open cup: same rule as glass_a"},
}


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


def penetration(cid, body):
    cps = pb.getContactPoints(bodyA=body, physicsClientId=cid)
    dists = [float(c[8]) for c in cps]
    return (max(0.0, -min(dists)) if dists else 0.0), len(cps)


def tray_floor_measurement(shell: Path) -> dict:
    """Confirm the flag fixes the support height, and check whether the floor is level."""
    cid = new_world()
    out: dict = {}
    try:
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(shell),
                                    flags=pb.GEOM_FORCE_CONCAVE_TRIMESH,
                                    physicsClientId=cid)
        pb.createMultiBody(0, s, basePosition=(0, 0, 0), physicsClientId=cid)
        V, F = load_obj(shell)
        lo, hi = V.min(axis=0), V.max(axis=0)
        # A tiny probe slid across the floor reveals any tilt: a level floor leaves it still.
        bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.006] * 3,
                                     physicsClientId=cid)
        xs = np.linspace(lo[0] + 0.25 * (hi[0] - lo[0]), hi[0] - 0.25 * (hi[0] - lo[0]), 5)
        ys = np.linspace(lo[1] + 0.25 * (hi[1] - lo[1]), hi[1] - 0.25 * (hi[1] - lo[1]), 5)
        bottoms, drifts = [], []
        for x in xs:
            for y in ys:
                pr = pb.createMultiBody(0.05, bs,
                                        basePosition=(float(x), float(y), hi[2] + 0.02),
                                        physicsClientId=cid)
                for _ in range(int(2.0 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                p0, _ = pb.getBasePositionAndOrientation(pr, physicsClientId=cid)
                for _ in range(int(WINDOW_S / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                p1, _ = pb.getBasePositionAndOrientation(pr, physicsClientId=cid)
                bottoms.append(float(p0[2] - 0.006))
                drifts.append(float(np.linalg.norm(np.array(p1) - np.array(p0))))
                pb.removeBody(pr, physicsClientId=cid)
        out["support_z_median"] = float(np.median(bottoms))
        out["support_z_min"] = float(min(bottoms))
        out["support_z_max"] = float(max(bottoms))
        out["bias_vs_floor_m"] = float(np.median(bottoms)) - FLOOR_Z
        out["max_probe_drift_per_s_m"] = float(max(drifts))
        out["floor_is_level"] = bool(max(drifts) < 2e-4)
        print(f"  concave tray: support z median {out['support_z_median']:.6f} "
              f"(bias {out['bias_vs_floor_m']*1000:+.4f} mm), "
              f"max probe drift {out['max_probe_drift_per_s_m']*1000:.4f} mm/s, "
              f"level={out['floor_is_level']}")
    finally:
        pb.disconnect(cid)
    return out


def main() -> int:
    tray = RUNTIME / "static_Vassoio.obj"
    decision = json.loads((SCENES / "props" / "proxy_decision.json").read_text(
        encoding="utf-8"))
    report: dict = {"floor_z": FLOOR_Z, "rim_z": RIM_Z, "tolerance_m": TOL_M,
                    "route": "fileName for every mesh collider",
                    "static_tray": "exact authored mesh + GEOM_FORCE_CONCAVE_TRIMESH",
                    "dt": DT, "settle_s": SETTLE_S}

    print("=" * 90)
    print("=== static support: exact authored tray, flagged concave ===")
    report["tray"] = tray_floor_measurement(tray)

    print("\n=== per-prop acceptance ===")
    results: dict = {}
    for name, spec in PROPS.items():
        restore = -np.asarray(decision[name]["recentre_offset_m"], float)
        entry: dict = {"allowed": spec["allowed"], "sealed": spec["sealed"],
                       "why": spec["why"], "candidates": {}}
        for label in ("vhacd", "hull", "visual"):
            files = sorted((SCENES / "props" / name / label).glob("*.obj"))
            if not files:
                continue
            V, F = merged(files)
            world_lo = V.min(axis=0) + restore
            obj_path = SCENES / "props" / name / f"{label}_placed.obj"
            # The mesh keeps its recentred local coordinates; the BODY carries the world
            # position. Baking the world offset into the mesh places geometry metres from its
            # body origin and breaks concave contact generation (measured).
            with obj_path.open("w", encoding="utf-8") as h:
                for p in V:
                    h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
                for t in F:
                    h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")

            cid = new_world()
            try:
                ts = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tray),
                                             flags=pb.GEOM_FORCE_CONCAVE_TRIMESH,
                                             physicsClientId=cid)
                pb.createMultiBody(0, ts, basePosition=(0, 0, 0), physicsClientId=cid)
                cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj_path),
                                             physicsClientId=cid)
                base_z = FLOOR_Z - world_lo[2]

                trace, pen0, n0 = [], 0.0, 0
                body = None
                for _ in range(50):
                    if body is not None:
                        pb.removeBody(body, physicsClientId=cid)
                    spawn = (restore + np.array([0.0, 0.0, base_z])).tolist()
                    body = pb.createMultiBody(spec["mass_kg"], cs, basePosition=spawn,
                                              physicsClientId=cid)
                    pb.changeDynamics(body, -1, lateralFriction=0.6, restitution=0.0,
                                      physicsClientId=cid)
                    pb.performCollisionDetection(physicsClientId=cid)
                    pen0, n0 = penetration(cid, body)
                    trace.append(round(float(pen0), 9))
                    if pen0 <= PEN_TOL_M:
                        break
                    base_z += pen0 * 1.05

                # Settle, then measure the drift and the velocity over the final window.
                for _ in range(int((SETTLE_S - WINDOW_S) / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                p0, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                for _ in range(int(WINDOW_S / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                p1, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
                speed, spin = float(np.linalg.norm(lin)), float(np.linalg.norm(ang))
                drift = float(np.linalg.norm(np.array(p1) - np.array(p0)))
                pen_final, n = penetration(cid, body)
                bottom = float(p1[2]) + float(V.min(axis=0)[2])
                rec = {
                    "triangles": int(len(F)),
                    "placed_mesh": str(obj_path),
                    "planted_bottom_z": round(float(world_lo[2] + base_z), 9),
                    "initial_penetration_m": round(float(pen0), 9),
                    "contacts_at_placement": n0,
                    "placement_iterations": len(trace),
                    "penetration_trace_m": trace,
                    "settled_bottom_z": round(bottom, 9),
                    "bias_vs_floor_m": round(bottom - FLOOR_Z, 9),
                    "drift_last_window_m": round(drift, 9),
                    "settled_speed_m_s": round(speed, 9),
                    "settled_spin_rad_s": round(spin, 9),
                    "final_penetration_m": round(float(pen_final), 9),
                    "contacts": n,
                    "zero_initial_penetration": bool(pen0 <= PEN_TOL_M),
                    "on_floor": bool(abs(bottom - FLOOR_Z) <= TOL_M),
                    "at_rest": bool(n > 0 and speed < 1e-3 and spin < 1e-2
                                    and drift < 1e-3),
                    "no_final_penetration": bool(pen_final <= PEN_TOL_M),
                }
            finally:
                pb.disconnect(cid)
            rec["meets_all"] = bool(rec["zero_initial_penetration"] and rec["on_floor"]
                                    and rec["at_rest"] and rec["no_final_penetration"])
            entry["candidates"][label] = rec
            print(f"  {name:18s} {label:6s} tri={len(F):6d} "
                  f"plant_z={rec['planted_bottom_z']:.6f} "
                  f"pen0={pen0*1000:6.4f} mm ({len(trace)}i) "
                  f"bottom={bottom:.6f} bias={(bottom-FLOOR_Z)*1000:+6.3f} mm "
                  f"drift={drift*1000:7.4f} mm/s speed={speed:.2e} spin={spin:.2e} "
                  f"contacts={n:2d} {'OK' if rec['meets_all'] else 'no'}")

        # Choose only from the labels 03 permits, and only if the candidate meets everything.
        ok = [l for l in spec["allowed"]
              if entry["candidates"].get(l, {}).get("meets_all")]
        entry["chosen"] = ok[0] if ok else None
        # The visual reference is reported separately: it is not a collider, it is the
        # fidelity yardstick the proxy is compared against.
        vis = entry["candidates"].get("visual", {})
        entry["visual_reference_bias_m"] = vis.get("bias_vs_floor_m")
        entry["proxy_minus_visual_bias_m"] = (
            entry["candidates"][entry["chosen"]]["bias_vs_floor_m"]
            - vis["bias_vs_floor_m"]) if entry["chosen"] and vis else None
        results[name] = entry
        print(f"    -> chosen: {entry['chosen']}   "
              f"(visual bias {vis.get('bias_vs_floor_m')}, proxy-visual "
              f"{entry['proxy_minus_visual_bias_m']})")
    report["props"] = results

    print("\n" + "=" * 90)
    print("=== VERDICT ===")
    print(f"  static tray bias {report['tray']['bias_vs_floor_m']*1000:+.4f} mm "
          f"(bound {TOL_M*1000:.0f} mm): "
          f"{'PASS' if abs(report['tray']['bias_vs_floor_m']) <= TOL_M else 'FAIL'}")
    allok = abs(report["tray"]["bias_vs_floor_m"]) <= TOL_M
    for name, e in results.items():
        ok = e["chosen"] is not None
        allok &= ok
        print(f"  {name:18s} sealed={str(e['sealed']):5s} chosen={str(e['chosen']):6s} "
              f"{'PASS' if ok else 'FAIL'}")
    report["all_pass"] = bool(allok)
    # Disclosures that must travel with the scene.
    report["disclosures"] = [
        "Bodies are spawned with the engine-verified zero-penetration placement above; no "
        "velocity, force, or constraint is applied to any body.",
        "Box/prop deformation is not simulated: all bodies are rigid. This is a known "
        "limitation of the pipeline and is disclosed rather than modelled.",
        "The static tray collider is the exact authored mesh with "
        "GEOM_FORCE_CONCAVE_TRIMESH; without the flag pybullet hulls it and props float "
        "12.65 mm high.",
        "All mesh colliders are created with fileName= because the vertices=/indices= route "
        "produces non-colliding shapes against GEOM_PLANE and concave trimeshes in this "
        "pybullet build (API 202010061).",
        "This pybullet build exposes no collision-margin API, so no margin is set and initial "
        "penetration is controlled by placement instead.",
    ]
    out = SCENES / "proxy_acceptance_final.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    print(f"\nSTAGE 03 PROXY + STATIC SUPPORT ACCEPTANCE: {'PASS' if allok else 'FAIL'}")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
