"""V5.6 B diagnostic: why the striker did not topple, and how big the collision hull really is.

Two anomalies came out of the first physics run and neither may be guessed at:

  1. `getAABB` on the upright proxy was LARGER than the measured mesh by up to 18 mm. Either the
     rewrite is wrong, or pybullet's convex hull carries a margin. This measures the EFFECTIVE
     collision surface with raycasts from six directions, with gravity off and the body floating,
     so the answer does not depend on how the body settles or tilts.
  2. The striker did not topple even though the trigger energy was 4x the analytic tipping energy.
     A tilt trajectory sampled every 20 ms shows whether the rotation is killed immediately (which
     would point at initial penetration or a solver artefact) or never started (a trigger bug).

Read-only apart from a scratch OBJ under `outcomes/v56/mixed_box_domino/build/`.
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


def quat_to_matrix(q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def tilt_deg(q):
    return math.degrees(math.acos(max(-1.0, min(1.0, quat_to_matrix(q)[2][2]))))


report = {"note": __doc__.strip().splitlines()[0], "assets": {}}

for aid in ASSETS:
    src = GSO / aid / "collision_geometry.obj"
    verts, tris, info = b_geom.upright_vertices(src)
    obj = BUILD / f"{aid}__upright_collision.obj"
    b_geom.write_obj(obj, verts, tris)
    t, w, h = info["thickness_m"], info["width_m"], info["height_m"]

    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, 0, physicsClientId=cid)          # float the body: pure geometry probe
    col = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj), flags=0, physicsClientId=cid)
    body = pb.createMultiBody(0.5, col, basePosition=(0, 0, 0.5), physicsClientId=cid)
    pb.performCollisionDetection(physicsClientId=cid)

    def surface(axis, sign):
        """First hit when a ray comes in along `axis` from `sign` side, expressed in local coords."""
        far, near = 2.0, -2.0
        start = [0.0, 0.0, 0.5]
        end = [0.0, 0.0, 0.5]
        start[axis] = 0.5 + far * sign
        end[axis] = 0.5 + near * sign
        hit = pb.rayTest(start, end, physicsClientId=cid)[0]
        if hit[0] < 0:
            return None
        return hit[3][axis] - 0.5

    eff = {}
    for axis, name in ((0, "x_thickness"), (1, "y_width"), (2, "z_height")):
        minus = surface(axis, -1.0)
        plus = surface(axis, +1.0)
        eff[name] = {
            "minus_m": minus, "plus_m": plus,
            "extent_m": (plus - minus) if (minus is not None and plus is not None) else None,
        }

    # The AABB at this same pose, for comparison with the raycast measurement.
    lo, hi = pb.getAABB(body, physicsClientId=cid)

    rec = {
        "measured_mesh_dims_t_w_h_m": [t, w, h],
        "raycast_effective_extents_m": [eff["x_thickness"]["extent_m"],
                                        eff["y_width"]["extent_m"],
                                        eff["z_height"]["extent_m"]],
        "raycast_detail": eff,
        "getAABB_dims_m": [hi[i] - lo[i] for i in range(3)],
        "getAABB_min_m": list(lo), "getAABB_max_m": list(hi),
    }
    # Is the growth a UNIFORM margin (2*margin per axis) or something shape-dependent?
    growth = []
    for i, name in enumerate(("x_thickness", "y_width", "z_height")):
        e = eff[name]["extent_m"]
        growth.append(None if e is None else e - [t, w, h][i])
    rec["extent_growth_m"] = growth
    margins = [g / 2.0 for g in growth if g is not None]
    rec["implied_margin_per_side_m"] = margins
    rec["margin_uniform"] = bool(margins and (max(margins) - min(margins)) < 2e-4)
    pb.disconnect(cid)
    report["assets"][aid] = rec

    print("=" * 110)
    print(f"{aid}")
    print(f"  measured mesh t/w/h       {t:.6f}  {w:.6f}  {h:.6f} m")
    print(f"  raycast effective extents {rec['raycast_effective_extents_m']}")
    print(f"  getAABB dims              {[round(v, 6) for v in rec['getAABB_dims_m']]}")
    print(f"  growth vs mesh            {[None if g is None else round(g, 6) for g in growth]}")
    print(f"  implied margin per side   {[round(m, 6) for m in margins]}  "
          f"uniform={rec['margin_uniform']}")

# ---------------------------------------------------------------------------------------------
# tilt trajectory: is the push being killed, or never applied?
# ---------------------------------------------------------------------------------------------
print("\n" + "=" * 110)
print("=== TILT TRAJECTORY after the trigger (Cranium, gap open, floor friction ON) ===")

aid = ASSETS[0]
src = GSO / aid / "collision_geometry.obj"
verts, tris, info = b_geom.upright_vertices(src)
obj = BUILD / f"{aid}__upright_collision.obj"
t, w, h = info["thickness_m"], info["width_m"], info["height_m"]
mass = 200.0 * info["hull_volume_m3"]

traj = {}
for omega0 in (0.0, 3.0, 4.5):
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[1.5, 1.5, 0.25], physicsClientId=cid)
    floor = pb.createMultiBody(0, fs, basePosition=(0, 0, -0.25), physicsClientId=cid)
    pb.changeDynamics(floor, -1, lateralFriction=0.5, restitution=0.0, physicsClientId=cid)
    col = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj), flags=0, physicsClientId=cid)
    body = pb.createMultiBody(mass, col, basePosition=(0, 0, 0.0005), physicsClientId=cid)
    pb.changeDynamics(body, -1, lateralFriction=0.5, restitution=0.0, physicsClientId=cid)

    for _ in range(int(1.0 / DT)):                       # settle
        pb.stepSimulation(physicsClientId=cid)
    p0, q0 = pb.getBasePositionAndOrientation(body, physicsClientId=cid)

    if omega0 > 0:
        # Pivot = front bottom edge; v_com = omega x r must be set for a clean edge rotation.
        pv = (omega0 * h / 2.0, 0.0, omega0 * t / 2.0)
        pb.resetBaseVelocity(body, linearVelocity=pv, angularVelocity=(0.0, omega0, 0.0),
                             physicsClientId=cid)

    samples = []
    for i in range(int(2.0 / DT)):
        pb.stepSimulation(physicsClientId=cid)
        if i % int(0.02 / DT) == 0:
            p, q = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
            lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
            samples.append({
                "t_s": round(i * DT, 4), "tilt_deg": round(tilt_deg(q), 3),
                "x_m": round(p[0], 6), "z_m": round(p[2], 6),
                "omega_y": round(ang[1], 4), "vx": round(lin[0], 4),
                "contacts_floor": len(pb.getContactPoints(bodyA=body, bodyB=floor,
                                                          physicsClientId=cid)),
            })
    traj[str(omega0)] = samples
    print(f"\n  omega0 = {omega0} rad/s   (settled tilt {tilt_deg(q0):.3f} deg, "
          f"z0 {p0[2]:.6f})")
    print(f"    {'t':>6s} {'tilt':>8s} {'x':>9s} {'z':>9s} {'omega_y':>9s} {'vx':>8s} {'ct':>3s}")
    for s in samples[:22]:
        print(f"    {s['t_s']:6.3f} {s['tilt_deg']:8.3f} {s['x_m']:9.5f} {s['z_m']:9.5f} "
              f"{s['omega_y']:9.4f} {s['vx']:8.4f} {s['contacts_floor']:3d}")
    mx = max(s["tilt_deg"] for s in samples)
    print(f"    -> max tilt {mx:.3f} deg, final tilt {samples[-1]['tilt_deg']:.3f} deg")
    pb.disconnect(cid)

report["tilt_trajectory_cranium"] = traj
(OUT / "b_diag.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_diag.json'}")
