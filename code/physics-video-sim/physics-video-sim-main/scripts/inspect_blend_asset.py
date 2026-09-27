"""Inspect a Blender asset without modifying or saving the source file."""

from __future__ import annotations

import json
import os
from collections import Counter

import bpy
from mathutils import Vector


meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
corners = [
    obj.matrix_world @ Vector(corner)
    for obj in meshes
    for corner in obj.bound_box
]
lower = [min(vertex[axis] for vertex in corners) for axis in range(3)]
upper = [max(vertex[axis] for vertex in corners) for axis in range(3)]
materials = {
    material.name
    for obj in meshes
    for material in obj.data.materials
    if material is not None
}
negative_determinant_meshes = [
    obj.name for obj in meshes if obj.matrix_world.to_3x3().determinant() < 0
]
material_node_types = Counter(
    node.type
    for material in bpy.data.materials
    if material.use_nodes and material.node_tree is not None
    for node in material.node_tree.nodes
)
images = [image for image in bpy.data.images if image.source == "FILE"]
missing_images = [
    {"name": image.name, "path": bpy.path.abspath(image.filepath)}
    for image in images
    if not image.packed_file and not os.path.isfile(bpy.path.abspath(image.filepath))
]
horizontal_candidates = []
for obj in meshes:
    object_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    object_lower = [min(vertex[axis] for vertex in object_corners) for axis in range(3)]
    object_upper = [max(vertex[axis] for vertex in object_corners) for axis in range(3)]
    dimensions = [object_upper[index] - object_lower[index] for index in range(3)]
    horizontal_candidates.append(
        {
            "name": obj.name,
            "bounds": {"min": object_lower, "max": object_upper},
            "dimensions": dimensions,
            "horizontal_score": dimensions[0]
            * dimensions[1]
            / max(dimensions[2], 0.01),
        }
    )
horizontal_candidates.sort(key=lambda item: item["horizontal_score"], reverse=True)
furniture_surface_candidates = [
    item
    for item in horizontal_candidates
    if any(
        token in item["name"].lower()
        for token in ("desk", "table", "bureau", "pupil", "teacher")
    )
]
elevated_surface_candidates = [
    item
    for item in horizontal_candidates
    if 0.5 <= item["bounds"]["max"][2] <= 1.5
    and item["dimensions"][2] <= 0.2
    and item["dimensions"][0] * item["dimensions"][1] >= 0.1
]
report = {
    "mesh_objects": len(meshes),
    "vertices": sum(len(obj.data.vertices) for obj in meshes),
    "triangles": sum(len(obj.data.loop_triangles) for obj in meshes),
    "materials": len(materials),
    "material_node_types": dict(sorted(material_node_types.items())),
    "backface_culling_materials": [
        material.name for material in bpy.data.materials if material.use_backface_culling
    ],
    "file_images": len(images),
    "packed_images": sum(bool(image.packed_file) for image in images),
    "missing_images": missing_images,
    "lights": [
        {
            "name": obj.name,
            "type": obj.data.type,
            "position": list(obj.location),
            "energy": obj.data.energy,
        }
        for obj in bpy.context.scene.objects
        if obj.type == "LIGHT"
    ],
    "bounds": {"min": lower, "max": upper},
    "dimensions": [upper[index] - lower[index] for index in range(3)],
    "world_uses_nodes": bool(
        bpy.context.scene.world and bpy.context.scene.world.use_nodes
    ),
    "gltf_node_groups": [
        {
            "name": node_group.name,
            "inputs": len(node_group.inputs),
            "outputs": len(node_group.outputs),
        }
        for node_group in bpy.data.node_groups
        if "gltf" in node_group.name.lower()
    ],
    "negative_determinant_mesh_count": len(negative_determinant_meshes),
    "negative_determinant_meshes": negative_determinant_meshes[:100],
    "basketball_court_objects": [
        {
            "name": obj.name,
            "determinant": obj.matrix_world.to_3x3().determinant(),
            "polygons": len(obj.data.polygons),
            "materials": [
                material.name
                for material in obj.data.materials
                if material is not None
            ],
            "uv_layers": [layer.name for layer in obj.data.uv_layers],
            "hide_render": obj.hide_render,
        }
        for obj in meshes
        if "basketball_court" in obj.name.lower()
    ],
    "horizontal_candidates": horizontal_candidates[:30],
    "furniture_surface_candidates": furniture_surface_candidates,
    "elevated_surface_candidates": elevated_surface_candidates,
}
print("BLEND_ASSET_REPORT=" + json.dumps(report, ensure_ascii=False))
