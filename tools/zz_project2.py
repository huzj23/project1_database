"""Project the elephant visual under candidate orientations; compare with mask.

No clean() between hypotheses: instead re-transform mesh data and reuse objects.
"""
import bpy, sys, math
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

SRC = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj"
CAM_POS = (1.194, -0.815, 1.3634)
LOOK_AT = (0.4140, 0.1750, 0.8084)
FOCAL, SENSOR, RES = 50.0, 36.0, (1920, 1080)
OBJ_POS = (0.21878514997792797, 0.042367839014833875, 0.854059)

# start from an empty scene
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

cam_data = bpy.data.cameras.new("cam"); cam_data.lens = FOCAL
cam_data.sensor_width = SENSOR; cam_data.sensor_fit = "AUTO"
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = CAM_POS
d = Vector(LOOK_AT) - Vector(CAM_POS)
cam.rotation_mode = "QUATERNION"
cam.rotation_quaternion = d.to_track_quat("-Z", "Y")
sc = bpy.context.scene
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.resolution_percentage = 100

bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False)
o = [x for x in bpy.context.scene.objects if x.type == "MESH"][0]
o.location = OBJ_POS

def project(label):
    bpy.context.view_layer.update()
    xs, ys = [], []
    for v in o.data.vertices:
        p = o.matrix_world @ v.co
        co = world_to_camera_view(sc, cam, p)
        xs.append(co.x * RES[0]); ys.append((1.0 - co.y) * RES[1])
    print(f"  {label}: x[{min(xs):.1f},{max(xs):.1f}] y[{min(ys):.1f},{max(ys):.1f}] "
          f"w={max(xs)-min(xs):.1f} h={max(ys)-min(ys):.1f}")

print("=== hypotheses (screen bbox; mask v2 bbox is the elephant) ===")
# A: object rotation = identity -> mesh data in raw file frame
o.rotation_mode = "QUATERNION"; o.rotation_quaternion = (1, 0, 0, 0)
project("A identity rot, raw-frame data")

# B: object rotation = +90 X (the importer's own rotation, left in place)
o.rotation_mode = "XYZ"; o.rotation_euler = (math.radians(90), 0, 0)
project("B +90X object rot   ")

# C: mesh data rotated -90 X, object identity  (this is what
#    visual_transform.x_rotation_degrees = -90 would do)
o.rotation_euler = (0, 0, 0)
o.data.transform(Matrix.Rotation(math.radians(-90), 4, "X")); o.data.update()
project("C mesh -90X identity ")

# D: mesh data rotated +90 X, object identity
o.data.transform(Matrix.Rotation(math.radians(180), 4, "X")); o.data.update()
project("D mesh +90X identity ")
