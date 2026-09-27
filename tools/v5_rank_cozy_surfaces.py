"""Rank authored Cozy Kitchen horizontal meshes by usable area and camera view."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


OUTPUT = Path("/data/raw/huzijian/project1_database/tmp/v5_cozy_surface_rank.json")


def main() -> None:
    scene = bpy.context.scene
    camera = scene.camera
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rows = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render or obj.data is None:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            normal_matrix = evaluated.matrix_world.to_3x3().inverted().transposed()
            entries = []
            for polygon in mesh.polygons:
                normal = (normal_matrix @ polygon.normal).normalized()
                if normal.z < 0.985 or polygon.area < 1e-6:
                    continue
                center = evaluated.matrix_world @ polygon.center
                area = float(polygon.area)
                entries.append((area, center))
            if not entries:
                continue
            area = sum(item[0] for item in entries)
            center = sum((item[1] * item[0] for item in entries), Vector()) / area
            ndc = world_to_camera_view(scene, camera, center)
            rows.append(
                {
                    "object": obj.name,
                    "upward_area_local": area,
                    "upward_face_count": len(entries),
                    "weighted_center": [float(value) for value in center],
                    "camera_ndc": [float(ndc.x), float(ndc.y), float(ndc.z)],
                    "in_camera": bool(0.0 <= ndc.x <= 1.0 and 0.0 <= ndc.y <= 1.0 and ndc.z > 0.0),
                }
            )
        finally:
            evaluated.to_mesh_clear()
    rows.sort(key=lambda row: row["upward_area_local"], reverse=True)
    report = {"camera": camera.name, "surfaces": rows[:250]}
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SURFACE_RANK=" + json.dumps(report, separators=(",", ":")))


main()
