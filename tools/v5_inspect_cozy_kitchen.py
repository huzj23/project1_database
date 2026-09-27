"""Audit the unmodified Blender Cozy Kitchen source scene."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import bpy
from mathutils import Vector


OUTPUT = Path(
    "/data/raw/huzijian/project1_database/tmp/v5_cozy_kitchen_audit.json"
)


def world_bounds(obj: bpy.types.Object) -> tuple[list[float], list[float]]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = [min(point[axis] for point in points) for axis in range(3)]
    upper = [max(point[axis] for point in points) for axis in range(3)]
    return lower, upper


def main() -> None:
    object_types = Counter(obj.type for obj in bpy.data.objects)
    mesh_rows = []
    horizontal_area_by_z: defaultdict[float, float] = defaultdict(float)
    horizontal_faces_by_z: defaultdict[float, int] = defaultdict(int)

    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        lower, upper = world_bounds(obj)
        mesh_rows.append(
            {
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "bounds_min": lower,
                "bounds_max": upper,
            }
        )
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        scale_area = abs(float(obj.scale.x * obj.scale.y))
        for polygon in obj.data.polygons:
            normal = (normal_matrix @ polygon.normal).normalized()
            if normal.z < 0.985:
                continue
            center = obj.matrix_world @ polygon.center
            level = round(float(center.z), 3)
            horizontal_area_by_z[level] += float(polygon.area) * scale_area
            horizontal_faces_by_z[level] += 1

    all_mesh_bounds = [row for row in mesh_rows if row["vertices"] > 0]
    scene_bounds = None
    if all_mesh_bounds:
        scene_bounds = {
            "min": [
                min(row["bounds_min"][axis] for row in all_mesh_bounds)
                for axis in range(3)
            ],
            "max": [
                max(row["bounds_max"][axis] for row in all_mesh_bounds)
                for axis in range(3)
            ],
        }

    support_levels = sorted(
        (
            {
                "z": level,
                "area_approx": area,
                "face_count": horizontal_faces_by_z[level],
            }
            for level, area in horizontal_area_by_z.items()
            if area >= 0.05
        ),
        key=lambda row: row["area_approx"],
        reverse=True,
    )[:30]

    report = {
        "blend_file": bpy.data.filepath,
        "blender_version": list(bpy.app.version),
        "object_type_counts": dict(sorted(object_types.items())),
        "scene_unit_system": bpy.context.scene.unit_settings.system,
        "scene_unit_scale": bpy.context.scene.unit_settings.scale_length,
        "render_engine": bpy.context.scene.render.engine,
        "frame_start": bpy.context.scene.frame_start,
        "frame_end": bpy.context.scene.frame_end,
        "scene_bounds": scene_bounds,
        "active_camera": (
            bpy.context.scene.camera.name if bpy.context.scene.camera else None
        ),
        "cameras": [
            {
                "name": obj.name,
                "location": list(obj.location),
                "lens_mm": float(obj.data.lens),
            }
            for obj in bpy.data.objects
            if obj.type == "CAMERA"
        ],
        "lights": [
            {
                "name": obj.name,
                "type": obj.data.type,
                "energy": float(obj.data.energy),
                "location": list(obj.location),
            }
            for obj in bpy.data.objects
            if obj.type == "LIGHT"
        ],
        "world": bpy.context.scene.world.name if bpy.context.scene.world else None,
        "world_uses_nodes": bool(
            bpy.context.scene.world and bpy.context.scene.world.use_nodes
        ),
        "images": [
            {
                "name": image.name,
                "filepath": image.filepath,
                "packed": image.packed_file is not None,
            }
            for image in bpy.data.images
        ],
        "support_level_candidates": support_levels,
        "largest_meshes": sorted(
            mesh_rows, key=lambda row: row["polygons"], reverse=True
        )[:40],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COZY_AUDIT=" + json.dumps(report, separators=(",", ":")))


main()
