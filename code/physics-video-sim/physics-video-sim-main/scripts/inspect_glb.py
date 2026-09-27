"""Print combined world-space mesh bounds for one GLB (Blender helper)."""

from __future__ import annotations

import sys

import bpy
import numpy as np


path = sys.argv[sys.argv.index("--") + 1]
if "bool" not in np.__dict__:
    np.bool = np.bool_  # type: ignore[attr-defined]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=path)
vertices = [
    obj.matrix_world @ vertex.co
    for obj in bpy.context.scene.objects
    if obj.type == "MESH"
    for vertex in obj.data.vertices
]
lower = tuple(min(vertex[axis] for vertex in vertices) for axis in range(3))
upper = tuple(max(vertex[axis] for vertex in vertices) for axis in range(3))
print(f"GLB_BOUNDS path={path} min={lower} max={upper}")
