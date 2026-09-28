#!/usr/bin/env python3
"""Render every untested, plausibly rigid GSO candidate as a neutral audit still.

This is an asset review pass, not a final scene.  A consistent seamless studio
floor, three soft lights, a long lens, and a near-eye-level camera make texture
and geometry quality comparable without pretending that the studio is a real
environment.
"""

from __future__ import annotations

import json
import math
import os
import re
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


WORKSPACE = Path("/data/raw/huzijian/project1_database")
GSO_ROOT = WORKSPACE / "models" / "gso"
OUTPUT_ROOT = WORKSPACE / "outcomes" / "v5_asset_review" / "objects"
REPORT_PATH = OUTPUT_ROOT / "render_manifest.json"

TESTED = {
    "Whey_Protein_Vanilla",
    "Mad_Gab_Refresh_Card_Game",
    "Ecoforms_Plant_Container_GP16A_Coral",
    "Down_To_Earth_Orchid_Pot_Ceramic_Lime",
    "Room_Essentials_Fabric_Cube_Lavender",
    "Sootheze_Cold_Therapy_Elephant",
    "Nikon_1_AW1_w11275mm_Lens_Silver",
    "Netgear_N750_Wireless_Dual_Band_Gigabit_Router",
}

SOFT_CATEGORIES = {
    "Shoe",
    "Bag",
    "Hat",
    "Stuffed Toys",
    "Headphones",
    "Car Seat",
}

EXCLUDED_NAME_REASONS = {
    "3M_Vinyl_Tape_Green_1_x_36_yd": "flexible tape roll",
    "ASSORTED_VEGETABLE_SET": "multiple disconnected toy pieces",
    "Avengers_Gamma_Green_Smash_Fists": "foam/flexible wearable toy",
    "Cole_Hardware_Antislip_Surfacing_White_2_x_60": "flexible surfacing roll",
    "FRUIT_VEGGIE_MEMO_GRADIENT": "multiple thin loose pieces",
    "JUICER_SET": "multiple disconnected toy pieces",
    "Object": "unknown identity and physical semantics",
    "Retail_Leadership_Summit_tQFCizMt6g0": "unknown identity and physical semantics",
    "Rexy_Glove_Heavy_Duty_Large": "flexible glove",
    "ROAD_CONSTRUCTION_SET": "multiple disconnected toy pieces",
    "SANDWICH_MEAL": "multiple disconnected toy pieces",
    "Threshold_Basket_Natural_Finish_Fabric_Liner_Small": "contains a flexible fabric liner",
}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.images,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 128
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 3.0
    scene.eevee.gtao_factor = 1.15
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1440
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = -0.25
    scene.view_settings.gamma = 1.0

    world = bpy.data.worlds.new("Neutral_Audit_World")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.055, 0.065, 0.080, 1.0)
    background.inputs["Strength"].default_value = 0.55
    scene.world = world

    # Seamless cyclorama: a large floor rolls continuously into a back wall.
    # The camera never sees a floor-wall junction, which keeps this diagnostic
    # setup from introducing the artificial seam rejected in the earlier work.
    cross_section = [(-50.0, 0.0), (2.0, 0.0)]
    radius = 2.0
    for step in range(1, 9):
        theta = -math.pi / 2.0 + (math.pi / 2.0) * (step / 8.0)
        cross_section.append((2.0 + radius * math.cos(theta), 2.0 + radius * math.sin(theta)))
    cross_section.append((4.0, 50.0))
    vertices = []
    for x in (-50.0, 50.0):
        vertices.extend((x, y, z) for y, z in cross_section)
    width = len(cross_section)
    faces = [(index, index + 1, width + index + 1, width + index) for index in range(width - 1)]
    floor_mesh = bpy.data.meshes.new("Neutral_Audit_Cyclorama_Mesh")
    floor_mesh.from_pydata(vertices, [], faces)
    floor_mesh.update()
    floor = bpy.data.objects.new("Neutral_Audit_Cyclorama", floor_mesh)
    bpy.context.scene.collection.objects.link(floor)
    material = bpy.data.materials.new("Neutral_Audit_Floor_Material")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.11, 0.125, 0.15, 1.0)
    principled.inputs["Roughness"].default_value = 0.82
    floor.data.materials.append(material)
    for polygon in floor.data.polygons:
        polygon.use_smooth = True

    bpy.ops.object.camera_add(location=(0.0, -2.0, 0.3))
    camera = bpy.context.object
    camera.name = "Audit_Camera_70mm"
    camera.data.lens = 70.0
    camera.data.sensor_width = 36.0
    camera.data.dof.use_dof = False
    scene.camera = camera

    for name in ("Audit_Key", "Audit_Fill", "Audit_Rim"):
        bpy.ops.object.light_add(type="AREA", location=(0.0, 0.0, 1.0))
        light = bpy.context.object
        light.name = name
        light.data.shape = "DISK"
        light.data.use_shadow = True
        light.data.use_contact_shadow = True


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = Vector(tuple(min(corner[axis] for corner in corners) for axis in range(3)))
    upper = Vector(tuple(max(corner[axis] for corner in corners) for axis in range(3)))
    return lower, upper


