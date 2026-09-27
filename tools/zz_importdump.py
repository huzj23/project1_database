import bpy, sys, math
from mathutils import Vector

SRC = sys.argv[sys.argv.index("--") + 1]

def clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

def dump(label):
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    o = objs[0]
    print(f"--- {label}")
    print(f"    n_mesh_objs={len(objs)}")
    print(f"    object.dimensions   = {[round(v,6) for v in o.dimensions]}")
    print(f"    rotation_euler(deg) = {[round(math.degrees(v),3) for v in o.rotation_euler]}")
    print(f"    rotation_mode       = {o.rotation_mode}")
    print(f"    scale               = {[round(v,6) for v in o.scale]}")
    print(f"    location            = {[round(v,6) for v in o.location]}")
    print(f"    matrix_world        = {[[round(x,4) for x in row] for row in o.matrix_world]}")
    lo = [1e18]*3; hi = [-1e18]*3
    for v in o.data.vertices:
        p = o.matrix_world @ v.co
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
    print(f"    world bbox min      = {[round(v,6) for v in lo]}")
    print(f"    world bbox max      = {[round(v,6) for v in hi]}")
    print(f"    world dims          = {[round(hi[i]-lo[i],6) for i in range(3)]}")
    lo2 = [1e18]*3; hi2 = [-1e18]*3
    for v in o.data.vertices:
        for i in range(3):
            lo2[i] = min(lo2[i], v.co[i]); hi2[i] = max(hi2[i], v.co[i])
    print(f"    MESH-DATA bbox min  = {[round(v,6) for v in lo2]}")
    print(f"    MESH-DATA bbox max  = {[round(v,6) for v in hi2]}")
    print(f"    MESH-DATA dims      = {[round(hi2[i]-lo2[i],6) for i in range(3)]}")

print("########## DEFAULT IMPORT ##########")
clean(); bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False); dump("default")

print("########## Z-UP IMPORT (axis_forward=Y, axis_up=Z) ##########")
clean(); bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False,
                                  axis_forward="Y", axis_up="Z"); dump("zup")

print("########## DEFAULT IMPORT + data.transform(Rot X, angle) ##########")
for ang in (-90.0, 90.0):
    clean(); bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False)
    o = [x for x in bpy.context.scene.objects if x.type == "MESH"][0]
    from mathutils import Matrix
    o.data.transform(Matrix.Rotation(math.radians(ang), 4, "X")); o.data.update()
    dump(f"default + x_rotation_degrees={ang}")
