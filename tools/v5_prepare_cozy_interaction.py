"""Extract the authored Ground collision mesh and find a clear interaction lane.

The source blend is read-only.  The exported OBJ is the evaluated, world-space
mesh of the scene's own ``Ground`` object; it is not a replacement plane.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path("/data/raw/huzijian/project1_database")
OUTPUT = ROOT / "tmp/v5_cozy_interaction_layout.json"
COLLISION = ROOT / "models/backgrounds/cozy_kitchen/collision/Ground.obj"


def export_world_obj(obj: bpy.types.Object, path: Path) -> dict:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Evaluated world-space mesh from Cozy Kitchen Ground\n")
            handle.write("o Ground\n")
            for vertex in mesh.vertices:
                point = evaluated.matrix_world @ vertex.co
                handle.write(f"v {point.x:.9g} {point.y:.9g} {point.z:.9g}\n")
            triangle_count = 0
            mesh.calc_loop_triangles()
            for triangle in mesh.loop_triangles:
                indices = [index + 1 for index in triangle.vertices]
                handle.write("f " + " ".join(str(index) for index in indices) + "\n")
                triangle_count += 1
        points = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
        return {
            "vertices": len(points),
            "triangles": triangle_count,
            "bounds_min": [min(point[axis] for point in points) for axis in range(3)],
            "bounds_max": [max(point[axis] for point in points) for axis in range(3)],
        }
    finally:
        evaluated.to_mesh_clear()


def main() -> None:
    scene = bpy.context.scene
    camera = scene.camera
    ground = bpy.data.objects.get("Ground")
    if ground is None or ground.type != "MESH":
        raise RuntimeError("Authored Ground mesh was not found")
    collision_stats = export_world_obj(ground, COLLISION)
    xmin, ymin, _zmin = collision_stats["bounds_min"]
    xmax, ymax, zmax = collision_stats["bounds_max"]
    depsgraph = bpy.context.evaluated_depsgraph_get()

    cache: dict[tuple[int, int], tuple[bool, list[float] | None]] = {}

    def clear(x: float, y: float) -> tuple[bool, list[float] | None]:
        key = (round(x * 1000), round(y * 1000))
        if key in cache:
            return cache[key]
        ok, location, normal, _face, obj, _matrix = scene.ray_cast(
            depsgraph,
            Vector((x, y, zmax + 2.5)),
            Vector((0.0, 0.0, -1.0)),
            distance=5.0,
        )
        usable = bool(
            ok
            and getattr(getattr(obj, "original", obj), "name", "") == ground.name
            and normal.z >= 0.90
        )
        result = (usable, [float(value) for value in location] if ok else None)
        cache[key] = result
        return result

    candidates = []
    directions = [
        (1.0, 0.0),
        (0.0, 1.0),
        (math.sqrt(0.5), math.sqrt(0.5)),
        (math.sqrt(0.5), -math.sqrt(0.5)),
    ]
    margin = 0.12
    step = 0.05
    x = xmin + margin
    while x <= xmax - margin + 1e-9:
        y = ymin + margin
        while y <= ymax - margin + 1e-9:
            for dx, dy in directions:
                px, py = -dy, dx
                samples = []
                valid = True
                # 0.60 m clear lane, 0.18 m wide.  The router's long axis is
                # aligned with the lane, so its 0.072 m thickness fits across.
                for along_index in range(13):
                    along = along_index * 0.05
                    for lateral in (-0.09, -0.045, 0.0, 0.045, 0.09):
                        sx = x + dx * along + px * lateral
                        sy = y + dy * along + py * lateral
                        usable, hit = clear(sx, sy)
                        if not usable:
                            valid = False
                            break
                        samples.append(hit)
                    if not valid:
                        break
                heights = [sample[2] for sample in samples if sample is not None]
                if valid and max(heights) - min(heights) > 0.025:
                    valid = False
                if valid:
                    surface_z = sum(heights) / len(heights)
                    actor = Vector((x + dx * 0.05, y + dy * 0.05, surface_z))
                    target = Vector((x + dx * 0.35, y + dy * 0.35, surface_z))
                    ndc = world_to_camera_view(scene, camera, target)
                    center_penalty = math.hypot(target.x, target.y)
                    camera_penalty = math.hypot(ndc.x - 0.5, ndc.y - 0.35)
                    candidates.append(
                        {
                            "actor_xy": [actor.x, actor.y],
                            "target_xy": [target.x, target.y],
                            "direction_xy": [dx, dy],
                            "surface_z": surface_z,
                            "source_camera_ndc": [float(ndc.x), float(ndc.y), float(ndc.z)],
                            "score": center_penalty + camera_penalty * 0.35,
                        }
                    )
            y += step
        x += step
    if not candidates:
        raise RuntimeError("No 0.60m x 0.18m clear lane exists on authored Ground")
    candidates.sort(key=lambda item: item["score"])
    report = {
        "source_blend": bpy.data.filepath,
        "source_ground_object": ground.name,
        "collision_obj": str(COLLISION),
        "collision_stats": collision_stats,
        "clearance_contract": {
            "lane_length_m": 0.60,
            "lane_width_m": 0.18,
            "ray_first_hit_must_be": ground.name,
            "normal_z_min": 0.90,
        },
        "selected": candidates[0],
        "alternates": candidates[1:20],
        "candidate_count": len(candidates),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COZY_INTERACTION_LAYOUT=" + json.dumps(report, separators=(",", ":")))


main()
