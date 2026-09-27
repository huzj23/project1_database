"""Replay validated V5 PyBullet trajectories in the authored Cozy Kitchen.

This script does not run Blender rigid-body physics and never invents motion.
It imports the two GSO visual meshes, keyframes the recorded PyBullet states,
and reuses the source scene's camera object, 13 lights, World, and all geometry.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector


ROOT = Path("/data/raw/huzijian/project1_database")
PHYSICS_DIR = ROOT / "outcomes/v5/physics"
OUTPUT_ROOT = ROOT / "outcomes/v5"


def args_after_double_dash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("drop", "interaction"), required=True)
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args(args_after_double_dash())


def import_obj_parent(name: str, filepath: str) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.obj(filepath=filepath, use_image_search=True)
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"OBJ import produced no mesh: {filepath}")
    parent = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(parent)
    for obj in imported:
        world = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = world
        obj.hide_render = False
    return parent


def keyframe_trajectory(parent: bpy.types.Object, rows: list[dict]) -> None:
    parent.rotation_mode = "QUATERNION"
    for row in rows:
        frame = int(row["frame"])
        parent.location = row["position"]
        qx, qy, qz, qw = row["quaternion_xyzw"]
        parent.rotation_quaternion = Quaternion((qw, qx, qy, qz))
        parent.keyframe_insert(data_path="location", frame=frame)
        parent.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    if parent.animation_data and parent.animation_data.action:
        for curve in parent.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"


def line_of_sight(scene, depsgraph, origin: Vector, points: list[Vector]) -> int:
    visible = 0
    for point in points:
        ray = point - origin
        distance = ray.length
        if distance <= 1e-6:
            continue
        hit, location, _normal, _face, _obj, _matrix = scene.ray_cast(
            depsgraph, origin, ray.normalized(), distance=max(0.0, distance - 0.035)
        )
        if not hit or (location - origin).length >= distance - 0.05:
            visible += 1
    return visible


def choose_camera(scene, camera, data: dict, scenario: str) -> dict:
    layout = data["layout"]
    surface_z = float(layout["surface_z"])
    trajectories = data["trajectories"]
    all_positions = [
        Vector(row["position"])
        for name in ("nikon", "router")
        for row in trajectories[name]
    ]
    xmin = min(point.x for point in all_positions)
    xmax = max(point.x for point in all_positions)
    ymin = min(point.y for point in all_positions)
    ymax = max(point.y for point in all_positions)
    zmin = min(point.z for point in all_positions)
    zmax = max(point.z for point in all_positions)
    focus = Vector(((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0))
    if scenario == "interaction":
        focus.z = max(focus.z, surface_z + 0.13)
    else:
        focus.z = max(focus.z, surface_z + 0.27)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    aim_points = [
        Vector((xmin, ymin, surface_z + 0.10)),
        Vector((xmax, ymax, surface_z + 0.14)),
        Vector((focus.x, focus.y, focus.z)),
    ]
    candidates = []
    # The chosen Ground lane was verified by top-down first-hit rays.  Keep the
    # reused authored camera above that clear column so room walls cannot fill
    # the foreground, then introduce a modest horizontal offset for depth.
    offsets = (
        (0.00, -0.34, 0.76),
        (0.00, 0.34, 0.76),
        (-0.24, -0.24, 0.76),
        (0.24, -0.24, 0.76),
        (-0.24, 0.24, 0.76),
        (0.24, 0.24, 0.76),
        (0.00, 0.00, 0.94),
    )
    for index, offset in enumerate(offsets):
        origin = focus + Vector(offset)
        visible = line_of_sight(scene, depsgraph, origin, aim_points)
        candidates.append(
            {
                "origin": origin,
                "visible_points": visible,
                "radius": float((origin - focus).length),
                "angle_index": index,
                "score": visible * 100.0 - index * 0.1,
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = candidates[0]
    camera.animation_data_clear()
    camera.constraints.clear()
    camera.location = selected["origin"]
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = (focus - camera.location).to_track_quat("-Z", "Y")
    # The splash scene's authored wide camera is orthographic (appropriate for
    # the full diorama, but it ignores focal length and keeps small actors tiny).
    # Reuse that same camera datablock as a perspective close-up for the physics
    # shots; no second camera is inserted into the scene.
    camera.data.type = "PERSP"
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.sensor_width = 36.0
    camera.data.lens = 42.0 if scenario == "interaction" else 32.0
    camera.data.dof.use_dof = False
    scene.camera = camera

    # Project every recorded center as a deterministic framing gate.  Lower the
    # focal length if necessary, but never move or scale an object.
    for lens in (camera.data.lens, 42.0, 36.0, 32.0):
        camera.data.lens = lens
        projected = [world_to_camera_view(scene, camera, point) for point in all_positions]
        if all(
            0.05 <= point.x <= 0.95
            and 0.05 <= point.y <= 0.95
            and point.z > 0.0
            for point in projected
        ):
            break
    projected = [world_to_camera_view(scene, camera, point) for point in all_positions]
    if not all(
        0.02 <= point.x <= 0.98
        and 0.02 <= point.y <= 0.98
        and point.z > 0.0
        for point in projected
    ):
        raise RuntimeError("Recorded rigid-body centers do not fit the camera frame")
    return {
        "source_camera_object": camera.name,
        "position": [float(value) for value in camera.location],
        "focus": [float(value) for value in focus],
        "lens_mm": float(camera.data.lens),
        "camera_type": camera.data.type,
        "line_of_sight_points": int(selected["visible_points"]),
        "center_ndc_bounds": {
            "xmin": min(float(point.x) for point in projected),
            "xmax": max(float(point.x) for point in projected),
            "ymin": min(float(point.y) for point in projected),
            "ymax": max(float(point.y) for point in projected),
        },
    }


def main() -> None:
    args = parse_args()
    scenario_file = (
        PHYSICS_DIR / "new_rigid_objects_drop.json"
        if args.scenario == "drop"
        else PHYSICS_DIR / "nikon_hits_router.json"
    )
    data = json.loads(scenario_file.read_text(encoding="utf-8"))
    if not data["validation"]["passed"]:
        raise RuntimeError(f"Refusing to render failed physics: {scenario_file}")

    scene = bpy.context.scene
    authored_lights = [obj for obj in scene.objects if obj.type == "LIGHT"]
    if len(authored_lights) != 13 or scene.world is None:
        raise RuntimeError(
            f"Authored lighting contract failed: lights={len(authored_lights)}, world={scene.world}"
        )
    camera = scene.camera
    if camera is None:
        raise RuntimeError("Authored camera is missing")

    camera_report = choose_camera(scene, camera, data, args.scenario)
    nikon = import_obj_parent("V5_Nikon_Actor", data["objects"]["nikon"]["visual_obj"])
    router = import_obj_parent("V5_Netgear_Target", data["objects"]["router"]["visual_obj"])
    keyframe_trajectory(nikon, data["trajectories"]["nikon"])
    keyframe_trajectory(router, data["trajectories"]["router"])

    clip_name = (
        "new_rigid_objects_drop" if args.scenario == "drop" else "nikon_hits_router_interaction"
    )
    output_dir = OUTPUT_ROOT / clip_name
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    scene.frame_start = 1
    scene.frame_end = 48
    scene.render.fps = 16
    scene.render.fps_base = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.filepath = str(frames_dir / "frame_####.png")

    render_report = {
        "scenario": args.scenario,
        "physics_json": str(scenario_file),
        "physics_validation": data["validation"],
        "camera": camera_report,
        "authored_lights": len(authored_lights),
        "authored_world": scene.world.name,
        "added_geometry": [data["objects"]["nikon"]["asset_id"], data["objects"]["router"]["asset_id"]],
        "added_lights": 0,
        "added_ground": 0,
        "source_scene_geometry_removed": 0,
        "render_engine": scene.render.engine,
        "resolution": [960, 540],
        "fps": 16,
        "frame_count": 48,
    }
    (output_dir / "render_report.json").write_text(
        json.dumps(render_report, indent=2), encoding="utf-8"
    )
    print("RIGID_RENDER_CONTRACT=" + json.dumps(render_report, separators=(",", ":")))
    if args.preview:
        preview_frame = 7 if args.scenario == "drop" else 4
        scene.frame_set(preview_frame)
        scene.render.filepath = str(output_dir / "preview.png")
        bpy.ops.render.render(write_still=True)
        print("V5_RIGID_PREVIEW_DONE")
    else:
        bpy.ops.render.render(animation=True)
        print("V5_RIGID_RENDER_DONE")


main()
