"""Import a complete baked ReplicaCAD scene and render several viewpoints."""

from pathlib import Path

import bpy
from mathutils import Vector


SOURCE = Path(
    r"D:\blender\data_found_online\ReplicaCAD_BakedLighting_full\stages\Baked_sc0_staging_00.glb"
)
OUTPUT_DIR = Path(r"D:\workspace\project1_database\blender_previews\baked_sc0_views")
BLEND_OUTPUT = Path(r"D:\workspace\project1_database\blender_previews\ReplicaCAD_Baked_sc0_COLOR_FIXED.blend")
DECODED_TEXTURE = Path(
    r"D:\workspace\project1_database\blender_previews\replica_texture_work\Baked_sc0_Image_0_unpacked_rgba_RGBA32_0_0000.png"
)


def point_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(SOURCE))

meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

# ReplicaCAD's baked GLBs use the legacy GOOGLE_texture_basis extension and
# image/x-basis. Blender imports the geometry but cannot decode that texture,
# so attach the officially decoded PNG atlas and pack it into the .blend.
decoded_image = bpy.data.images.load(str(DECODED_TEXTURE), check_existing=False)
decoded_image.name = "ReplicaCAD_Baked_sc0_Color_Atlas"
decoded_image.pack()
for material in bpy.data.materials:
    if not material.use_nodes or not material.node_tree:
        continue
    image_nodes = [node for node in material.node_tree.nodes if node.type == "TEX_IMAGE"]
    for image_node in image_nodes:
        image_node.image = decoded_image

for obj in meshes:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.rigidbody.object_add()
    obj.rigid_body.type = "PASSIVE"
    obj.rigid_body.collision_shape = "MESH"
    obj.rigid_body.friction = 0.8
    obj.rigid_body.restitution = 0.0
    obj["source_asset"] = str(SOURCE)
    obj["scene_role"] = "complete_baked_static_scene"

bpy.ops.object.camera_add()
camera = bpy.context.object
camera.name = "VIEW_CAMERA"
camera.data.lens = 48
camera.data.clip_start = 0.02
camera.data.clip_end = 100.0
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type="SUN", location=(0, 0, 8))
sun = bpy.context.object
sun.name = "Soft_Sun"
sun.rotation_euler = (0.5, -0.35, 0.5)
sun.data.energy = 1.5

bpy.ops.object.light_add(type="AREA", location=(1.0, -2.0, 2.8))
area = bpy.context.object
area.name = "Interior_Fill"
area.data.energy = 600
area.data.shape = "DISK"
area.data.size = 4.0
point_at(area, (1.0, -2.0, 0.8))

scene = bpy.context.scene
scene.name = "ReplicaCAD Baked sc0 complete color"
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 720
scene.render.resolution_y = 540
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.world.color = (0.12, 0.12, 0.12)
scene["source_glb"] = str(SOURCE)
scene["note"] = "Complete baked ReplicaCAD indoor scene; colors and object layout come directly from one official GLB."

views = [
    ("top", (1.0, -1.8, 13.0), (1.0, -1.8, 0.0), 52),
    ("living_a", (2.0, -4.8, 1.55), (1.5, -0.8, 1.2), 58),
    ("living_b", (3.4, -0.8, 1.55), (0.0, -2.0, 1.15), 56),
    ("hall", (-1.2, 2.7, 1.55), (0.7, -1.5, 1.2), 58),
    ("reverse", (0.5, -0.2, 1.55), (1.5, -6.0, 1.15), 58),
]

for name, location, target, lens in views:
    camera.data.type = "PERSP"
    camera.data.lens = lens
    camera.location = location
    point_at(camera, target)
    scene.render.filepath = str(OUTPUT_DIR / f"{name}.png")
    bpy.ops.render.render(write_still=True)

# Save with the clearest indoor viewpoint selected.
camera.location = (2.0, -4.8, 1.55)
camera.data.lens = 58
point_at(camera, (1.5, -0.8, 1.2))

for screen in bpy.data.screens:
    for screen_area in screen.areas:
        if screen_area.type == "VIEW_3D":
            space = screen_area.spaces.active
            space.shading.type = "MATERIAL"
            space.region_3d.view_perspective = "CAMERA"

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_OUTPUT), check_existing=False)
print(
    "BAKED_SCENE_READY",
    str(BLEND_OUTPUT),
    "meshes",
    len(meshes),
    "materials",
    len(bpy.data.materials),
    "images",
    len(bpy.data.images),
)
