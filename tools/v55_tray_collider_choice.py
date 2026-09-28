"""V5.5 stage 03 section 5: decide the static tray collider, one collider per clean world.

The previous attempt created three tray colliders in ONE world and the second and third then
reported no probe contacts at all -- an artifact of the shared world, not a property of the
colliders, since the same V-HACD compound supported probes correctly in its own world
earlier. Every candidate is therefore measured in a FRESH world here, so no result can be
contaminated by another collider.

Candidates, all measured against the tray floor z = 0.510600 (raycast) and rim z = 0.522260:
  A  tray mesh, no flags               -- if pybullet hulls it, this rests at the rim
  B  tray mesh + GEOM_FORCE_CONCAVE    -- the exact authored geometry, if it works
  C  V-HACD compound, 71 convex parts  -- an approximation with a measured bias
  D  a box "floor plate" + thin walls  -- a deliberately simple, verifiable stand-in

Acceptance is 03's own contact-face bound: min(2 mm, thinnest*5%), which the 22.26 mm tray caps
at 2 mm. A candidate passes if a settled probe's bottom is within 2 mm of the true floor.
Placement then solves each prop's spawn height against pybullet's narrowphase until initial
penetration is <= 0.1 mm, so no body starts the solve overlapping the environment. That is a
geometric placement correction verified by the engine: no force, velocity or constraint is ever
applied, and each body settles under gravity alone.
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
FLOOR_Z = 0.510600
RIM_Z = 0.522260
TOL_M = 0.002
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


def add_tray_bodies(cid, spec) -> list:
    """spec = {"kind": "mesh"|"concave"|"parts"|"boxes", ...} -> list of static body ids."""
    if spec["kind"] in ("mesh", "concave"):
        flags = pb.GEOM_FORCE_CONCAVE_TRIMESH if spec["kind"] == "concave" else 0
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(spec["uri"]), flags=flags,
                                    physicsClientId=cid)
        return [pb.createMultiBody(0, s, basePosition=(0, 0, 0), physicsClientId=cid)]
    if spec["kind"] == "parts":
        out = []
        for p in spec["uris"]:
            s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(p),
                                        physicsClientId=cid)
            out.append(pb.createMultiBody(0, s, basePosition=(0, 0, 0),
                                          physicsClientId=cid))
        return out
    if spec["kind"] == "boxes":
        out = []
        for (c, h) in spec["boxes"]:
            s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=list(h),
                                        physicsClientId=cid)
            out.append(pb.createMultiBody(0, s, basePosition=list(c),
                                          physicsClientId=cid))
        return out
    raise ValueError(spec["kind"])


def probe_support(spec, lo, hi, label, n=3):
    cid = new_world()
    try:
        bodies = add_tray_bodies(cid, spec)
        half = 0.008
        bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3,
                                     physicsClientId=cid)
        xs = np.linspace(lo[0] + 0.3 * (hi[0] - lo[0]), hi[0] - 0.3 * (hi[0] - lo[0]), n)
        ys = np.linspace(lo[1] + 0.3 * (hi[1] - lo[1]), hi[1] - 0.3 * (hi[1] - lo[1]), n)
        bottoms, spans = [], []
        for x in xs:
            for y in ys:
                pr = pb.createMultiBody(0.05, bs,
                                        basePosition=(float(x), float(y), hi[2] + 0.03),
                                        physicsClientId=cid)
                for _ in range(int(2.0 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                p, _ = pb.getBasePositionAndOrientation(pr, physicsClientId=cid)
                cnt = sum(len(pb.getContactPoints(bodyA=pr, bodyB=b,
                                                  physicsClientId=cid)) for b in bodies)
                if cnt > 0:
                    bottoms.append(float(p[2] - half))
                spans.append({"xy": [round(float(x), 5), round(float(y), 5)],
                              "bottom_z": round(float(p[2] - half), 6), "contacts": cnt})
                pb.removeBody(pr, physicsClientId=cid)
        med = float(np.median(bottoms)) if bottoms else None
        ok = med is not None and abs(med - FLOOR_Z) <= TOL_M
        msg = (f"support={med:.6f} bias={(med-FLOOR_Z)*1000:+8.4f} mm "
               f"({len(bottoms)}/{n*n} probes)") if med is not None else \
              f"NO SUPPORT ({n*n} probes, 0 contacts)"
        print(f"  {label:38s} {msg}  {'PASS' if ok else 'fail'}")
        return {"label": label, "support_z_median": med, "bias_m":
                (med - FLOOR_Z) if med is not None else None,
                "probes_with_support": len(bottoms), "probes_total": n * n,
                "within_tolerance": bool(ok), "probe_detail": spans}
    finally:
        pb.disconnect(cid)


def main() -> int:
    report: dict = {"floor_z": FLOOR_Z, "rim_z": RIM_Z, "tolerance_m": TOL_M}
    shell = RUNTIME / "static_Vassoio.obj"
    sv, sf = load_obj(shell)
    slo, shi = sv.min(axis=0), sv.max(axis=0)
    parts = sorted(STATIC_PROXIES.glob("part*.obj"))
    vv = np.vstack([load_obj(p)[0] for p in parts])

    # A simple box floor + thin rim walls, built from the measured tray extents. The floor
    # plate's TOP is placed exactly at FLOOR_Z, which makes this candidate unconditional on
    # decomposition quality.
    pad = 0.0
    boxes = [
        # floor plate: 2 mm thick slab whose top sits at the measured floor
        ([0.5 * (slo[0] + shi[0]), 0.5 * (slo[1] + shi[1]), FLOOR_Z - 0.001],
         [0.5 * (shi[0] - slo[0]) + pad, 0.5 * (shi[1] - slo[1]) + pad, 0.001]),
    ]
    # rim walls, 3 mm thick, reaching from below the floor up to the rim height
    rim_h = (RIM_Z - FLOOR_Z + 0.002) / 2
    rim_cz = (RIM_Z + FLOOR_Z - 0.002) / 2
    t = 0.0015
    for x, sx in ((slo[0], -1), (shi[0], +1)):
        boxes.append(([x + sx * t, 0.5 * (slo[1] + shi[1]), rim_cz],
                      [t, 0.5 * (shi[1] - slo[1]), rim_h]))
    for y, sy in ((slo[1], -1), (shi[1], +1)):
        boxes.append(([0.5 * (slo[0] + shi[0]), y + sy * t, rim_cz],
                      [0.5 * (shi[0] - slo[0]), t, rim_h]))

    candidates = [
        ("A_mesh_no_flags", {"kind": "mesh", "uri": shell}),
        ("B_mesh_concave", {"kind": "concave", "uri": shell}),
        ("C_vhacd_compound", {"kind": "parts", "uris": parts}),
        ("D_box_floor_and_rim", {"kind": "boxes", "boxes": boxes}),
    ]

    print("=" * 78)
    print("=== static tray collider candidates, each in its own FRESH world ===")
    results = []
    for label, spec in candidates:
        r = probe_support(spec, slo, shi, label)
        r["kind"] = spec["kind"]
        if spec["kind"] == "parts":
            r["parts"] = len(parts)
        if spec["kind"] == "boxes":
            r["boxes"] = len(boxes)
        results.append(r)
    report["candidates"] = results

    passing = [r for r in results if r["within_tolerance"]]
    passing.sort(key=lambda r: abs(r["bias_m"]))
    report["passing"] = [r["label"] for r in passing]
    print(f"\n  passing within {TOL_M*1000:.0f} mm: {[r['label'] for r in passing]}")

    # Preference: exact authored geometry first, then the simplest robust stand-in, then the
    # decomposition. All of these are inside the same tolerance, so the tie-break is fidelity
    # and cost rather than a fabricated ranking.
    pref = ["B_mesh_concave", "A_mesh_no_flags", "D_box_floor_and_rim", "C_vhacd_compound"]
    chosen = next((p for p in pref if p in report["passing"]), None)
    report["chosen"] = chosen
    if chosen:
        rec = next(r for r in results if r["label"] == chosen)
        report["chosen_bias_m"] = rec["bias_m"]
        print(f"  CHOSEN: {chosen} (bias {rec['bias_m']*1000:+.4f} mm)")

    # ---- zero-penetration placement against the chosen collider --------------------
    if chosen:
        spec = dict(candidates[[c[0] for c in candidates].index(chosen)][1])
        print("\n=== prop placement: solve spawn height for ZERO initial penetration ===")
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
                cid = new_world()
                try:
                    add_tray_bodies(cid, spec)
                    cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                                 indices=F.ravel().tolist(),
                                                 physicsClientId=cid)
                    base_z = FLOOR_Z - world_lo[2]
                    trace, pen0 = [], None
                    for _ in range(40):
                        body = pb.createMultiBody(
                            PROP_MASS[name], cs,
                            basePosition=(restore + np.array([0.0, 0.0, base_z])).tolist(),
                            physicsClientId=cid)
                        pb.changeDynamics(body, -1, lateralFriction=0.6, restitution=0.0,
                                          physicsClientId=cid)
                        pb.performCollisionDetection(physicsClientId=cid)
                        cps = pb.getContactPoints(bodyA=body, physicsClientId=cid)
                        pen0 = max((-float(c[8]) for c in cps), default=0.0)
                        trace.append(round(float(pen0), 9))
                        if pen0 <= PEN_TOL_M:
                            break
                        pb.removeBody(body, physicsClientId=cid)
                        base_z += pen0 * 1.05
                    # Settle under gravity alone.
                    for _ in range(int(1.2 / DT)):
                        pb.stepSimulation(physicsClientId=cid)
                    pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                    lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
                    speed, spin = float(np.linalg.norm(lin)), float(np.linalg.norm(ang))
                    n = len(pb.getContactPoints(bodyA=body, physicsClientId=cid))
                    rec = {
                        "triangles": int(len(F)),
                        "planted_bottom_z": round(float(world_lo[2] + base_z), 9),
                        "initial_penetration_m": round(float(pen0), 9),
                        "placement_iterations": len(trace),
                        "penetration_trace_m": trace,
                        "settled_origin_z": round(float(pos[2]), 9),
                        "settled_speed_m_s": round(speed, 9),
                        "settled_spin_rad_s": round(spin, 9),
                        "contacts": n,
                        "at_rest": bool(n > 0 and speed < 1e-3 and spin < 1e-3),
                        "zero_initial_penetration": bool(pen0 <= PEN_TOL_M),
                    }
                finally:
                    pb.disconnect(cid)
                entry[label] = rec
                print(f"  {name:18s} {label:6s} planted_z={rec['planted_bottom_z']:.6f} "
                      f"init_pen={pen0*1000:7.4f} mm ({len(trace)} iter) "
                      f"settled_z={rec['settled_origin_z']:.6f} contacts={n:3d} "
                      f"speed={speed:.1e} at_rest={rec['at_rest']}")
            placement[name] = entry
        report["placement"] = placement

    print("\n" + "=" * 78)
    print("=== VERDICT ===")
    for r in results:
        b = f"{r['bias_m']*1000:+.4f} mm" if r["bias_m"] is not None else "no support"
        print(f"  {r['label']:24s} {b:>14s}  "
              f"{'PASS' if r['within_tolerance'] else 'FAIL'}")
    print(f"  chosen: {chosen}")
    allok = True
    for name, entry in report.get("placement", {}).items():
        for label, r in entry.items():
            allok &= r["zero_initial_penetration"] and r["at_rest"]
            print(f"  {name:18s} {label:6s} init_pen={r['initial_penetration_m']*1000:7.4f} mm "
                  f"at_rest={r['at_rest']}")
    ok = bool(chosen) and allok
    out = SCENES / "tray_collider_final.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    print(f"\nSTATIC SUPPORT + ZERO-PENETRATION PLACEMENT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
