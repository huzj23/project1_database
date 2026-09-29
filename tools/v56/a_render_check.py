"""a_render_check.py -- V5.6 visual confirmation for the Hidden Alley board pick.

Renders three low-cost Cycles CPU images so a human (or the parent agent) can
see the candidate boards:

  1. `overview.png`  -- full frame through the scene's own camera.
  2. `pile_crop.png` -- same camera, render border cropped to the region where
                        wooden_boards.001 sits.
  3. `can_scale.png` -- a purpose-built camera close-up of the leaning board
                        pile, with an untextured proxy cylinder of a real
                        beverage can (66 mm dia x 122 mm tall) placed on the
                        ground beside the boards purely as a scale reference.

The proxy can is created in memory only; the .blend is never saved, so the
scene file on disk is untouched.  Nothing is deleted.

Run:
  & '<blender.exe>' --background --factory-startup --python a_render_check.py -- \
        --blend <scene.blend> --outdir <dir> [--samples 24] [--width 720]
"""

import argparse
import json
import math
import os
import sys

import numpy as np

import bpy
from mathutils import Vector

CAN_DIA_M = 0.066
CAN_H_M = 0.122


def look_at(cam_obj, target):
    d = Vector(target) - cam_obj.location
    cam_obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--width", type=int, default=720)
    A = ap.parse_args(args)

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    os.makedirs(A.outdir, exist_ok=True)

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = A.samples
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 4
    sc.cycles.transparent_max_bounces = 4
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False

    info = {"blend": A.blend, "samples": A.samples, "renders": []}

    # ---------------- 1. overview ----------------
    sc.render.resolution_x = A.width
    sc.render.resolution_y = int(round(A.width * 9 / 16))
    sc.render.use_border = False
    sc.render.use_crop_to_border = False
    sc.render.filepath = os.path.join(A.outdir, "overview.png")
    bpy.ops.render.render(write_still=True)
    info["renders"].append({"file": sc.render.filepath,
                            "camera": sc.camera.name, "border": None})
    print("[a_render_check] wrote", sc.render.filepath, flush=True)

    # ---------------- 2. crop of the left third ----------------
    sc.render.use_border = True
    sc.render.use_crop_to_border = True
    sc.render.border_min_x = 0.13
    sc.render.border_max_x = 0.45
    sc.render.border_min_y = 0.05
    sc.render.border_max_y = 0.80
    sc.render.resolution_x = 640
    sc.render.resolution_y = 800
    sc.render.filepath = os.path.join(A.outdir, "pile_crop.png")
    bpy.ops.render.render(write_still=True)
    info["renders"].append({"file": sc.render.filepath,
                            "camera": sc.camera.name,
                            "border": [0.13, 0.05, 0.45, 0.80]})
    print("[a_render_check] wrote", sc.render.filepath, flush=True)
    sc.render.use_border = False
    sc.render.use_crop_to_border = False

    # ---------------- 3. close-up with a scale-reference can ----------------
    # ground level near the pile
    dg = bpy.context.evaluated_depsgraph_get()
    probe = sc.ray_cast(dg, Vector((-1.30, 1.10, 1.0)), Vector((0, 0, -1)))
    ground_z = float(probe[1][2]) if probe[0] else 0.0
    info["ground_z_under_pile"] = round(ground_z, 5)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=CAN_DIA_M / 2.0, depth=CAN_H_M,
        location=(-1.30, 1.10, ground_z + CAN_H_M / 2.0))
    can = bpy.context.active_object
    can.name = "can_scale_proxy"
    mat = bpy.data.materials.new("can_proxy_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.85, 0.15, 0.12, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.35
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.8
    can.data.materials.append(mat)

    cam_data = bpy.data.cameras.new("board_check_cam")
    cam_data.lens = 35.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 100.0
    cam = bpy.data.objects.new("board_check_cam", cam_data)
    sc.collection.objects.link(cam)
    # stand in the alley, look at the pile
    cam.location = (-0.55, 2.95, 0.72)
    look_at(cam, (-1.55, 1.55, 0.55))
    sc.camera = cam
    sc.render.resolution_x = 760
    sc.render.resolution_y = 760
    sc.render.filepath = os.path.join(A.outdir, "can_scale.png")
    bpy.ops.render.render(write_still=True)
    info["renders"].append({"file": sc.render.filepath, "camera": cam.name,
                            "camera_location": [-0.55, 2.95, 0.72],
                            "look_at": [-1.55, 1.55, 0.55],
                            "note": "red cylinder is an in-memory proxy for a "
                                    "66 mm x 122 mm beverage can, for scale only"})
    print("[a_render_check] wrote", sc.render.filepath, flush=True)

    # ---------------- 4. top-down plan of the pile ----------------
    cam2_data = bpy.data.cameras.new("board_plan_cam")
    cam2_data.type = "ORTHO"
    cam2_data.ortho_scale = 3.4
    cam2_data.clip_start = 0.05
    cam2 = bpy.data.objects.new("board_plan_cam", cam2_data)
    sc.collection.objects.link(cam2)
    cam2.location = (-1.55, 1.70, 3.2)
    look_at(cam2, (-1.55, 1.70, 0.4))
    sc.camera = cam2
    sc.render.resolution_x = 700
    sc.render.resolution_y = 760
    sc.render.filepath = os.path.join(A.outdir, "pile_plan.png")
    bpy.ops.render.render(write_still=True)
    info["renders"].append({"file": sc.render.filepath, "camera": cam2.name,
                            "ortho_scale": 3.4})
    print("[a_render_check] wrote", sc.render.filepath, flush=True)

    with open(os.path.join(A.outdir, "render_check.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    print("[a_render_check] done")


main()
