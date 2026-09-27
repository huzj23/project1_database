from pathlib import Path

import bpy
from mathutils import Vector


stage_root = Path(r"D:\blender\data_found_online\ReplicaCAD_BakedLighting_full\stages")
for index in range(4):
    path = stage_root / f"Baked_sc{index}_staging_00.glb"
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    mins = tuple(round(min(point[axis] for point in points), 2) for axis in range(3))
    maxs = tuple(round(max(point[axis] for point in points), 2) for axis in range(3))
    print(
        "SCENE_INFO",
        path.name,
        "meshes",
        len(meshes),
        "materials",
        len(bpy.data.materials),
        "images",
        len(bpy.data.images),
        "bounds",
        mins,
        maxs,
    )