def import_joined_obj(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.obj(filepath=str(path), use_image_search=True, use_split_objects=False)
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"no mesh imported from {path}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    result = bpy.context.view_layer.objects.active
    result.name = name
    for obj in imported:
        if obj != result and obj.name in bpy.context.scene.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    return result


def categorize(directory: Path, metadata: dict) -> tuple[bool, str]:
    name = directory.name
    category = metadata.get("metadata", {}).get("category")
    if name in TESTED:
        return False, "already rendered/tested"
    if category in SOFT_CATEGORIES:
        return False, f"soft or articulated category: {category}"
    if name in EXCLUDED_NAME_REASONS:
        return False, EXCLUDED_NAME_REASONS[name]
    visual = directory / "visual_geometry.obj"
    if not visual.is_file():
        return False, "missing visual_geometry.obj"
    texture_candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if not texture_candidates:
        return False, "missing texture image"
    bounds = metadata.get("kwargs", {}).get("bounds")
    if not isinstance(bounds, list) or len(bounds) != 2:
        return False, "missing physical bounds"
    dimensions = [float(bounds[1][axis] - bounds[0][axis]) for axis in range(3)]
    if min(dimensions) <= 0.0 or max(dimensions) > 0.55:
        return False, "invalid or unsuitable physical extent"
    return True, "untested single rigid scan with texture and physical bounds"


def set_camera_and_lights(lower: Vector, upper: Vector) -> dict:
    scene = bpy.context.scene
    camera = bpy.data.objects["Audit_Camera_70mm"]
    extent = upper - lower
    max_extent = max(float(extent.x), float(extent.y), float(extent.z))
    target = Vector((0.0, 0.0, float(lower.z + 0.50 * extent.z)))

    aspect = scene.render.resolution_x / scene.render.resolution_y
    horizontal_fov = 2.0 * math.atan(camera.data.sensor_width / (2.0 * camera.data.lens))
    vertical_fov = 2.0 * math.atan(math.tan(horizontal_fov / 2.0) / aspect)
    horizontal_extent = max(float(extent.x), float(extent.y))
    distance_horizontal = horizontal_extent / (2.0 * math.tan(horizontal_fov / 2.0) * 0.42)
    distance_vertical = float(extent.z) / (2.0 * math.tan(vertical_fov / 2.0) * 0.42)
    distance = max(0.38, distance_horizontal, distance_vertical)
    azimuth = math.radians(24.0)
    elevation = math.radians(6.0)
    horizontal = math.cos(elevation) * distance
    camera.location = target + Vector(
        (
            math.sin(azimuth) * horizontal,
            -math.cos(azimuth) * horizontal,
            math.sin(elevation) * distance,
        )
    )
    point_at(camera, target)

    scale = max(0.24, max_extent)
    setups = {
        "Audit_Key": ((2.8 * scale, -3.2 * scale, 3.8 * scale), 950.0 * scale * scale + 70.0, 3.2 * scale),
        "Audit_Fill": ((-3.0 * scale, -2.0 * scale, 2.2 * scale), 420.0 * scale * scale + 35.0, 2.8 * scale),
        "Audit_Rim": ((-1.8 * scale, 3.0 * scale, 3.2 * scale), 700.0 * scale * scale + 50.0, 2.4 * scale),
    }
    for name, (position, energy, size) in setups.items():
        light = bpy.data.objects[name]
        light.location = position
        light.data.energy = energy
        light.data.size = size
        point_at(light, target)
    return {
        "camera_location": [float(value) for value in camera.location],
        "camera_target": [float(value) for value in target],
        "camera_distance_m": float(distance),
        "camera_lens_mm": float(camera.data.lens),
        "object_frame_fraction_target": 0.42,
        "camera_elevation_deg": 6.0,
    }


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:180] + ".png"


