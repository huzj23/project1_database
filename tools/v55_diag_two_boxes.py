"""V5.5 stage 04 diagnostic: why did the two real boxes not collide?

The smoke test reported a 0.11 mm target displacement and zero recorded contacts, yet the
geometry should guarantee an impact.  Rather than guess, this steps the same scene and
prints the trigger's own position and velocity every frame, plus whether pybullet itself
reports any contact at all (with an unlimited force threshold).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main")
sys.path.insert(0, str(REPO / "src"))

import pybullet as pb  # noqa: E402

from physim.contracts import ROLE_TARGET, ROLE_TRIGGER, BodySpec, box_inertia_diagonal  # noqa: E402
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

HE = (0.05, 0.05, 0.025)
DIMS = tuple(2 * h for h in HE)


def mk(iid, role, pos, vel=(0, 0, 0), mass=0.35):
    return BodySpec(
        instance_id=iid, asset_id="prim", role=role, mass_kg=mass,
        mass_basis="estimated", collider_type="box",
        position_m=tuple(float(v) for v in pos),
        linear_velocity_m_s=tuple(float(v) for v in vel),
        inertia_diagonal_kg_m2=box_inertia_diagonal(mass, DIMS),
    )


trigger = mk("box_001", ROLE_TRIGGER, (-0.30, 0.0, 0.0251), (0.8, 0, 0))
target = mk("box_002", ROLE_TARGET, (0.0, 0.0, 0.0251))
prims = {"box_001": {"half_extents_m": HE}, "box_002": {"half_extents_m": HE}}

settings = SolverSettings(physics_fps=480.0, video_fps=24.0)
solver = MultibodySolver(settings)
solver.connect()

print("=== A. body creation sanity ===")
solver.load([trigger, target],
            [__import__("physim.contracts", fromlist=["StaticCollider"]).StaticCollider(
                collider_id="static:ground", collider_type="plane",
                position_m=(0.0, 0.0, 0.0))],
            primitives=prims)
cid = solver.client
print(f"  body ids: {solver._body_ids}")
print(f"  static ids: {solver._static_ids}")
for iid, bid in solver._body_ids.items():
    dyn = pb.getDynamicsInfo(bid, -1, physicsClientId=cid)
    pos, orn = pb.getBasePositionAndOrientation(bid, physicsClientId=cid)
    lin, ang = pb.getBaseVelocity(bid, physicsClientId=cid)
    print(f"  {iid}: id={bid} mass={dyn[0]} pos={tuple(round(v,5) for v in pos)} "
          f"lin={tuple(round(v,5) for v in lin)} friction={dyn[1]}")

print()
print("=== B. step and watch the trigger ===")
print(f"  {'step':>5} {'t':>7} {'x1':>9} {'v1x':>8} {'x2':>9} {'v2x':>8} {'ncontacts':>9}")
prev_x1 = None
for step in range(1, 481):
    pb.stepSimulation(physicsClientId=cid)
    if step % 20 == 0:
        p1, _ = pb.getBasePositionAndOrientation(solver._body_ids["box_001"], physicsClientId=cid)
        v1, _ = pb.getBaseVelocity(solver._body_ids["box_001"], physicsClientId=cid)
        p2, _ = pb.getBasePositionAndOrientation(solver._body_ids["box_002"], physicsClientId=cid)
        v2, _ = pb.getBaseVelocity(solver._body_ids["box_002"], physicsClientId=cid)
        # Ask pybullet directly, with no threshold at all.
        raw = pb.getContactPoints(solver._body_ids["box_001"], solver._body_ids["box_002"],
                                  physicsClientId=cid)
        print(f"  {step:5d} {step/480:7.4f} {p1[0]:9.5f} {v1[0]:8.4f} {p2[0]:9.5f} "
              f"{v2[0]:8.4f} {len(raw):9d}")
        if prev_x1 is not None and abs(p1[0] - prev_x1) < 1e-9 and step > 40:
            print(f"    (trigger stopped moving between step {step-20} and {step})")
        prev_x1 = p1[0]

print()
print("=== C. ground contact check ===")
raw_ground = pb.getContactPoints(solver._body_ids["box_001"],
                                 solver._static_ids["static:ground"], physicsClientId=cid)
print(f"  trigger-ground contact points: {len(raw_ground)}")
if raw_ground:
    print(f"  normal={tuple(round(v,4) for v in raw_ground[0][7])} "
          f"distance={raw_ground[0][8]:.6f} force={raw_ground[0][9]:.4f}")

print()
print("=== D. does the trigger's x actually change over the whole run? ===")
p1, _ = pb.getBasePositionAndOrientation(solver._body_ids["box_001"], physicsClientId=cid)
print(f"  trigger x now = {p1[0]:.6f} (started at -0.30)")
print(f"  travelled {p1[0] - (-0.30):.6f} m")

solver.disconnect()
