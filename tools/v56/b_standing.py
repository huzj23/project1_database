"""V5.6 B: how stable is each box really, and does it converge or keep rocking?

The 2 s standing test flagged two of the three boxes as not fully at rest:

  * Trivial Pursuit: final tilt 0.78 deg, speed 4.8e-3 m/s, spin 3.5e-2 rad/s
  * Ouija:           final tilt 2.29 deg, MAX tilt 3.51 deg, speed 1.5e-2 m/s, spin 7.5e-2 rad/s

A single 2 s snapshot cannot distinguish "still settling and will be fine" from "rocks forever" or
"slowly falls over", and that distinction is exactly what "will not stand still is unusable" turns
on. It also cannot distinguish a genuine property of the warped scanned base from an artefact of
the 0.5 mm drop used to spawn the body.

This measures, for each asset:
  * a LONG run (20 s) with a WINDOWED tilt envelope, so convergence (envelope shrinking) is visible
    rather than inferred from one number;
  * two spawn clearances (0.5 mm and 0.05 mm), because a drop impact is not inherent geometry;
  * several yaw orientations, because a warped base makes stability direction-dependent;
  * the base flatness that should explain the differences, measured from the hull itself.

Read-only apart from scratch OBJs under `outcomes/v56/mixed_box_domino/build/`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pybullet as pb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b_geom  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v56/mixed_box_domino"
BUILD = OUT / "build"
BUILD.mkdir(parents=True, exist_ok=True)

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]
DT = 1.0 / 240.0
G = 9.81
DENSITY = 200.0
FRICTION = 0.5


def tilt_of(q):
    return math.degrees(math.acos(max(-1.0, min(1.0, pb.getMatrixFromQuaternion(q)[8]))))


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -G, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[1.5, 1.5, 0.25], physicsClientId=cid)
    fl = pb.createMultiBody(0, fs, basePosition=(0, 0, -0.25), physicsClientId=cid)
    pb.changeDynamics(fl, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return cid, fl


def standing(spec, clearance, yaw_deg=0.0, sim_s=20.0, window_s=1.0):
    """Long standing run with a windowed tilt envelope and velocity trace."""
    cid, floor = new_world()
    try:
        mass = DENSITY * spec["hull_volume_m3"]
        cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=spec["obj"], flags=0,
                                     physicsClientId=cid)
        q0 = pb.getQuaternionFromEuler([0.0, 0.0, math.radians(yaw_deg)], physicsClientId=cid)
        b = pb.createMultiBody(mass, cs, basePosition=(0, 0, clearance), baseOrientation=q0,
                               baseInertialFramePosition=spec["com_local_m"],
                               physicsClientId=cid)
        pb.changeDynamics(b, -1, lateralFriction=FRICTION, restitution=0.0,
                          physicsClientId=cid)

        per_step = int(window_s / DT)
        envelopes = []
        cur_max = 0.0
        max_xy = 0.0
        trace = []
        for w in range(int(sim_s / window_s)):
            for i in range(per_step):
                pb.stepSimulation(physicsClientId=cid)
                p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
                t = tilt_of(q)
                cur_max = max(cur_max, t)
                max_xy = max(max_xy, math.sqrt(p[0] ** 2 + p[1] ** 2))
                if i % 40 == 0:
                    trace.append([round((w * per_step + i) * DT, 3), round(t, 4),
                                  round(math.sqrt(p[0] ** 2 + p[1] ** 2), 6)])
            envelopes.append(round(cur_max, 5))
            cur_max = 0.0

        p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        lin, ang = pb.getBaseVelocity(b, physicsClientId=cid)
        contacts = len(pb.getContactPoints(bodyA=b, bodyB=floor, physicsClientId=cid))
        speed = math.sqrt(sum(v * v for v in lin))
        spin = math.sqrt(sum(v * v for v in ang))
        # Convergence: the envelope over the last 5 windows vs the first 5.
        early = max(envelopes[:5]) if len(envelopes) >= 5 else max(envelopes)
        late = max(envelopes[-5:]) if len(envelopes) >= 5 else min(envelopes)
        return {
            "clearance_m": clearance, "yaw_deg": yaw_deg,
            "envelope_max_tilt_per_window_deg": envelopes,
            "final_tilt_deg": round(tilt_of(q), 5),
            "max_tilt_deg": round(max(envelopes), 5),
            "final_xy_drift_m": round(math.sqrt(p[0] ** 2 + p[1] ** 2), 6),
            "max_xy_drift_m": round(max_xy, 6),
            "final_speed_m_s": round(speed, 6), "final_spin_rad_s": round(spin, 6),
            "floor_contacts": contacts,
            "envelope_early_max": round(early, 5), "envelope_late_max": round(late, 5),
            "settles": bool(late < 1e-3),
            "still_upright": bool(tilt_of(q) < 15.0),
            "at_rest": bool(speed < 1e-3 and spin < 1e-3 and contacts > 0),
            "trace": trace,
        }
    finally:
        pb.disconnect(cid)


SPEC = {}
for aid in ASSETS:
    src = GSO / aid / "collision_geometry.obj"
    verts, tris, info = b_geom.upright_vertices(src)
    dst = BUILD / f"{aid}__upright_collision.obj"
    b_geom.write_obj(dst, verts, tris)
    # Base flatness of the UPRIGHT PROXY: how much of the nominal footprint actually touches down,
    # and how far the lowest vertices spread in z (a spread base must rock).
    z0 = 0.0
    zb = [p[2] for p in verts]
    near = [p for p in verts if p[2] - min(zb) < 0.001]
    SPEC[aid] = {
        "obj": str(dst), "hull_volume_m3": info["hull_volume_m3"],
        "thickness_m": info["thickness_m"], "width_m": info["width_m"],
        "height_m": info["height_m"], "com_local_m": [0.0, 0.0, info["height_m"] / 2.0],
        "balance_angle_deg": math.degrees(math.atan2(info["thickness_m"], info["height_m"])),
        "base_vertices_within_1mm": len(near),
        "base_z_spread_mm": (max(p[2] for p in near) - min(p[2] for p in near)) * 1000
        if near else None,
        "base_footprint_x_mm": (max(p[0] for p in near) - min(p[0] for p in near)) * 1000
        if near else None,
        "nominal_x_mm": info["thickness_m"] * 1000,
        "base_footprint_frac_of_nominal_x": (
            (max(p[0] for p in near) - min(p[0] for p in near)) / info["thickness_m"]
            if near and info["thickness_m"] > 0 else None),
    }

report = {"note": __doc__.strip().splitlines()[0], "spec": SPEC, "runs": []}

print("=" * 116)
print("V5.6 B: standing-stability convergence (20 s, windowed envelope)")
print(f"\n  {'asset':44s} {'clear':>6s} {'yaw':>5s} {'maxTilt':>8s} {'finTilt':>8s} "
      f"{'early5':>8s} {'late5':>8s} {'settles':>8s} {'upright':>8s} {'atrest':>7s}")
for aid in ASSETS:
    for clearance in (0.0005, 0.00005):
        for yaw in (0.0, 90.0):
            r = standing(SPEC[aid], clearance, yaw)
            r["asset"] = aid
            report["runs"].append(r)
            print(f"  {aid:44s} {clearance*1000:5.2f}m {yaw:5.0f} {r['max_tilt_deg']:8.4f} "
                  f"{r['final_tilt_deg']:8.4f} {r['envelope_early_max']:8.4f} "
                  f"{r['envelope_late_max']:8.4f} {str(r['settles']):>8s} "
                  f"{str(r['still_upright']):>8s} {str(r['at_rest']):>7s}")

print("\n=== yaw dependence (a warped base is direction-dependent), clearance 0.05 mm ===")
print(f"  {'asset':44s} {'yaw':>5s} {'maxTilt':>8s} {'finTilt':>8s} {'late5':>8s} {'upright':>8s}")
for aid in ASSETS:
    for yaw in (0.0, 45.0, 90.0, 135.0, 180.0):
        r = standing(SPEC[aid], 0.00005, yaw, sim_s=12.0)
        r["asset"] = aid
        report["runs"].append(r)
        print(f"  {aid:44s} {yaw:5.0f} {r['max_tilt_deg']:8.4f} {r['final_tilt_deg']:8.4f} "
              f"{r['envelope_late_max']:8.4f} {str(r['still_upright']):>8s}")

print("\n=== base flatness of the upright proxy (explains the differences) ===")
print(f"  {'asset':44s} {'n<1mm':>6s} {'zspread_mm':>11s} {'base_x_mm':>10s} {'nom_x_mm':>9s} "
      f"{'frac':>6s} {'balance_deg':>12s}")
for aid, s in SPEC.items():
    print(f"  {aid:44s} {s['base_vertices_within_1mm']:6d} {s['base_z_spread_mm']:11.4f} "
          f"{s['base_footprint_x_mm']:10.4f} {s['nominal_x_mm']:9.4f} "
          f"{s['base_footprint_frac_of_nominal_x']:6.4f} {s['balance_angle_deg']:12.4f}")

print("\n=== tilt trace, clearance 0.5 mm, yaw 0 (t, tilt deg, xy drift m) ===")
for r in report["runs"]:
    if r["clearance_m"] == 0.0005 and r["yaw_deg"] == 0.0:
        print(f"\n  {r['asset']}")
        for row in r["trace"][:40]:
            print(f"    t={row[0]:7.3f}  tilt={row[1]:8.4f}  drift={row[2]:.6f}")

(OUT / "b_standing.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_standing.json'}")