def render_one(directory: Path, metadata: dict) -> dict:
    name = directory.name
    obj = import_joined_obj(directory / "visual_geometry.obj", f"Candidate_{name}")
    try:
        bpy.context.view_layer.update()
        lower, upper = world_bounds(obj)
        center = (lower + upper) * 0.5
        obj.location += Vector((-center.x, -center.y, -lower.z))
        obj.rotation_euler[2] += math.radians(18.0)
        bpy.context.view_layer.update()
        lower, upper = world_bounds(obj)
        center = (lower + upper) * 0.5
        obj.location += Vector((-center.x, -center.y, -lower.z))
        bpy.context.view_layer.update()
        lower, upper = world_bounds(obj)
        camera = set_camera_and_lights(lower, upper)

        output = OUTPUT_ROOT / safe_filename(name)
        bpy.context.scene.render.filepath = str(output)
        bpy.context.scene.render.image_settings.color_mode = "RGB"
        bpy.ops.render.render(write_still=True)
        return {
            "name": name,
            "category": metadata.get("metadata", {}).get("category"),
            "output": str(output.relative_to(WORKSPACE)),
            "bounds_m": {
                "lower": [float(value) for value in lower],
                "upper": [float(value) for value in upper],
            },
            **camera,
            "status": "rendered",
        }
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
            for datablock in list(datablocks):
                if datablock.users == 0:
                    datablocks.remove(datablock)


def main() -> None:
    if not str(OUTPUT_ROOT).startswith(str(WORKSPACE) + os.sep):
        raise RuntimeError("output path escaped workspace")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    clear_scene()
    configure_scene()

    included: list[tuple[Path, dict]] = []
    excluded: list[dict] = []
    for directory in sorted(path for path in GSO_ROOT.iterdir() if path.is_dir()):
        data_path = directory / "data.json"
        if not data_path.is_file():
            continue
        metadata = json.loads(data_path.read_text(encoding="utf-8"))
        keep, reason = categorize(directory, metadata)
        if keep:
            included.append((directory, metadata))
        else:
            excluded.append(
                {
                    "name": directory.name,
                    "category": metadata.get("metadata", {}).get("category"),
                    "reason": reason,
                }
            )

    rendered: list[dict] = []
    failures: list[dict] = []
    print(f"OBJECT_CANDIDATES included={len(included)} excluded={len(excluded)}", flush=True)
    for index, (directory, metadata) in enumerate(included, start=1):
        print(f"OBJECT_RENDER {index}/{len(included)} {directory.name}", flush=True)
        try:
            rendered.append(render_one(directory, metadata))
        except Exception as error:
            failures.append(
                {
                    "name": directory.name,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            )
            print(f"OBJECT_FAILED {directory.name}: {error}", flush=True)

    report = {
        "purpose": "untested rigid-object visual realism review",
        "selection_rule": {
            "required": [
                "Google Scanned Objects source in workspace",
                "not previously rendered/tested in project records",
                "single plausibly rigid object",
                "texture image and physical bounds present",
                "largest extent no more than 0.55 m",
            ],
            "excluded_categories": sorted(SOFT_CATEGORIES),
            "tested_names": sorted(TESTED),
        },
        "render_contract": {
            "resolution": [1920, 1440],
            "renderer": "Blender EEVEE CPU-only launch",
            "samples": 128,
            "camera_lens_mm": 70,
            "camera_elevation_deg": 6,
            "target_frame_fraction": 0.42,
            "environment": "neutral audit studio; not a candidate scene",
            "added_content": "one neutral floor and three soft area lights for comparable asset review",
        },
        "rendered": rendered,
        "excluded": excluded,
        "failures": failures,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"OBJECT_REVIEW_DONE rendered={len(rendered)} excluded={len(excluded)} failures={len(failures)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
