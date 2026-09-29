"""V5.6 B: fine gap sweep -- at which gaps does each box reliably topple a following box?

The three requested gaps (0.15h, 0.25h, 0.35h) all succeeded for all three assets. Three points are
not enough to say "reliably", and the 0.02h control exposed a regime the requested gaps do not
cover: when the two boxes start closer together than roughly the striker's own thickness, the
striker contacts the target almost immediately and JAMS against it, tilting only a few degrees
before gravity returns it upright -- a lean, not a topple. Contact is made but nothing falls.

That is a real mechanical effect (the target acts as a prop that stops the striker before its centre
of mass passes over its pivot edge), and it is worth knowing because it sets a MINIMUM WORKABLE GAP
for laying out a chain. This sweep therefore scans gaps from well inside the jam regime out to well
beyond the requested range, so the report can state a working interval rather than three anecdotes:

  * same-asset pairs, gap from 0.02h to 0.70h;
  * a free-topple reference (no target at all) per asset, giving each striker's unobstructed
    behaviour and the tip-over time for comparison;
  * each gap repeated at three push strengths and two densities, so "reliable" means it holds across
    the trigger and mass assumptions rather than at one lucky setting.

Read-only apart from scratch OBJs under `outcomes/v56/mixed_box_domino/build/`.
Writes `outcomes/v56/mixed_box_domino/b_gap_sweep.json`.
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
GRAVITY = -9.81
DENSITY_PRIMARY = 200.0
FRICTION = 0.5
SETTLE_S = 1.0
SIM_S = 5.0
TOPPLE_DEG = 60.0

GAPS = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70]
OMEGAS = (2.0, 3.0, 4.5)
DENSITIES = (100.0, 200.0, 600.0)


def tilt_of(q):
    return math.degrees(math.acos(max(-1.0, min(1.0, pb.getMatrixFromQuaternion(q)[8]))))


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, GRAVITY, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[2.0, 2.0, 0.25], physicsClientId=cid)
    fl = pb.createMultiBody(0, fs, basePosition=(0, 0, -0.25), physicsClientId=cid)
    pb.changeDynamics(fl, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return cid, fl


def make(cid, spec, mass, x):
    cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=spec["obj"], flags=0,
                                 physicsClientId=cid)
    b = pb.createMultiBody(mass, cs, basePosition=(x, 0, 0.0005),
                           baseInertialFramePosition=spec["com_local_m"], physicsClientId=cid)
    pb.changeDynamics(b, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return b


def run(spec_a, spec_b, gap_frac, omega0, density, sim_s=SIM_S):
    """A and B may be different specs; gap is a fraction of the SHORTER height."""
    h_short = min(spec_a["height_m"], spec_b["height_m"])
    gap = gap_frac * h_short
    ma = density * spec_a["hull_volume_m3"]
    mb = density * spec_b["hull_volume_m3"]
    xb = spec_a["thickness_m"] / 2.0 + gap + spec_b["thickness_m"] / 2.0

    cid, floor = new_world()
    try:
        a = make(cid, spec_a, ma, 0.0)
        b = make(cid, spec_b, mb, xb)
        for _ in range(int(SETTLE_S / DT)):
            pb.stepSimulation(physicsClientId=cid)
        pre = len(pb.getContactPoints(bodyA=a, bodyB=b, physicsClientId=cid))

        pb.resetBaseVelocity(a, (omega0 * spec_a["height_m"] / 2.0, 0.0,
                                 omega0 * spec_a["thickness_m"] / 2.0),
                             (0.0, omega0, 0.0), physicsClientId=cid)

        max_a = max_b = 0.0
        touched = False
        first_touch = None
        a_top_t = b_top_t = None
        for i in range(int(sim_s / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if i % 4:
                continue
            _p, qa = pb.getBasePositionAndOrientation(a, physicsClientId=cid)
            _pb_, qb = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
            ta, tb = tilt_of(qa), tilt_of(qb)
            max_a, max_b = max(max_a, ta), max(max_b, tb)
            if a_top_t is None and ta >= TOPPLE_DEG:
                a_top_t = i * DT
            if b_top_t is None and tb >= TOPPLE_DEG:
                b_top_t = i * DT
            if not touched and pb.getContactPoints(bodyA=a, bodyB=b, physicsClientId=cid):
                touched = True
                first_touch = i * DT

        for _ in range(int(0.4 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p_a, q_a = pb.getBasePositionAndOrientation(a, physicsClientId=cid)
        p_b, q_b = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        return {
            "gap_fraction": gap_frac, "gap_m": gap, "density_kg_m3": density,
            "omega0_rad_s": omega0, "gap_over_striker_thickness": gap / spec_a["thickness_m"],
            "pre_trigger_contacts": pre,
            "striker_max_tilt_deg": round(max_a, 3),
            "striker_toppled": bool(max_a >= TOPPLE_DEG),
            "striker_topple_time_s": a_top_t,
            "contact_made": bool(touched), "first_contact_time_s": first_touch,
            "target_max_tilt_deg": round(max_b, 3),
            "target_toppled": bool(max_b >= TOPPLE_DEG),
            "target_topple_time_s": b_top_t,
            "target_translation_x_m": round(p_b[0] - xb, 6),
        }
    finally:
        pb.disconnect(cid)


def free_topple(spec, omega0, density):
    """No target: the striker's unobstructed toppling, as a reference."""
    cid, floor = new_world()
    try:
        a = make(cid, spec, density * spec["hull_volume_m3"], 0.0)
        for _ in range(int(SETTLE_S / DT)):
            pb.stepSimulation(physicsClientId=cid)
        pb.resetBaseVelocity(a, (omega0 * spec["height_m"] / 2.0, 0.0,
                                 omega0 * spec["thickness_m"] / 2.0),
                             (0.0, omega0, 0.0), physicsClientId=cid)
        max_t = 0.0
        top_t = None
        for i in range(int(SIM_S / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if i % 4:
                continue
            _p, q = pb.getBasePositionAndOrientation(a, physicsClientId=cid)
            t = tilt_of(q)
            max_t = max(max_t, t)
            if top_t is None and t >= TOPPLE_DEG:
                top_t = i * DT
        return {"omega0_rad_s": omega0, "density_kg_m3": density,
                "max_tilt_deg": round(max_t, 3),
                "topple_time_s": top_t, "toppled": bool(max_t >= TOPPLE_DEG)}
    finally:
        pb.disconnect(cid)


SPEC = {}
for aid in ASSETS:
    verts, tris, info = b_geom.upright_vertices(GSO / aid / "collision_geometry.obj")
    dst = BUILD / f"{aid}__upright_collision.obj"
    b_geom.write_obj(dst, verts, tris)
    SPEC[aid] = {
        "obj": str(dst), "hull_volume_m3": info["hull_volume_m3"],
        "thickness_m": info["thickness_m"], "width_m": info["width_m"],
        "height_m": info["height_m"], "com_local_m": [0.0, 0.0, info["height_m"] / 2.0],
        "balance_angle_deg": math.degrees(math.atan2(info["thickness_m"], info["height_m"])),
    }

report = {"note": __doc__.strip().splitlines()[0], "gaps": GAPS, "omegas": list(OMEGAS),
          "densities": list(DENSITIES), "assets": {}}

print("=" * 122)
print("V5.6 B: fine gap sweep (same-asset pairs). gap = fraction of the box height.")
for aid in ASSETS:
    spec = SPEC[aid]
    print(f"\n{'=' * 122}")
    print(f"{aid}")
    print(f"  thickness {spec['thickness_m']*1000:.2f} mm, height {spec['height_m']*1000:.2f} mm, "
          f"balance angle {spec['balance_angle_deg']:.2f} deg")

    free = [free_topple(spec, w, DENSITY_PRIMARY) for w in OMEGAS]
    print("  free topple (no target): " + "  ".join(
        f"w={f['omega0_rad_s']}: max_tilt {f['max_tilt_deg']:.1f} t_tip {f['topple_time_s']}"
        for f in free))

    grid = {}
    for gap in GAPS:
        for w in OMEGAS:
            for d in DENSITIES:
                r = run(spec, spec, gap, w, d)
                grid[(gap, w, d)] = r

    # The primary configuration is w=3.0, density=200; reliability is judged across all of them.
    print(f"\n  {'gap':>5s} {'gap_mm':>7s} {'g/t':>6s} | {'A_tip':>7s} {'A_topl':>6s} "
          f"{'contact':>7s} {'B_tip':>7s} {'B_topl':>6s} {'B_dx_mm':>8s} | "
          f"{'reliable?':>10s} {'frac_topl':>9s}")
    per_gap = []
    for gap in GAPS:
        prim = grid[(gap, 3.0, DENSITY_PRIMARY)]
        allruns = [grid[(gap, w, d)] for w in OMEGAS for d in DENSITIES]
        frac = sum(1 for r in allruns if r["target_toppled"]) / len(allruns)
        reliable = frac == 1.0
        print(f"  {gap:5.2f} {prim['gap_m']*1000:7.2f} {prim['gap_over_striker_thickness']:6.3f} | "
              f"{prim['striker_max_tilt_deg']:7.2f} {str(prim['striker_toppled']):>6s} "
              f"{str(prim['contact_made']):>7s} {prim['target_max_tilt_deg']:7.2f} "
              f"{str(prim['target_toppled']):>6s} {prim['target_translation_x_m']*1000:8.2f} | "
              f"{str(reliable):>10s} {frac*100:8.1f}%")
        per_gap.append({
            "gap_fraction": gap, "gap_m": prim["gap_m"],
            "gap_over_striker_thickness": prim["gap_over_striker_thickness"],
            "primary": prim,
            "fraction_of_all_settings_toppling": round(frac, 4),
            "reliable_across_all_settings": bool(reliable),
            "all_settings": [grid[(gap, w, d)] for w in OMEGAS for d in DENSITIES],
        })

    ok = [g["gap_fraction"] for g in per_gap if g["reliable_across_all_settings"]]
    any_ok = [g["gap_fraction"] for g in per_gap
              if g["primary"]["target_toppled"] or g["fraction_of_all_settings_toppling"] > 0]
    report["assets"][aid] = {
        "spec": spec, "free_topple": free, "per_gap": per_gap,
        "reliable_gap_range_fraction": [min(ok), max(ok)] if ok else None,
        "gaps_that_ever_toppled": [min(any_ok), max(any_ok)] if any_ok else None,
        "reliable_at_requested_gaps": [
            g["gap_fraction"] for g in per_gap
            if g["reliable_across_all_settings"] and g["gap_fraction"] in (0.15, 0.25, 0.35)],
        "jam_regime_below_gap_over_thickness": next(
            (g["gap_over_striker_thickness"] for g in per_gap
             if not g["primary"]["target_toppled"]), None),
    }
    print(f"\n  reliable across ALL {len(OMEGAS)*len(DENSITIES)} settings at gaps (fraction of h): "
          f"{report['assets'][aid]['reliable_gap_range_fraction']}")
    print(f"  topples under at least one setting at gaps: "
          f"{report['assets'][aid]['gaps_that_ever_toppled']}")
    print(f"  requested gaps (0.15/0.25/0.35) that are reliable: "
          f"{report['assets'][aid]['reliable_at_requested_gaps']}")

(OUT / "b_gap_sweep.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_gap_sweep.json'}")
