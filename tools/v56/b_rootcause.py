"""V5.6 B root-cause: is the unusable mesh toppling a COM/centre-of-mass placement bug?

The decisive control showed a hand-made EXACT box OBJ as GEOM_MESH placed 70 deg PAST its balance
point springing back to standing, which no rigid box can do. The leading explanation is not contact
physics at all but where pybullet puts the body's centre of mass:

  * for GEOM_MESH the collision shape's local origin is the OBJ's own origin. The upright proxies
    were written with the BASE at z = 0, so if pybullet takes that origin as the COM, the COM sits
    on the FLOOR -- below the pivot edge -- and gravity then always restores the box upright,
    however far it is tipped. That would explain the spring-back exactly.
  * for GEOM_BOX the shape is centred on the origin, so its COM is correctly at mid-height.

This script reads `getDynamicsInfo` (which reports `localInertialPos`) for both shape types, then
re-runs the same tilt-release test with the COM explicitly placed at mid-height via the
`baseInertialFramePosition` argument of `createMultiBody`. If the mesh then topples, the earlier
"these meshes cannot topple" result was a HARNESS bug and not a property of the assets.

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

DT = 1.0 / 240.0
G = 9.81
DENSITY = 200.0
FRICTION = 0.5
AID = "Hasbro_Cranium_Performance_and_Acting_Game"

v_mesh, t_mesh, info = b_geom.upright_vertices(GSO / AID / "collision_geometry.obj")
GSO_OBJ = BUILD / f"{AID}__upright_collision.obj"
b_geom.write_obj(GSO_OBJ, v_mesh, t_mesh)
T, W, H = info["thickness_m"], info["width_m"], info["height_m"]
VOL = info["hull_volume_m3"]

# Same hull, but re-expressed so the mesh ORIGIN is at the geometric centre (COM at origin).
cx = (max(p[0] for p in v_mesh) + min(p[0] for p in v_mesh)) / 2.0
cy = (max(p[1] for p in v_mesh) + min(p[1] for p in v_mesh)) / 2.0
cz = (max(p[2] for p in v_mesh) + min(p[2] for p in v_mesh)) / 2.0
CENTRED_OBJ = BUILD / "cranium_hull_centred.obj"
b_geom.write_obj(CENTRED_OBJ, [(p[0] - cx, p[1] - cy, p[2] - cz) for p in v_mesh], t_mesh)


def tilt_of(q):
    R = pb.getMatrixFromQuaternion(q)
    return math.degrees(math.acos(max(-1.0, min(1.0, R[8]))))


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -G, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[1.5, 1.5, 0.25], physicsClientId=cid)
    fl = pb.createMultiBody(0, fs, basePosition=(0, 0, -0.25), physicsClientId=cid)
    pb.changeDynamics(fl, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return cid, fl


report = {"note": __doc__.strip().splitlines()[0], "dynamics_info": {}, "trials": []}

# --- 1. what does pybullet report as the inertial frame for each shape type? -------------------
cid, floor = new_world()
cs_box = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[T / 2, W / 2, H / 2],
                                 physicsClientId=cid)
b_box = pb.createMultiBody(DENSITY * T * W * H, cs_box, basePosition=(0, 0, H / 2),
                           physicsClientId=cid)
cs_mesh = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(GSO_OBJ), flags=0,
                                  physicsClientId=cid)
b_mesh = pb.createMultiBody(DENSITY * VOL, cs_mesh, basePosition=(0, 0, 0.0),
                            physicsClientId=cid)
for label, b in (("GEOM_BOX (base at z=H/2)", b_box), ("GEOM_MESH (origin at base z=0)", b_mesh)):
    d = pb.getDynamicsInfo(b, -1, physicsClientId=cid)
    report["dynamics_info"][label] = {
        "mass_kg": d[0], "lateral_friction": d[1],
        "local_inertia_diagonal": list(d[2]), "local_inertial_pos": list(d[3]),
        "local_inertial_orn": list(d[4]) if len(d) > 4 else None,
        "collision_shape_type": d[5] if len(d) > 5 else None,
    }
pb.disconnect(cid)

print("=" * 112)
print("ROOT CAUSE CHECK: where does pybullet put the centre of mass?")
for label, d in report["dynamics_info"].items():
    print(f"  {label:36s} mass={d['mass_kg']:.6f}  local_inertial_pos={d['local_inertial_pos']}")
print(f"\n  the box's mid-height is {H/2:.6f} m above its base, so a correct COM for a body whose")
print(f"  origin is at the base would be [0, 0, {H/2:.6f}]. The mesh proxy's origin sits at the base,")
print(f"  so a local_inertial_pos of [0, 0, 0] means the COM is on the FLOOR.")


def release(kind, obj=None, theta0=45.0, com_at_mid=False, sim=2.0):
    """Tilt-release about the front bottom edge; optionally force the COM to mid-height."""
    cid, floor = new_world()
    try:
        mass = DENSITY * (VOL if kind == "mesh" else T * W * H)
        if kind == "mesh":
            cs = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj), flags=0,
                                         physicsClientId=cid)
            kw = {}
            if com_at_mid:
                kw["baseInertialFramePosition"] = [0, 0, H / 2]
            b = pb.createMultiBody(mass, cs, basePosition=(0, 0, 0.0), **kw,
                                   physicsClientId=cid)
            pivot = (T / 2, 0.0, 0.0)
        else:
            cs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[T / 2, W / 2, H / 2],
                                         physicsClientId=cid)
            b = pb.createMultiBody(mass, cs, basePosition=(0, 0, H / 2), physicsClientId=cid)
            pivot = (T / 2, 0.0, -H / 2)
        pb.changeDynamics(b, -1, lateralFriction=FRICTION, restitution=0.0,
                          physicsClientId=cid)
        for _ in range(int(0.8 / DT)):
            pb.stepSimulation(physicsClientId=cid)

        th = math.radians(theta0)
        q = pb.getQuaternionFromEuler([0.0, th, 0.0], physicsClientId=cid)
        R = pb.getMatrixFromQuaternion(q)
        px = R[0] * pivot[0] + R[1] * pivot[1] + R[2] * pivot[2]
        py = R[3] * pivot[0] + R[4] * pivot[1] + R[5] * pivot[2]
        pz = R[6] * pivot[0] + R[7] * pivot[1] + R[8] * pivot[2]
        pb.resetBasePositionAndOrientation(b, (-px, -py, -pz + 0.0002), q, physicsClientId=cid)
        pb.resetBaseVelocity(b, (0, 0, 0), (0, 0, 0), physicsClientId=cid)
        _p, q_placed = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        placed = tilt_of(q_placed)

        traj = []
        for i in range(int(sim / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if i % 8 == 0:
                p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
                traj.append([round(i * DT, 4), round(tilt_of(q), 3)])
        p, q = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        return {"tilt_placed_deg": round(placed, 3),
                "max_tilt_deg": round(max(t[1] for t in traj), 3),
                "final_tilt_deg": round(tilt_of(q), 3),
                "toppled": bool(tilt_of(q) >= 60.0),
                "trajectory": traj}
    finally:
        pb.disconnect(cid)


print("\n--- re-run the identical tilt-release test WITH the COM moved to mid-height ---")
print(f"  {'trial':54s} {'placed':>8s} {'maxTilt':>8s} {'finTilt':>8s} {'topl':>5s}")
for label, kind, obj, com in (
    ("GEOM_BOX  release 45 deg", "box", None, False),
    ("GEOM_MESH hull origin-at-base, release 45", "mesh", GSO_OBJ, False),
    ("GEOM_MESH hull origin-at-base, COM fixed to mid", "mesh", GSO_OBJ, True),
    ("GEOM_MESH hull origin-at-centre, release 45", "mesh", CENTRED_OBJ, False),
    ("GEOM_MESH hull origin-at-centre, COM fixed to mid", "mesh", CENTRED_OBJ, True),
    ("GEOM_MESH hull origin-at-base, COM fixed, release 20", "mesh", GSO_OBJ, True),
):
    r = release(kind, obj=obj, theta0=20.0 if label.endswith("20") else 45.0, com_at_mid=com)
    r["label"] = label
    report["trials"].append(r)
    print(f"  {label:54s} {r['tilt_placed_deg']:8.2f} {r['max_tilt_deg']:8.2f} "
          f"{r['final_tilt_deg']:8.2f} {str(r['toppled']):>5s}")

print("\n--- trajectories (t, tilt) for the fixed-COM mesh vs the plain mesh ---")
for r in report["trials"]:
    if "release 45" in r["label"] or "release 20" in r["label"]:
        print(f"  {r['label'][:52]:52s} {[t[1] for t in r['trajectory'][:16]]}")

(OUT / "b_rootcause.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_rootcause.json'}")
