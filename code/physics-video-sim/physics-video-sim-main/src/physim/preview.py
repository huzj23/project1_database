"""Blender viewport guides layered on the shared render scene."""

from __future__ import annotations

from typing import Any

from physim.physics import SimulationResult
from physim.scenarios import ScenarioSample


def add_preview_guides(
    built_scene: Any,
    sample: ScenarioSample,
    simulation: SimulationResult,
    config: dict,
) -> dict[str, Any]:
    """Add minimal non-rendering viewport markers without changing the scene."""
    import bpy

    collection = bpy.data.collections.new("PHYSIM_PREVIEW_GUIDES")
    bpy.context.scene.collection.children.link(collection)

    def move_to_guides(obj) -> None:
        for owner in tuple(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)
        obj.hide_render = True
        obj.show_in_front = True

    bpy.ops.object.empty_add(type="ARROWS", location=sample.position)
    spawn = bpy.context.object
    spawn.name = "GUIDE_SpawnPosition"
    spawn.empty_display_size = max(sample.radius * 2.5, 0.3)
    spawn.color = (0.1, 1.0, 0.2, 1.0)
    move_to_guides(spawn)

    camera_object = built_scene.camera.linked_objects[built_scene.renderer]
    bpy.ops.object.empty_add(type="SPHERE", location=config["camera_look_at"])
    camera_target = bpy.context.object
    camera_target.name = "GUIDE_CameraTarget"
    camera_target.empty_display_size = 0.18
    camera_target.color = (0.8, 0.2, 1.0, 1.0)
    move_to_guides(camera_target)

    scene = bpy.context.scene
    scene.frame_start = simulation.trajectory[0].frame
    scene.frame_end = simulation.trajectory[-1].frame
    scene.render.fps = sample.video_fps
    scene.frame_set(scene.frame_start)
    scene.camera = camera_object
    scene["physim_scenario"] = sample.scenario
    scene["physim_seed"] = sample.seed
    scene["physim_asset_id"] = sample.asset_id
    scene["physim_map_id"] = sample.map_id
    scene["physim_surface_id"] = sample.surface_id
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.region_3d.view_perspective = "CAMERA"
            space.shading.type = "SOLID"
            space.shading.color_type = "OBJECT"
            space.overlay.show_relationship_lines = True
            space.overlay.show_extras = True

    return {
        "collection": collection.name,
        "spawn": spawn.name,
        "camera": camera_object.name,
        "camera_target": camera_target.name,
    }


add_rolling_preview_guides = add_preview_guides
