"""Project the elephant visual under both candidate orientations using the
recorded camera, and print screen-space bboxes to compare with the mask."""
import bpy, sys, math
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

SRC = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj"

CAM_POS = (1.194, -0.815, 1.3634)
LOOK_AT = (0.4140, 0.1750, 0.8084)
FOCAL = 50.0
SENSOR = 36.0
RES = (1920, 1080)
# frame 0 actor position, identity quaternion
OBJ_POS = (0.21878514997792797, 0.042367839014833875, 0.854059)

def clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

# camera
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = FOCAL
cam_data.sensor_width = SENSOR
cam_data.sensor_fit = "AUTO"
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = CAM_POS
d = Vector(LOOK_AT) - Vector(CAM_POS)
cam.rotation_mode = "QUATERNION"
cam.rotation_quaternion = d.to_track_quat("-Z", "Y")
bpy.context.scene.camera = cam
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.resolution_percentage = 100

def project(objs, label):
    xs, ys = [], []
    for o in objs:
        for v in o.data.vertices:
            p = o.matrix_world @ v.co
            co = world_to_camera_view(sc, cam, p)
            xs.append(co.x * RES[0]); ys.append((1.0 - co.y) * RES[1])
    print(f"  {label}: screen x[{min(xs):.1f},{max(xs):.1f}] y[{min(ys):.1f},{max(ys):.1f}] "
          f"w={max(xs)-min(xs):.1f} h={max(ys)-min(ys):.1f} "
          f"cx={sum(xs)/len(xs):.1f} cy={sum(ys)/len(ys):.1f}")

print("=== hypothesis A: identity object rotation (mesh-data = raw file frame) ===")
clean()
bpy.ops.import_scene.obj(filepath=SRC, use_split_objects=False)
o = [x for x in bpy.context.scene.objects if x.type == "MESH"][0]
# force identity rotation: this is what happens when Kubric writes the sampled
# quaternion (identity here) onto the object after import.
o.rotation_mode = "QUATERNION"
o.rotation_quaternion = (1, 0, 0, 0)
o.location = OBJ_POS
bpy.context.view_layer.update()
project([o], "A raw-frame mesh, identity rot")

print("=== hypothesis B: object keeps the importer's +90deg X rotation ===")
o.rotation_mode = "XYZ"
o.rotation_euler = (math.radians(90), 0, 0)
bpy.context.view_layer.update()
project([o], "B +90X object rot")

print("=== hypothesis C: mesh-data rotated +90X, object identity ===")
o.rotation_euler = (0, 0, 0)
o.data.transform(Matrix.Rotation(math.radians(90), 4, "X"))
o.data.update()
bpy.context.view_layer.update()
project([o], "C mesh +90X, identity rot")

print("=== hypothesis D: mesh-data rotated -90X, object identity ===")
o.data.transform(Matrix.Rotation(math.radians(-180), 4, "X"))
o.data.update()
bpy.context.view_layer.update()
project([o], "D mesh -90X (net), identity rot")
