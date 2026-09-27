"""Probe visible, upward-facing surfaces in the unmodified Cozy Kitchen scene.

Run only through Blender.  The script casts camera rays at a regular image-space
grid and records the first real scene surface hit by each ray.  No geometry,
light, camera, or world datablock is created or modified.
"""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector


OUTPUT = Path("/data/raw/huzijian/project1_database/tmp/v5_cozy_view_probe.json")


def camera_ray(camera: bpy.types.Object, u: float, v: float) -> tuple[Vector, Vector]:
    """Return a world-space ray through normalized camera coordinates."""
    frame = camera.data.view_frame(scene=bpy.context.scene)
    # Blender returns near-frame corners in clockwise order:
    # bottom-right, top-right, top-left, bottom-left.
    bottom = frame[3].lerp(frame[0], u)
    top = frame[2].lerp(frame[1], u)
    point = bottom.lerp(top, v)
    origin = camera.matrix_world.translation.copy()
    world_point = camera.matrix_world @ point
    return origin, (world_point - origin).normalized()


def main() -> None:
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("Cozy Kitchen has no active authored camera")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hits = []
    for v in (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
        for u in (0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85):
            origin, direction = camera_ray(camera, u, v)
            ok, location, normal, face_index, obj, _matrix = scene.ray_cast(
                depsgraph, origin, direction, distance=100.0
            )
            row = {"u": u, "v": v, "hit": bool(ok)}
            if ok:
                row.update(
                    {
                        "object": obj.name,
                        "location": [float(value) for value in location],
                        "normal": [float(value) for value in normal],
                        "face_index": int(face_index),
                        "upward": float(normal.z) >= 0.90,
                        "distance": float((location - origin).length),
                    }
                )
            hits.append(row)

    camera_forward = -(camera.matrix_world.to_quaternion() @ Vector((0, 0, 1)))
    report = {
        "blend_file": bpy.data.filepath,
        "camera": camera.name,
        "camera_location": [float(value) for value in camera.matrix_world.translation],
        "camera_quaternion_wxyz": [
            float(camera.matrix_world.to_quaternion().w),
            float(camera.matrix_world.to_quaternion().x),
            float(camera.matrix_world.to_quaternion().y),
            float(camera.matrix_world.to_quaternion().z),
        ],
        "camera_forward": [float(value) for value in camera_forward],
        "lens_mm": float(camera.data.lens),
        "hits": hits,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COZY_VIEW_PROBE=" + json.dumps(report, separators=(",", ":")))


main()
