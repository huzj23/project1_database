"""V5.6 B: practical mixed-asset chains, and a focused look at the one marginal failure.

Two things the per-asset sweep does not cover, both needed for a usable conclusion:

1. MIXED CHAINS. The task is a mixed-box domino chain, so the question is not only "can A topple a
   box of its own kind" but "can these three knock each other over in a chain". This runs 3-box
   chains in several asset orders at the requested gaps and reports how far the chain propagated,
   which is the operationally meaningful measure.

2. THE ONE MARGINAL FAILURE. At gap 0.15h with a weak push (omega0=2.0 rad/s) the Cranium and
   Trivial Pursuit strikers toppled and CONTACTED the target, yet the target only tilted ~2 deg and
   stayed up. "A toppled but B did not" needs a mechanism, not a shrug. The candidate explanation is
   TIMING: at a small gap the striker strikes the target early in its fall, while its angular speed
   is still low, so less momentum is transferred; at a larger gap the striker accelerates under
   gravity before contact. That predicts the striker's angular speed AT FIRST CONTACT should be
   lower for the small-gap failures than for the successes. This measures that speed directly, so
   the explanation is checked rather than asserted.

Read-only apart from scratch OBJs under `outcomes/v56/mixed_box_domino/build/`.
Writes `outcomes/v56/mixed_box_domino/b_chain.json`.
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

CRAN = "Hasbro_Cranium_Performance_and_Acting_Game"
TRIV = "Hasbro_Trivial_Pursuit_Family_Edition_Game"
OUIJ = "Supernatural_Ouija_Board_Game"
ASSETS = [CRAN, TRIV, OUIJ]

DT = 1.0 / 240.0
TOPPLE_DEG = 60.0
FRICTION = 0.5
SETTLE_S = 1.0


def tilt_of(q):
    return math.degrees(math.acos(max(-1.0, min(1.0, pb.getMatrixFromQuaternion(q)[8]))))


def build_spec(aid):
    verts, tris, info = b_geom.upright_vertices(GSO / aid / "collision_geometry.obj")
    dst = BUILD / f"{aid}__upright_collision.obj"
    b_geom.write_obj(dst, verts, tris)
    return {"id": aid, "obj": str(dst), "hull_volume_m3": info["hull_volume_m3"],
            "thickness_m": info["thickness_m"], "width_m": info["width_m"],
            "height_m": info["height_m"], "com_local_m": [0.0, 0.0, info["height_m"] / 2.0]}


SPEC = {a: build_spec(a) for a in ASSETS}


def new_world(extent=3.0):
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[extent, extent, 0.25],
                                 physicsClientId=cid)
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


# ---------------------------------------------------------------------------------------------
# 1. mixed 3-box chains
# ---------------------------------------------------------------------------------------------

def chain(order, gap_frac, omega0=3.0, density=200.0, sim_s=9.0):
    """A chain of |order| boxes, all gaps equal to gap_frac x the SHORTER height of each pair."""
    cid, floor = new_world()
    try:
        xs = [0.0]
        gap_details = []
        for i, aid in enumerate(order):
            if i == 0:
                continue
            prev = SPEC[order[i - 1]]
            cur = SPEC[aid]
            h_short = min(prev["height_m"], cur["height_m"])
            gap = gap_frac * h_short
            x = xs[-1] + prev["thickness_m"] / 2.0 + gap + cur["thickness_m"] / 2.0
            xs.append(x)
            gap_details.append({"pair": f"{order[i-1]}->{aid}", "gap_m": gap})

        bodies = [make(cid, SPEC[aid], density * SPEC[aid]["hull_volume_m3"], xs[i])
                  for i, aid in enumerate(order)]
        for _ in range(int(SETTLE_S / DT)):
            pb.stepSimulation(physicsClientId=cid)

        first = SPEC[order[0]]
        pb.resetBaseVelocity(bodies[0],
                             (omega0 * first["height_m"] / 2.0, 0.0,
                              omega0 * first["thickness_m"] / 2.0),
                             (0.0, omega0, 0.0), physicsClientId=cid)

        max_tilts = [0.0] * len(order)
        contacts_seen = [False] * (len(order) - 1)
        for i in range(int(sim_s / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if i % 4:
                continue
            for j, b in enumerate(bodies):
                _p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
                max_tilts[j] = max(max_tilts[j], tilt_of(q))
            for j in range(len(order) - 1):
                if not contacts_seen[j] and pb.getContactPoints(
                        bodyA=bodies[j], bodyB=bodies[j + 1], physicsClientId=cid):
                    contacts_seen[j] = True

        finals = []
        for b in bodies:
            _p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
            finals.append(round(tilt_of(q), 3))
        toppled = [t >= TOPPLE_DEG for t in finals]
        # A chain has propagated through link j if box j+1 ended up toppled.
        propagated = sum(1 for t in toppled[1:] if t)
        return {
            "order": order, "gap_fraction": gap_frac, "omega0_rad_s": omega0,
            "density_kg_m3": density, "positions_x_m": [round(v, 6) for v in xs],
            "gap_details": gap_details,
            "max_tilt_deg": [round(t, 3) for t in max_tilts],
            "final_tilt_deg": finals,
            "toppled": toppled,
            "links_that_made_contact": contacts_seen,
            "boxes_toppled": sum(1 for t in toppled if t),
            "boxes_total": len(order),
            "chain_propagated_fully": bool(all(toppled)),
        }
    finally:
        pb.disconnect(cid)


# ---------------------------------------------------------------------------------------------
# 2. striker angular speed AT FIRST CONTACT, for small-gap failures vs successes
# ---------------------------------------------------------------------------------------------

def contact_speed(striker, target, gap_frac, omega0, density=200.0):
    cid, floor = new_world()
    try:
        sa, sb = SPEC[striker], SPEC[target]
        h_short = min(sa["height_m"], sb["height_m"])
        gap = gap_frac * h_short
        xb = sa["thickness_m"] / 2.0 + gap + sb["thickness_m"] / 2.0
        a = make(cid, sa, density * sa["hull_volume_m3"], 0.0)
        b = make(cid, sb, density * sb["hull_volume_m3"], xb)
        for _ in range(int(SETTLE_S / DT)):
            pb.stepSimulation(physicsClientId=cid)
        pb.resetBaseVelocity(a, (omega0 * sa["height_m"] / 2.0, 0.0,
                                 omega0 * sa["thickness_m"] / 2.0),
                             (0.0, omega0, 0.0), physicsClientId=cid)

        # Trigger strength is also recorded so the comparison is between like quantities.
        _p, _q = pb.getBasePositionAndOrientation(a, physicsClientId=cid)
        _l, w_trig = pb.getBaseVelocity(a, physicsClientId=cid)

        first = None
        speed_at_first = None
        omega_at_first = None
        tilt_at_first = None
        max_b = 0.0
        for i in range(int(5.0 / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if first is None and pb.getContactPoints(bodyA=a, bodyB=b, physicsClientId=cid):
                first = i * DT
                _pa, qa = pb.getBasePositionAndOrientation(a, physicsClientId=cid)
                lin, ang = pb.getBaseVelocity(a, physicsClientId=cid)
                speed_at_first = math.sqrt(sum(v * v for v in lin))
                omega_at_first = abs(ang[1])
                tilt_at_first = tilt_of(qa)
            _p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
            max_b = max(max_b, tilt_of(q))
        return {
            "striker": striker, "target": target, "gap_fraction": gap_frac,
            "gap_m": round(gap, 6), "omega0_rad_s": omega0,
            "omega_at_trigger_rad_s": round(abs(w_trig[1]), 4),
            "first_contact_time_s": first,
            "striker_tilt_at_first_contact_deg": (round(tilt_at_first, 3)
                                                  if tilt_at_first is not None else None),
            "striker_omega_at_first_contact_rad_s": (round(omega_at_first, 4)
                                                     if omega_at_first is not None else None),
            "striker_speed_at_first_contact_m_s": (round(speed_at_first, 4)
                                                   if speed_at_first is not None else None),
            "target_max_tilt_deg": round(max_b, 3),
            "target_toppled": bool(max_b >= TOPPLE_DEG),
        }
    finally:
        pb.disconnect(cid)


report = {"note": __doc__.strip().splitlines()[0], "chains": [], "contact_speed": []}

print("=" * 116)
print("1. MIXED 3-BOX CHAINS (gap as a fraction of the shorter height of each pair)")
orders = [
    [CRAN, TRIV, OUIJ],
    [OUIJ, TRIV, CRAN],
    [TRIV, OUIJ, CRAN],
    [CRAN, OUIJ, TRIV],
]
for frac in (0.15, 0.25, 0.35):
    print(f"\n  --- gap {frac:.2f}h ---")
    for order in orders:
        r = chain(order, frac)
        report["chains"].append(r)
        names = " -> ".join(a.split("_")[0][:6] for a in order)
        print(f"    {names:26s} toppled {r['boxes_toppled']}/{r['boxes_total']} "
              f"full={str(r['chain_propagated_fully']):>5s}  "
              f"final tilts {r['final_tilt_deg']}  contacts {r['links_that_made_contact']}")

print("\n" + "=" * 116)
print("2. STRIKER ANGULAR SPEED AT FIRST CONTACT: small-gap failure vs larger-gap success")
print(f"  {'striker':10s} {'gap':>5s} {'w0':>5s} {'t_contact':>10s} {'tilt@contact':>13s} "
      f"{'omega@contact':>14s} {'B_tip':>7s} {'B_topl':>6s}")
SHORT = {CRAN: "Cranium", TRIV: "Trivial", OUIJ: "Ouija"}
cases = []
for striker, target in ((CRAN, CRAN), (TRIV, TRIV), (OUIJ, OUIJ)):
    for frac in (0.02, 0.08, 0.15, 0.25, 0.35):
        for w in (2.0, 3.0):
            cases.append((striker, target, frac, w))
for striker, target, frac, w in cases:
    r = contact_speed(striker, target, frac, w)
    report["contact_speed"].append(r)
    print(f"  {SHORT[striker]:10s} {frac:5.2f} {w:5.1f} {str(r['first_contact_time_s']):>10s} "
          f"{str(r['striker_tilt_at_first_contact_deg']):>13s} "
          f"{str(r['striker_omega_at_first_contact_rad_s']):>14s} "
          f"{r['target_max_tilt_deg']:7.2f} {str(r['target_toppled']):>6s}")

# Compare the mean contact speed for failures vs successes, to test the timing explanation.
fails = [r["striker_omega_at_first_contact_rad_s"] for r in report["contact_speed"]
         if not r["target_toppled"] and r["striker_omega_at_first_contact_rad_s"] is not None]
succ = [r["striker_omega_at_first_contact_rad_s"] for r in report["contact_speed"]
        if r["target_toppled"] and r["striker_omega_at_first_contact_rad_s"] is not None]
summary = {
    "failures_n": len(fails), "successes_n": len(succ),
    "mean_omega_at_contact_when_failed_rad_s": round(sum(fails) / len(fails), 4) if fails else None,
    "mean_omega_at_contact_when_succeeded_rad_s": (round(sum(succ) / len(succ), 4)
                                                   if succ else None),
    "min_omega_at_contact_when_succeeded_rad_s": round(min(succ), 4) if succ else None,
    "max_omega_at_contact_when_failed_rad_s": round(max(fails), 4) if fails else None,
}
summary["timing_explanation_supported"] = bool(
    fails and succ and max(fails) < min(succ) + 1e-9)
report["contact_speed_summary"] = summary
print(f"\n  failures  n={summary['failures_n']:2d} mean omega@contact "
      f"{summary['mean_omega_at_contact_when_failed_rad_s']} rad/s "
      f"(max {summary['max_omega_at_contact_when_failed_rad_s']})")
print(f"  successes n={summary['successes_n']:2d} mean omega@contact "
      f"{summary['mean_omega_at_contact_when_succeeded_rad_s']} rad/s "
      f"(min {summary['min_omega_at_contact_when_succeeded_rad_s']})")
print(f"  every failure had a slower strike than every success: "
      f"{summary['timing_explanation_supported']}")

(OUT / "b_chain.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_chain.json'}")
