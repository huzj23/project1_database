import bpy, sys

# Verify the 4 structural rules for replicad_apartment/visual/scene.blend
path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=path)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print("MESH objects:", len(meshes))
for o in meshes:
    print(f"  name={o.name!r} verts={len(o.data.vertices)} "
          f"polys={len(o.data.polygons)}")

total_v = sum(len(o.data.vertices) for o in meshes)
print("total mesh vertices:", total_v)

# rule: exactly one mesh object named 'environment'
print("RULE single mesh named environment:",
      len(meshes) == 1 and meshes[0].name == "environment")

# rule: all images packed
imgs = list(bpy.data.images)
packed = [i for i in imgs if i.packed_file is not None]
print(f"images: {len(imgs)}  packed: {len(packed)}")
print("RULE all images packed:", len(imgs) == len(packed))

# rule: authored lights in collection 'environment_lighting'
coll = bpy.data.collections.get("environment_lighting")
print("collection 'environment_lighting' present:", coll is not None)
if coll:
    lights = [o for o in coll.objects if o.type == "LIGHT"]
    print(f"  lights in collection: {len(lights)}")
    print(f"  types: {sorted(set(l.data.type for l in lights))}")
    print("RULE 7 POINT lights:", len(lights) == 7 and
          all(l.data.type == "POINT" for l in lights))

# rule: World named 'environment_world'
worlds = [w.name for w in bpy.data.worlds]
print("worlds:", worlds)
print("RULE world 'environment_world':", "environment_world" in worlds)
print("scene.world:", bpy.context.scene.world.name if bpy.context.scene.world else None)
