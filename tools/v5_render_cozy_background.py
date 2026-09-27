"""Render a short Cozy Kitchen establishing shot using authored content only."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


OUTPUT_DIR = Path(
    "/data/raw/huzijian/project1_database/outcomes/v5/cozy_kitchen_background/frames"
)


def main() -> None:
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("Cozy Kitchen has no active authored camera")
    authored_lights = [obj for obj in scene.objects if obj.type == "LIGHT"]
    if len(authored_lights) != 13:
        raise RuntimeError(
            f"Expected exactly 13 authored lights; source has {len(authored_lights)}"
        )
    if scene.world is None:
        raise RuntimeError("Cozy Kitchen has no authored World")

    # Do not add, remove, or change scene content.  The only animation is a very
    # small dolly on the already-authored wide camera so the background result is
    # visibly a video rather than a duplicated still.
    start_location = camera.location.copy()
    start_quaternion = camera.rotation_euler.to_quaternion()
    camera_right = start_quaternion @ Vector((1.0, 0.0, 0.0))

    scene.frame_start = 1
    scene.frame_end = 48
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(OUTPUT_DIR / "frame_####.png")

    camera.rotation_mode = "QUATERNION"
    for frame in (1, 48):
        alpha = (frame - 1) / 47.0
        smooth = alpha * alpha * (3.0 - 2.0 * alpha)
        # CAM-wide is orthographic, so moving along its viewing axis would be
        # visually static.  A restrained 0.12 m authored-camera truck produces
        # a real establishing-shot pan without changing scene contents.
        camera.location = start_location + camera_right * (0.12 * smooth)
        camera.rotation_quaternion = start_quaternion
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    scene.render.fps = 16
    scene.render.fps_base = 1.0
    print(
        "BACKGROUND_CONTRACT "
        f"camera={camera.name} lights={len(authored_lights)} "
        f"world={scene.world.name} engine={scene.render.engine} "
        "added_geometry=0 added_lights=0 added_worlds=0"
    )
    bpy.ops.render.render(animation=True)
    print("BACKGROUND_RENDER_DONE")


main()
