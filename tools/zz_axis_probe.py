import bpy, sys
from mathutils import Vector

SRC = sys.argv[sys.argv.index("--") + 1]

def bounds(objs, label):
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    print(f"{label}: min=[{lo[0]:.6f},{lo[1]:.6f},{lo[2]:.6f}] "
          f"max=[{hi[0]:.6f},{hi[1]:.6f},{hi[2]:.6f}] "
          f"dim=[{hi[0]-lo[0]:.6f},{hi[1]-lo[1]:.6f},{hi[2]-lo[2]:.6f}]")

def clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

print("=== raw file AABB (parsed textually, no Blender) ===")
lo = [1e9]*3; hi = [-1e9]*3
for line in open(SRC):
    if line.startswith("v "):
        p = [float(x) for x in line.split()[1:4]]
        for i in range(3):
            lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
print(f"raw: min=[{lo[0]:.6f},{lo[1]:.6f},{lo[2]:.6f}] "
      f"max=[{hi[0]:.6f},{hi[1]:.6f},{hi[2]:.6f}] "
      f"dim=[{hi[0]-lo[0]:.6f},{hi[1]-lo[1]:.6f},{hi[2]-lo[2]:.6f}]")

print("=== import with DEFAULTS (what generate_collision_mesh.py does) ===")
clean()
bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False)
bounds([o for o in bpy.context.scene.objects if o.type == "MESH"], "default-import")

print("=== import with axis_forward=Y axis_up=Z (Z-up passthrough) ===")
clean()
bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False,
                         axis_forward="Y", axis_up="Z")
bounds([o for o in bpy.context.scene.objects if o.type == "MESH"], "zup-import")
