"""Minimal script executed inside Blender for local integration checks."""

from __future__ import annotations

import json
import sys

import bpy


def main() -> None:
    version = tuple(bpy.app.version)
    if version[:2] != (3, 6):
        raise RuntimeError(f"Expected Blender 3.6.x, got {bpy.app.version_string}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))

    cube = bpy.context.active_object
    if cube is None or cube.name != "Cube":
        raise RuntimeError("Failed to create the smoke-test cube")

    result = {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "python_version": sys.version.split()[0],
        "object": cube.name,
        "scene_object_count": len(bpy.context.scene.objects),
    }
    print("PHYSIM_BLENDER_SMOKE=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
