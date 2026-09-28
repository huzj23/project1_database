#!/usr/bin/env python3
"""Audit authored Blender scenes for rigid/soft-body interaction feasibility."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector


DEFAULT_WORKSPACE = Path("/data/raw/huzijian/project1_database")
SOFT_KEYWORDS = {
    "bed",
    "blanket",
    "carpet",
    "cloth",
    "couch",
    "curtain",
    "cushion",
    "fabric",
    "mattress",
    "pillow",
    "pouf",
    "rug",
    "sofa",
    "towel",
}
INTERACTION_KEYWORDS = {
    "bench",
    "board",
    "bottle",
    "box",
    "cabinet",
    "can",
    "carafe",
    "chair",
    "container",
    "counter",
    "crate",
    "cup",
    "decanter",
    "desk",
    "dish",
    "door",
    "drawer",
    "floor",
    "flask",
    "glass",
    "ground",
    "jar",
    "kitchen",
    "plate",
    "shelf",
    "stool",
    "table",
    "tool",
    "trash",
    "vase",
    "wine",
    "wood",
}
SUPPORT_KEYWORDS = {"bench", "counter", "desk", "shelf", "table"}


def keyword_hits(name: str, keywords: set[str]) -> list[str]:
    lowered = name.lower()
    return sorted(keyword for keyword in keywords if keyword in lowered)


def world_bounds(obj: bpy.types.Object) -> dict | None:
    if obj.type != "MESH" or not obj.bound_box:
        return None
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = [float(min(corner[axis] for corner in corners)) for axis in range(3)]
    upper = [float(max(corner[axis] for corner in corners)) for axis in range(3)]
    return {
        "min": lower,
        "max": upper,
        "dimensions": [upper[axis] - lower[axis] for axis in range(3)],
        "center": [(upper[axis] + lower[axis]) * 0.5 for axis in range(3)],
    }


def disconnected_component_count(obj: bpy.types.Object) -> int | None:
    """Count vertex-connected mesh islands without modifying the authored mesh."""
    if obj.type != "MESH":
        return None
    vertex_count = len(obj.data.vertices)
    if vertex_count == 0:
        return 0
    if vertex_count > 200_000:
        return None

    parents = list(range(vertex_count))

    def find(vertex: int) -> int:
        while parents[vertex] != vertex:
            parents[vertex] = parents[parents[vertex]]
            vertex = parents[vertex]
        return vertex

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for edge in obj.data.edges:
        union(int(edge.vertices[0]), int(edge.vertices[1]))
    return len({find(vertex) for vertex in range(vertex_count)})


def object_row(obj: bpy.types.Object, hits: list[str]) -> dict:
    return {
        "name": obj.name,
        "type": obj.type,
        "keyword_hits": hits,
        "collections": sorted(collection.name for collection in obj.users_collection),
        "hide_render": bool(obj.hide_render),
        "mesh": {
            "vertices": len(obj.data.vertices),
            "polygons": len(obj.data.polygons),
            "materials": len(obj.data.materials),
            "shape_keys": bool(obj.data.shape_keys),
            "disconnected_vertex_components": disconnected_component_count(obj),
        }
        if obj.type == "MESH"
        else None,
        "bounds_world": world_bounds(obj),
        "modifiers": [modifier.type for modifier in obj.modifiers],
        "rigid_body": {
            "type": obj.rigid_body.type,
            "collision_shape": obj.rigid_body.collision_shape,
            "mass": float(obj.rigid_body.mass),
            "friction": float(obj.rigid_body.friction),
            "restitution": float(obj.rigid_body.restitution),
        }
        if obj.rigid_body
        else None,
        "animation": bool(obj.animation_data and obj.animation_data.action),
    }


def support_relations(objects: list[bpy.types.Object]) -> list[dict]:
    mesh_objects = [obj for obj in objects if obj.type == "MESH" and not obj.hide_render]
    bounds = {obj.name: world_bounds(obj) for obj in mesh_objects}
    relations = []
    for support in mesh_objects:
        support_hits = keyword_hits(support.name, SUPPORT_KEYWORDS)
        support_bounds = bounds[support.name]
        if not support_hits or support_bounds is None:
            continue
        top_z = support_bounds["max"][2]
        occupants = []
        for candidate in mesh_objects:
            if candidate == support:
                continue
            candidate_bounds = bounds[candidate.name]
            if candidate_bounds is None:
                continue
            dimensions = candidate_bounds["dimensions"]
            if max(dimensions) > 1.0:
                continue
            center = candidate_bounds["center"]
            bottom_delta = candidate_bounds["min"][2] - top_z
            inside_xy = (
                support_bounds["min"][0] - 0.05
                <= center[0]
                <= support_bounds["max"][0] + 0.05
                and support_bounds["min"][1] - 0.05
                <= center[1]
                <= support_bounds["max"][1] + 0.05
            )
            if inside_xy and -0.03 <= bottom_delta <= 0.45:
                occupants.append(
                    {
                        "name": candidate.name,
                        "bottom_above_support_m": float(bottom_delta),
                        "bounds_world": candidate_bounds,
                        "vertices": len(candidate.data.vertices),
                        "polygons": len(candidate.data.polygons),
                    }
                )
        if occupants:
            relations.append(
                {
                    "support": support.name,
                    "support_keyword_hits": support_hits,
                    "support_bounds_world": support_bounds,
                    "possible_occupants": sorted(
                        occupants, key=lambda row: (row["bottom_above_support_m"], row["name"])
                    ),
                }
            )
    return relations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    args = parser.parse_args(os.sys.argv[os.sys.argv.index("--") + 1 :])

    workspace = Path(args.workspace).resolve()
    report_path = Path(args.report).resolve()
    if not str(report_path).startswith(str(workspace) + os.sep):
        raise RuntimeError(f"report path escaped workspace: {report_path}")

    objects = list(bpy.data.objects)
    modifiers = Counter(modifier.type for obj in objects for modifier in obj.modifiers)
    rigid_bodies = [obj for obj in objects if obj.rigid_body]
    soft_physics = [
        obj
        for obj in objects
        if any(modifier.type in {"SOFT_BODY", "CLOTH"} for modifier in obj.modifiers)
    ]
    collision_modifiers = [
        obj for obj in objects if any(modifier.type == "COLLISION" for modifier in obj.modifiers)
    ]

    soft_candidates = []
    interaction_candidates = []
    for obj in sorted(objects, key=lambda item: item.name.lower()):
        soft_hits = keyword_hits(obj.name, SOFT_KEYWORDS)
        interaction_hits = keyword_hits(obj.name, INTERACTION_KEYWORDS)
        if soft_hits:
            soft_candidates.append(object_row(obj, soft_hits))
        if interaction_hits:
            interaction_candidates.append(object_row(obj, interaction_hits))

    report = {
        "tag": args.tag,
        "source": str(Path(bpy.data.filepath).resolve()),
        "blender_runtime": bpy.app.version_string,
        "active_scene": bpy.context.scene.name,
        "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
        "object_type_counts": dict(sorted(Counter(obj.type for obj in objects).items())),
        "mesh_totals": {
            "vertices": sum(len(obj.data.vertices) for obj in objects if obj.type == "MESH"),
            "polygons": sum(len(obj.data.polygons) for obj in objects if obj.type == "MESH"),
        },
        "physics": {
            "rigid_body_world": bool(bpy.context.scene.rigidbody_world),
            "rigid_body_count": len(rigid_bodies),
            "active_rigid_body_count": sum(
                1 for obj in rigid_bodies if obj.rigid_body.type == "ACTIVE"
            ),
            "passive_rigid_body_count": sum(
                1 for obj in rigid_bodies if obj.rigid_body.type == "PASSIVE"
            ),
            "soft_or_cloth_modifier_count": len(soft_physics),
            "collision_modifier_count": len(collision_modifiers),
            "rigid_body_constraint_count": sum(
                1 for obj in objects if obj.rigid_body_constraint
            ),
            "modifier_type_counts": dict(sorted(modifiers.items())),
            "rigid_bodies": [object_row(obj, []) for obj in rigid_bodies],
            "soft_or_cloth_objects": [object_row(obj, []) for obj in soft_physics],
            "collision_modifier_objects": [obj.name for obj in collision_modifiers],
        },
        "soft_semantic_candidates": soft_candidates,
        "interaction_semantic_candidates": interaction_candidates,
        "possible_support_relations": support_relations(objects),
        "all_mesh_objects": [
            {
                "name": obj.name,
                "bounds_world": world_bounds(obj),
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "modifiers": [modifier.type for modifier in obj.modifiers],
                "collections": sorted(collection.name for collection in obj.users_collection),
            }
            for obj in sorted(objects, key=lambda item: item.name.lower())
            if obj.type == "MESH"
        ],
        "interpretation": {
            "soft_semantic_candidate": "name-based review candidate, not proof of soft-body setup",
            "physics_evidence": "only explicit Blender rigid-body/cloth/soft-body/collision data blocks are counted",
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"V54_SCENE_AUDIT tag={args.tag} objects={len(objects)} "
        f"rigid={len(rigid_bodies)} soft={len(soft_physics)} "
        f"semantic_soft={len(soft_candidates)} interaction={len(interaction_candidates)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
