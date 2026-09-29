"""V5.6 B decisive control: is the mesh's refusal to topple REAL geometry or a shape-type artefact?

The control run showed something that decides how the whole re-verification must be read:

  * a plain GEOM_BOX with EXACTLY the Cranium dimensions topples cleanly from the same push
    (max tilt 91 deg);
  * the same dimensions taken from the GSO `collision_geometry.obj` as a GEOM_MESH reaches only
    7-17 deg and rocks back to standing, after dissipating ~95% of the trigger energy.

Dims and mass are near-identical, so either the scanned hull's SHAPE is responsible (real physics),
or GEOM_MESH collisions of a thin box behave differently from GEOM_BOX (a simulation artefact). The
distinction matters enormously: if it is an artefact, then "these boxes cannot knock each other
over" is an artefact too, and must not be reported as a physical property of the assets.

This script separates the two by holding the shape constant and varying only the shape TYPE:

  E1  GEOM_BOX   with the Cranium dims                       (baseline: topples)
  E2  GEOM_MESH  built from a hand-made EXACT box OBJ with the SAME dims  <- the discriminator
  E3  GEOM_MESH  from the GSO collision hull                 (the asset's real proxy)

If E2 topples like E1, the shape type is fine and E3's failure is a property of the scanned hull.
If E2 also fails, GEOM_MESH thin-box collisions are at fault and the failure is (at least partly) an
artefact.

It also measures the hull's own bottom-face geometry, because a warped or inset base would explain
a genuine inability to pivot:
  * how many hull vertices lie within 1 mm of the base, and their z spread (a warped base rocks);
  * whether the base contact is an edge (1-2 manifold points) or a face (4+), sampled as the box
    begins to tip -- an edge pivot cannot dissipate energy the way a face slap does.

Triggers are placement-verified: the tilt is read back IMMEDIATELY after placement and before any
settling, so a placement bug cannot masquerade as an inability to topple.
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

T = info["thickness_m"]
W = info["width_m"]
H = info["height_m"]
VOL_HULL = info["hull_volume_m3"]

# An EXACT box OBJ with the identical outer dimensions: 8 vertices, 12 triangles, base at z = 0.
EXACT_OBJ = BUILD / "exact_box_same_dims.obj"
_ev = [(sx * T / 2, sy * W / 2, sz * H) for sx in (-1, 1) for sy in (-1, 1) for sz in (0, 1)]
_ef = [(0, 1, 3), (0, 3, 2), (4, 7, 5), (4, 6, 7), (0, 4, 5), (0, 5, 1),
       (2, 3, 7), (2, 7, 6), (0, 6, 2), (0, 4, 6), (1, 5, 7), (1, 7, 3)]
b_geom.write_obj(EXACT_OBJ, _ev, _ef)


def tilt_from_quat(q):
    R = pb.getMatrixFromQuaternion(q)
    up_z = R[8]                       # element (2,2) of the row-major 3x3
    return math.degrees(math.acos(max(-1.0, min(1.0, up_z))))


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -G, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[1.5, 1.5, 0.25], physicsClientId=cid)
    fl = pb.createMultiBody(0, fs, basePosition=(0, 0, -0.25), physicsClientId=cid)
    pb.changeDynamics(fl, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return cid, fl


def make_body(cid, kind, obj=None):
    """Return (body, mass, pivot_local). pivot_local is the front bottom edge in body coords."""
    if kind == "box":
        vol = T * W * H
        mass = DENSITY * vol
        s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[T / 2, W / 2, H / 2],
                                    physicsClientId=cid)
        b = pb.createMultiBody(mass, s, basePosition=(0, 0, H / 2),
                               physicsClientId=cid)
        pivot = (T / 2, 0.0, -H / 2)          # origin is the box CENTRE
    else:
        vol = VOL_HULL
        mass = DENSITY * vol
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj), flags=0,
                                    physicsClientId=cid)
        b = pb.createMultiBody(mass, s, basePosition=(0, 0, 0.0), physicsClientId=cid)
        pivot = (T / 2, 0.0, 0.0)             # origin is the BASE centre
    pb.changeDynamics(b, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return b, mass, pivot


def place_about_edge(cid, body, pivot_local, theta_deg):
    """Rotate the body about its front bottom edge, with that edge exactly on the floor.

    Uses pybullet's OWN quaternion->matrix, so the placement cannot disagree with the engine's
    rotation convention (an earlier hand-rolled version did exactly that).
    """
    th = math.radians(theta_deg)
    q = pb.getQuaternionFromEuler([0.0, th, 0.0], physicsClientId=cid)
    R = pb.getMatrixFromQuaternion(q)
    # basePosition = pivot_world - R @ pivot_local, with pivot_world at the origin on the floor
    px = R[0] * pivot_local[0] + R[1] * pivot_local[1] + R[2] * pivot_local[2]
    py = R[3] * pivot_local[0] + R[4] * pivot_local[1] + R[5] * pivot_local[2]
    pz = R[6] * pivot_local[0] + R[7] * pivot_local[1] + R[8] * pivot_local[2]
    pb.resetBasePositionAndOrientation(body, (-px, -py, -pz + 0.0002), q, physicsClientId=cid)
    pb.resetBaseVelocity(body, (0, 0, 0), (0, 0, 0), physicsClientId=cid)


def trial(label, kind, obj=None, mode="push", omega0=3.0, theta0=None, sim=2.5):
    cid, floor = new_world()
    try:
        body, mass, pivot = make_body(cid, kind, obj)
        for _ in range(int(0.8 / DT)):            # settle upright
            pb.stepSimulation(physicsClientId=cid)
        _, q_settled = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
        tilt_before = tilt_from_quat(q_settled)

        if mode == "push":
            pv = (omega0 * H / 2.0, 0.0, omega0 * T / 2.0)
            pb.resetBaseVelocity(body, linearVelocity=pv, angularVelocity=(0.0, omega0, 0.0),
                                 physicsClientId=cid)
            tilt_placed = tilt_before
        else:
            place_about_edge(cid, body, pivot, theta0)
            _, q_now = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
            tilt_placed = tilt_from_quat(q_now)   # VERIFY the placement orientation

        samples = []
        for i in range(int(sim / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if i % 4 == 0:
                p, q = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                cps = pb.getContactPoints(bodyA=body, bodyB=floor, physicsClientId=cid)
                samples.append({
                    "t_s": round(i * DT, 4), "tilt_deg": round(tilt_from_quat(q), 3),
                    "x_m": round(p[0], 6), "z_m": round(p[2], 6),
                    "floor_contacts": len(cps),
                })
        p, q = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
        return {
            "label": label, "kind": kind, "mode": mode,
            "mass_kg": round(mass, 6),
            "tilt_before_trigger_deg": round(tilt_before, 4),
            "tilt_placed_deg": round(tilt_placed, 4),
            "release_angle_requested_deg": theta0,
            "max_tilt_deg": round(max(s["tilt_deg"] for s in samples), 3),
            "final_tilt_deg": round(tilt_from_quat(q), 3),
            "toppled": bool(tilt_from_quat(q) >= 60.0),
            "max_floor_contacts_early": max(s["floor_contacts"] for s in samples[:25]),
            "trajectory": samples,
        }
    finally:
        pb.disconnect(cid)


report = {
    "note": __doc__.strip().splitlines()[0],
    "cranium_dims_m": {"t": T, "w": W, "h": H},
    "hull_volume_m3": VOL_HULL, "exact_box_volume_m3": T * W * H,
    "balance_angle_deg": math.degrees(math.atan2(T, H)),
    "trials": [],
}

print("=" * 116)
print("DECISIVE CONTROL: shape TYPE vs shape GEOMETRY")
print(f"  Cranium t x w x h = {T:.6f} x {W:.6f} x {H:.6f} m, balance angle "
      f"{math.degrees(math.atan2(T, H)):.3f} deg")
print(f"  GSO hull volume {VOL_HULL:.9f} m^3 vs exact box {T*W*H:.9f} m^3 "
      f"(hull/box {VOL_HULL/(T*W*H):.4f})")

print("\n--- E: PUSH trigger, same dims and push, only the shape type changes ---")
trials = []
trials.append(trial("E1 GEOM_BOX  dims=Cranium, push w=3.0", "box", mode="push", omega0=3.0))
trials.append(trial("E2 GEOM_MESH EXACT box OBJ same dims, push w=3.0", "mesh", obj=EXACT_OBJ,
                    mode="push", omega0=3.0))
trials.append(trial("E3 GEOM_MESH GSO hull, push w=3.0", "mesh", obj=GSO_OBJ,
                    mode="push", omega0=3.0))
trials.append(trial("E2b GEOM_MESH EXACT box, push w=4.5", "mesh", obj=EXACT_OBJ,
                    mode="push", omega0=4.5))
trials.append(trial("E3b GEOM_MESH GSO hull, push w=4.5", "mesh", obj=GSO_OBJ,
                    mode="push", omega0=4.5))

print(f"\n  {'trial':50s} {'placed':>8s} {'maxTilt':>8s} {'finTilt':>8s} {'topl':>5s} {'ctMax':>6s}")
for r in trials:
    print(f"  {r['label']:50s} {r['tilt_placed_deg']:8.2f} {r['max_tilt_deg']:8.2f} "
          f"{r['final_tilt_deg']:8.2f} {str(r['toppled']):>5s} {r['max_floor_contacts_early']:6d}")
report["trials"].extend(trials)

print("\n--- F: TILT-RELEASE trigger, placement read back, both signs of rotation ---")
rel = []
for kind, obj, tag in (("box", None, "GEOM_BOX"), ("mesh", EXACT_OBJ, "MESH exact-box"),
                       ("mesh", GSO_OBJ, "MESH GSO hull")):
    for th in (20.0, 45.0, 70.0, -45.0):
        # theta about +y tips the box's top toward +x; the sign that puts the COM ahead of the
        # pivot is the one that must topple. Both signs are run so neither is assumed.
        r = trial(f"F {tag} release {th:+.0f} deg", kind, obj=obj, mode="tilt", theta0=th,
                  sim=2.0)
        rel.append(r)
report["trials"].extend(rel)
print(f"\n  {'trial':46s} {'placed':>8s} {'maxTilt':>8s} {'finTilt':>8s} {'topl':>5s}")
for r in rel:
    print(f"  {r['label']:46s} {r['tilt_placed_deg']:8.2f} {r['max_tilt_deg']:8.2f} "
          f"{r['final_tilt_deg']:8.2f} {str(r['toppled']):>5s}")

# --- bottom-face geometry of the GSO hull ------------------------------------------------------
print("\n--- G: base geometry of the GSO collision hull (why might it not pivot?) ---")
zbase = min(p[2] for p in v_mesh)
near = [p for p in v_mesh if p[2] - zbase < 0.001]
zs = [p[2] - zbase for p in near]
base = {
    "total_vertices": len(v_mesh),
    "vertices_within_1mm_of_base": len(near),
    "base_z_spread_mm": (max(zs) - min(zs)) * 1000 if zs else None,
    "base_x_extent_mm": (max(p[0] for p in near) - min(p[0] for p in near)) * 1000 if near else None,
    "base_y_extent_mm": (max(p[1] for p in near) - min(p[1] for p in near)) * 1000 if near else None,
    "box_x_extent_mm": T * 1000, "box_y_extent_mm": W * 1000,
    "distinct_base_z_values_mm": sorted({round(z * 1000, 6) for z in zs}),
}
print(f"  vertices within 1 mm of the base : {base['vertices_within_1mm_of_base']} of "
      f"{base['total_vertices']}")
print(f"  base z spread                    : {base['base_z_spread_mm']} mm")
print(f"  distinct base z values (mm)      : {base['distinct_base_z_values_mm']}")
print(f"  base footprint x extent          : {base['base_x_extent_mm']} mm "
      f"(box {base['box_x_extent_mm']} mm)")
print(f"  base footprint y extent          : {base['base_y_extent_mm']} mm "
      f"(box {base['box_y_extent_mm']} mm)")
report["base_geometry"] = base

(OUT / "b_control2.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_control2.json'}")
