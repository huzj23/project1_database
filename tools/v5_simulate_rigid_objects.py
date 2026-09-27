"""Generate deterministic real-PyBullet trajectories for the V5 videos.

Both clips use the exact exported Cozy Kitchen ``Ground`` mesh as the static
collision body.  The Nikon camera and Netgear router use their Google Scanned
Objects convex collision meshes; only the clearly nonphysical density-derived
URDF masses are replaced with measured-product-scale masses.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pybullet as p


ROOT = Path("/data/raw/huzijian/project1_database")
LAYOUT = ROOT / "tmp/v5_cozy_interaction_layout.json"
GROUND_OBJ = ROOT / "models/backgrounds/cozy_kitchen/collision/Ground.obj"
NIKON_DIR = ROOT / "models/gso/Nikon_1_AW1_w11275mm_Lens_Silver"
ROUTER_DIR = ROOT / "models/gso/Netgear_N750_Wireless_Dual_Band_Gigabit_Router"
OUTPUT_DIR = ROOT / "outcomes/v5/physics"

VIDEO_FPS = 16
PHYSICS_FPS = 480
FRAME_COUNT = 48
SUBSTEPS = PHYSICS_FPS // VIDEO_FPS
DT = 1.0 / PHYSICS_FPS

OBJECTS = {
    "nikon": {
        "asset_id": "Nikon_1_AW1_w11275mm_Lens_Silver",
        "urdf": NIKON_DIR / "object.urdf",
        "visual_obj": NIKON_DIR / "visual_geometry.obj",
        "bounds_min": (-0.0313251680, -0.0314206701, -0.0389613544),
        "bounds_max": (0.0315048320, 0.0314343299, 0.0396706456),
        # Nikon official specs: AW1 body 313 g + AW 11-27.5 mm lens 182 g.
        "mass_kg": 0.495,
    },
    "router": {
        "asset_id": "Netgear_N750_Wireless_Dual_Band_Gigabit_Router",
        "urdf": ROUTER_DIR / "object.urdf",
        "visual_obj": ROUTER_DIR / "visual_geometry.obj",
        "bounds_min": (-0.1492619048, -0.0369842307, -0.1325092017),
        "bounds_max": (0.1469980952, 0.0353857693, 0.1333817983),
        "mass_kg": 0.50,
    },
}


def inertia_box(mass: float, lower: tuple[float, ...], upper: tuple[float, ...]):
    sx, sy, sz = (upper[index] - lower[index] for index in range(3))
    return (
        mass * (sy * sy + sz * sz) / 12.0,
        mass * (sx * sx + sz * sz) / 12.0,
        mass * (sx * sx + sy * sy) / 12.0,
    )


def state(body_id: int, frame: int) -> dict[str, Any]:
    position, quaternion = p.getBasePositionAndOrientation(body_id)
    linear, angular = p.getBaseVelocity(body_id)
    return {
        "frame": frame,
        "time_seconds": (frame - 1) / VIDEO_FPS,
        "position": [float(value) for value in position],
        "quaternion_xyzw": [float(value) for value in quaternion],
        "linear_velocity": [float(value) for value in linear],
        "angular_velocity": [float(value) for value in angular],
    }


def horizontal_distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def reset_world() -> int:
    p.resetSimulation()
    p.setGravity(0.0, 0.0, -9.81)
    p.setTimeStep(DT)
    p.setPhysicsEngineParameter(
        fixedTimeStep=DT,
        numSolverIterations=100,
        deterministicOverlappingPairs=1,
        enableConeFriction=1,
    )
    shape = p.createCollisionShape(
        shapeType=p.GEOM_MESH,
        fileName=str(GROUND_OBJ),
        meshScale=(1.0, 1.0, 1.0),
        flags=p.GEOM_FORCE_CONCAVE_TRIMESH,
    )
    ground_id = p.createMultiBody(
        baseMass=0.0,
        baseCollisionShapeIndex=shape,
        basePosition=(0.0, 0.0, 0.0),
        baseOrientation=(0.0, 0.0, 0.0, 1.0),
    )
    p.changeDynamics(
        ground_id,
        -1,
        lateralFriction=0.55,
        rollingFriction=0.001,
        spinningFriction=0.001,
        restitution=0.03,
    )
    return ground_id


def load_object(name: str, position, quaternion) -> int:
    spec = OBJECTS[name]
    body = p.loadURDF(
        str(spec["urdf"]),
        basePosition=position,
        baseOrientation=quaternion,
        useFixedBase=False,
        flags=p.URDF_USE_INERTIA_FROM_FILE,
    )
    p.changeDynamics(
        body,
        -1,
        mass=spec["mass_kg"],
        localInertiaDiagonal=inertia_box(
            spec["mass_kg"], spec["bounds_min"], spec["bounds_max"]
        ),
        lateralFriction=0.38,
        rollingFriction=0.001,
        spinningFriction=0.001,
        restitution=0.05,
        linearDamping=0.02,
        angularDamping=0.02,
    )
    return body


def contact_row(contact, frame: int, substep: int) -> dict[str, Any]:
    return {
        "frame": frame,
        "substep": substep,
        "time_seconds": ((frame - 1) * SUBSTEPS + substep) * DT,
        "position_on_a": [float(value) for value in contact[5]],
        "position_on_b": [float(value) for value in contact[6]],
        "contact_normal_on_b": [float(value) for value in contact[7]],
        "distance": float(contact[8]),
        "normal_force": float(contact[9]),
    }


def base_report(layout: dict[str, Any], scenario: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "solver": "PyBullet",
        "physics_fps": PHYSICS_FPS,
        "video_fps": VIDEO_FPS,
        "frame_count": FRAME_COUNT,
        "gravity_m_s2": [0.0, 0.0, -9.81],
        "ground_collision": {
            "source_blend": layout["source_blend"],
            "source_object": layout["source_ground_object"],
            "mesh": str(GROUND_OBJ),
            "sha256_recorded_by_prepare_job": True,
        },
        "objects": {
            key: {
                "asset_id": value["asset_id"],
                "urdf": str(value["urdf"]),
                "visual_obj": str(value["visual_obj"]),
                "bounds_min": value["bounds_min"],
                "bounds_max": value["bounds_max"],
                "mass_kg": value["mass_kg"],
                "rigid": True,
            }
            for key, value in OBJECTS.items()
        },
        "layout": layout["selected"],
    }


def run_drop(layout: dict[str, Any]) -> dict[str, Any]:
    ground = reset_world()
    selected = layout["selected"]
    z = float(selected["surface_z"])
    direction = selected["direction_xy"]
    theta = math.atan2(direction[1], direction[0])
    nikon_q = p.getQuaternionFromEuler((0.0, 0.0, theta))
    router_q = p.getQuaternionFromEuler((0.0, 0.0, theta))
    nikon_xy = selected["actor_xy"]
    router_xy = selected["target_xy"]
    drop_height = 0.38
    nikon = load_object(
        "nikon",
        (nikon_xy[0], nikon_xy[1], z - OBJECTS["nikon"]["bounds_min"][2] + drop_height),
        nikon_q,
    )
    router = load_object(
        "router",
        (router_xy[0], router_xy[1], z - OBJECTS["router"]["bounds_min"][2] + drop_height),
        router_q,
    )
    report = base_report(layout, "new_rigid_objects_drop")
    report["initial_drop_height_m"] = drop_height
    report["trajectories"] = {"nikon": [], "router": []}
    report["ground_contacts"] = {"nikon": [], "router": []}
    for frame in range(1, FRAME_COUNT + 1):
        report["trajectories"]["nikon"].append(state(nikon, frame))
        report["trajectories"]["router"].append(state(router, frame))
        for substep in range(SUBSTEPS):
            p.stepSimulation()
            for name, body in (("nikon", nikon), ("router", router)):
                contacts = p.getContactPoints(bodyA=body, bodyB=ground)
                if contacts and len(report["ground_contacts"][name]) < 80:
                    strongest = max(contacts, key=lambda item: item[9])
                    report["ground_contacts"][name].append(
                        contact_row(strongest, frame, substep)
                    )
    report["validation"] = {
        "nikon_ground_contact_count": len(report["ground_contacts"]["nikon"]),
        "router_ground_contact_count": len(report["ground_contacts"]["router"]),
        "nikon_drop_m": (
            report["trajectories"]["nikon"][0]["position"][2]
            - min(row["position"][2] for row in report["trajectories"]["nikon"])
        ),
        "router_drop_m": (
            report["trajectories"]["router"][0]["position"][2]
            - min(row["position"][2] for row in report["trajectories"]["router"])
        ),
    }
    report["validation"]["passed"] = bool(
        report["validation"]["nikon_ground_contact_count"] > 0
        and report["validation"]["router_ground_contact_count"] > 0
        and report["validation"]["nikon_drop_m"] > 0.20
        and report["validation"]["router_drop_m"] > 0.20
    )
    return report


def run_interaction_attempt(layout: dict[str, Any], launch_speed: float) -> dict[str, Any]:
    ground = reset_world()
    selected = layout["selected"]
    z = float(selected["surface_z"])
    dx, dy = (float(value) for value in selected["direction_xy"])
    theta = math.atan2(dy, dx)
    nikon_q = p.getQuaternionFromEuler((0.0, 0.0, theta))
    router_q = p.getQuaternionFromEuler((0.0, 0.0, theta))
    nikon_xy = selected["actor_xy"]
    router_xy = selected["target_xy"]
    nikon = load_object(
        "nikon",
        (nikon_xy[0], nikon_xy[1], z - OBJECTS["nikon"]["bounds_min"][2] + 0.003),
        nikon_q,
    )
    router = load_object(
        "router",
        (router_xy[0], router_xy[1], z - OBJECTS["router"]["bounds_min"][2] + 0.003),
        router_q,
    )
    # Let both real collision hulls settle on the authored Ground before the
    # Nikon receives a single initial velocity.  No later pose is scripted.
    for _ in range(PHYSICS_FPS // 3):
        p.stepSimulation()
    p.resetBaseVelocity(nikon, linearVelocity=(dx * launch_speed, dy * launch_speed, 0.0))

    report = base_report(layout, "nikon_hits_router")
    report["launch_speed_m_s"] = launch_speed
    report["trajectories"] = {"nikon": [], "router": []}
    report["actor_target_contacts"] = []
    report["ground_contact_frames"] = {"nikon": 0, "router": 0}
    for frame in range(1, FRAME_COUNT + 1):
        report["trajectories"]["nikon"].append(state(nikon, frame))
        report["trajectories"]["router"].append(state(router, frame))
        frame_ground_names = set()
        for substep in range(SUBSTEPS):
            p.stepSimulation()
            contacts = p.getContactPoints(bodyA=nikon, bodyB=router)
            if contacts and len(report["actor_target_contacts"]) < 100:
                strongest = max(contacts, key=lambda item: item[9])
                report["actor_target_contacts"].append(
                    contact_row(strongest, frame, substep)
                )
            if p.getContactPoints(bodyA=nikon, bodyB=ground):
                frame_ground_names.add("nikon")
            if p.getContactPoints(bodyA=router, bodyB=ground):
                frame_ground_names.add("router")
        for name in frame_ground_names:
            report["ground_contact_frames"][name] += 1

    router_positions = [row["position"] for row in report["trajectories"]["router"]]
    nikon_positions = [row["position"] for row in report["trajectories"]["nikon"]]
    router_displacement = horizontal_distance(router_positions[0], router_positions[-1])
    nikon_displacement = horizontal_distance(nikon_positions[0], nikon_positions[-1])
    report["validation"] = {
        "actor_target_contact_count": len(report["actor_target_contacts"]),
        "first_contact_frame": (
            report["actor_target_contacts"][0]["frame"]
            if report["actor_target_contacts"]
            else None
        ),
        "max_contact_force_n": max(
            (row["normal_force"] for row in report["actor_target_contacts"]),
            default=0.0,
        ),
        "router_horizontal_displacement_m": router_displacement,
        "nikon_horizontal_displacement_m": nikon_displacement,
        "router_peak_speed_m_s": max(
            math.hypot(*row["linear_velocity"][:2])
            for row in report["trajectories"]["router"]
        ),
        "ground_contact_frames": report["ground_contact_frames"],
    }
    report["validation"]["passed"] = bool(
        report["validation"]["actor_target_contact_count"] > 0
        and router_displacement >= 0.05
        and report["ground_contact_frames"]["nikon"] >= FRAME_COUNT // 2
        and report["ground_contact_frames"]["router"] >= FRAME_COUNT // 2
    )
    return report


def main() -> None:
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = p.connect(p.DIRECT)
    if client < 0:
        raise RuntimeError("PyBullet DIRECT connection failed")
    try:
        drop = run_drop(layout)
        (OUTPUT_DIR / "new_rigid_objects_drop.json").write_text(
            json.dumps(drop, indent=2), encoding="utf-8"
        )
        if not drop["validation"]["passed"]:
            raise RuntimeError("Rigid-object drop validation failed: " + json.dumps(drop["validation"]))

        interaction = None
        for speed in (1.4, 1.8, 2.2, 2.6):
            candidate = run_interaction_attempt(layout, speed)
            if candidate["validation"]["passed"]:
                interaction = candidate
                break
            interaction = candidate
        (OUTPUT_DIR / "nikon_hits_router.json").write_text(
            json.dumps(interaction, indent=2), encoding="utf-8"
        )
        if not interaction["validation"]["passed"]:
            raise RuntimeError(
                "Actor-target collision validation failed after sweep: "
                + json.dumps(interaction["validation"])
            )
        print("DROP_VALIDATION=" + json.dumps(drop["validation"], sort_keys=True))
        print(
            "INTERACTION_VALIDATION="
            + json.dumps(interaction["validation"], sort_keys=True)
        )
        print("V5_REAL_PYBULLET_DONE")
    finally:
        p.disconnect()


main()
