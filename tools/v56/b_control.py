"""V5.6 B control: is the trigger/harness able to topple ANY box, and is the failure an artefact?

The first physical run produced a result that cannot be taken at face value: with a trigger whose
energy was 4-9x the analytic tipping barrier, the striker reached 17.15 deg -- PAST its 11.58 deg
balance point -- and still rocked back to standing. A rigid box pivoting on its front edge cannot do
that. Before any conclusion about the GSO assets is drawn, the harness must be shown to topple a
KNOWN-GOOD domino, otherwise a failure would be a property of the trigger, not of the asset.

Controls, all at the same dims/mass as the Cranium box (t=55.838, w=207.669, h=272.574 mm):

  A. plain GEOM_BOX domino, angular-velocity push trigger
  B. the GSO collision hull as GEOM_MESH, angular-velocity push trigger
  C. the GSO collision hull as an idealised GEOM_BOX (box approximation of its own dims)
  D. plain GEOM_BOX domino, TILT-RELEASE trigger (placed past its balance point, gravity does the rest)

The tilt-release trigger removes the energy-budget ambiguity entirely: a body placed beyond its
balance point MUST topple under gravity. If A/D topple but B does not, the difference is the real
effect of the scanned hull shape. If nothing topples, the harness itself is at fault.

Energy is logged over time so dissipation is measured rather than inferred.
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


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -G, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)
    fs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[1.5, 1.5, 0.25], physicsClientId=cid)
    floor = pb.createMultiBody(0, fs, basePosition=(0, 0, -0.25), physicsClientId=cid)
    pb.changeDynamics(floor, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return cid, floor


def add_box(cid, half, mass, pos, quat=(0, 0, 0, 1)):
    s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=half, physicsClientId=cid)
    b = pb.createMultiBody(mass, s, basePosition=pos, baseOrientation=quat, physicsClientId=cid)
    pb.changeDynamics(b, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return b


def add_mesh(cid, obj, mass, pos, quat=(0, 0, 0, 1)):
    s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj), flags=0, physicsClientId=cid)
    b = pb.createMultiBody(mass, s, basePosition=pos, baseOrientation=quat, physicsClientId=cid)
    pb.changeDynamics(b, -1, lateralFriction=FRICTION, restitution=0.0, physicsClientId=cid)
    return b


def energy(cid, body, mass, floor_z=0.0):
    """Total mechanical energy about the floor datum, using the full inertia diagonal."""
    p, q = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
    lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
    dyn = pb.getDynamicsInfo(body, -1, physicsClientId=cid)
    I = dyn[2]
    ke = 0.5 * mass * sum(v * v for v in lin) + 0.5 * sum(I[i] * ang[i] ** 2 for i in range(3))
    pe = mass * G * (p[2] - floor_z)
    return ke, pe, p, q, lin, ang


def run(label, kind, half=None, obj=None, trigger="push", omega0=3.0, theta0=None,
        settle=1.0, sim=2.5, spawn_clearance=0.0005):
    """One control run. Returns the trajectory and a verdict."""
    verts = None
    if kind == "mesh":
        v, t, info = b_geom.upright_vertices(GSO / AID / "collision_geometry.obj")
        obj = BUILD / f"{AID}__upright_collision.obj"
        b_geom.write_obj(obj, v, t)
        half = [info["thickness_m"] / 2, info["width_m"] / 2, info["height_m"] / 2]
        vol = info["hull_volume_m3"]
    else:
        vol = 8 * half[0] * half[1] * half[2]
    mass = DENSITY * vol

    cid, floor = new_world()
    try:
        quat = (0, 0, 0, 1)
        pos = [0.0, 0.0, spawn_clearance]
        if trigger == "tilt":
            # Rotate the body about its front bottom edge by theta0, keeping that edge on the floor.
            th = math.radians(theta0)
            t = 2 * half[0]
            # body origin is the base centre; pivot edge is at local (+t/2, 0, 0)
            pos = [t / 2 * (1 - math.cos(th)), 0.0, t / 2 * math.sin(th) + spawn_clearance]
            quat = pb.getQuaternionFromEuler([0.0, th, 0.0], physicsClientId=cid)
            # lift so the pivot edge sits exactly on the floor: the rotated body's lowest point is
            # the pivot itself, so only the clearance remains.
        if kind == "mesh":
            body = add_mesh(cid, obj, mass, pos, quat)
        else:
            body = add_box(cid, half, mass, pos, quat)

        for _ in range(int(settle / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p0, q0 = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
        tilt_at_trigger = tilt_deg(q0)

        if trigger == "push":
            h = 2 * half[2]
            t = 2 * half[0]
            pv = (omega0 * h / 2.0, 0.0, omega0 * t / 2.0)   # v = omega x (com - pivot)
            pb.resetBaseVelocity(body, linearVelocity=pv, angularVelocity=(0.0, omega0, 0.0),
                                 physicsClientId=cid)
        elif trigger == "tilt":
            pb.resetBaseVelocity(body, linearVelocity=(0, 0, 0), angularVelocity=(0, 0, 0),
                                 physicsClientId=cid)

        # Balance angle measured from the ACTUAL settled pose, for reference.
        tip_deg = tilt_at_trigger + math.degrees(
            math.atan2(2 * half[0], 2 * half[2]))

        samples = []
        prev_ke = prev_pe = None
        for i in range(int(sim / DT)):
            pb.stepSimulation(physicsClientId=cid)
            if i % int(0.02 / DT) == 0:
                ke, pe, p, q, lin, ang = energy(cid, body, mass)
                samples.append({
                    "t_s": round(i * DT, 4), "tilt_deg": round(tilt_deg(q), 3),
                    "x_m": round(p[0], 6), "z_m": round(p[2], 6),
                    "ke_J": round(ke, 8), "pe_J": round(pe, 8),
                    "total_J": round(ke + pe, 8),
                    "contacts": len(pb.getContactPoints(bodyA=body, bodyB=floor,
                                                        physicsClientId=cid)),
                })
        p, q = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
        max_tilt = max(s["tilt_deg"] for s in samples)
        e0 = samples[0]["total_J"]
        e_min = min(s["total_J"] for s in samples)
        return {
            "label": label, "kind": kind, "trigger": trigger,
            "mass_kg": mass, "half_extents_m": half,
            "tilt_at_trigger_deg": tilt_at_trigger,
            "balance_angle_deg": tip_deg,
            "max_tilt_deg": max_tilt, "final_tilt_deg": tilt_deg(q),
            "toppled": bool(tilt_deg(q) >= 60.0),
            "energy_initial_J": e0, "energy_min_J": e_min,
            "energy_lost_to_min_J": e0 - e_min,
            "energy_lost_fraction": (e0 - e_min) / e0 if e0 > 0 else None,
            "samples": samples,
        }
    finally:
        pb.disconnect(cid)


half_mesh = None
v, t, info = b_geom.upright_vertices(GSO / AID / "collision_geometry.obj")
half_mesh = [info["thickness_m"] / 2, info["width_m"] / 2, info["height_m"] / 2]
t_crit = math.degrees(math.atan2(info["thickness_m"], info["height_m"]))
w_crit = math.sqrt(3 * G * (math.hypot(info["thickness_m"], info["height_m"])
                            - info["height_m"]) / math.hypot(info["thickness_m"],
                                                             info["height_m"]) ** 2)

print("=" * 112)
print("V5.6 B CONTROL: can the harness topple a known-good box?")
print(f"  Cranium dims t x w x h = {info['thickness_m']:.6f} x {info['width_m']:.6f} x "
      f"{info['height_m']:.6f} m")
print(f"  critical balance angle {t_crit:.3f} deg, analytic w_crit {w_crit:.4f} rad/s")
print(f"  half extents used for the control GEOM_BOX: {[round(x,6) for x in half_mesh]}")

runs = []
runs.append(run("A: plain BOX, push w=3.0", "box", half=half_mesh, trigger="push", omega0=3.0))
runs.append(run("A2: plain BOX, push w=4.5", "box", half=half_mesh, trigger="push", omega0=4.5))
runs.append(run("B: GSO hull MESH, push w=3.0", "mesh", trigger="push", omega0=3.0))
runs.append(run("B2: GSO hull MESH, push w=4.5", "mesh", trigger="push", omega0=4.5))
runs.append(run("C: GSO dims as BOX, push w=3.0", "box", half=half_mesh, trigger="push",
                omega0=3.0))
for th in (t_crit + 5.0, 30.0, 45.0):
    runs.append(run(f"D: plain BOX, tilt-release {th:.1f} deg", "box", half=half_mesh,
                    trigger="tilt", theta0=th))
    runs.append(run(f"D2: GSO hull MESH, tilt-release {th:.1f} deg", "mesh", trigger="tilt",
                    theta0=th))

print(f"\n  {'run':44s} {'trig':>5s} {'bal':>7s} {'maxTilt':>8s} {'finTilt':>8s} {'topl':>5s} "
      f"{'E0_J':>9s} {'Emin_J':>9s} {'lost%':>7s}")
for r in runs:
    print(f"  {r['label']:44s} {r['trigger']:>5s} {r['balance_angle_deg']:7.2f} "
          f"{r['max_tilt_deg']:8.2f} {r['final_tilt_deg']:8.2f} "
          f"{str(r['toppled']):>5s} {r['energy_initial_J']:9.6f} {r['energy_min_J']:9.6f} "
          f"{(r['energy_lost_fraction'] or 0)*100:7.2f}")

print("\n=== trajectories (tilt deg, every 40 ms, first 1.2 s) ===")
for r in runs:
    seq = [s["tilt_deg"] for s in r["samples"] if s["t_s"] <= 1.2][::2]
    print(f"  {r['label']:44s} {seq}")

(OUT / "b_control.json").write_text(json.dumps({
    "note": "control runs deciding whether the harness/trigger can topple a known-good domino",
    "cranium_dims_m": info, "balance_angle_deg": t_crit, "analytic_w_crit_rad_s": w_crit,
    "runs": runs}, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_control.json'}")
