"""Normalize a downloaded visual asset into a hierarchy-free runtime asset.

Run this script with Blender, for example::

    blender --background --python scripts/prepare_visual_asset.py -- \
      --source assets/objects/example/source/model.gltf \
      --output assets/objects/example/visual/model.glb --center

The source may also be a ``.blend`` scene.  Every mesh gets a private data
block and its complete world transform is baked into its vertices.  This is
important for the legacy PhyCo-Sim/Kubric GLB loader, which joins imported
meshes and otherwise can lose transformations inherited from parent empties.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


LIGHTING_COLLECTION_NAME = "environment_lighting"
WORLD_NAME = "environment_world"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--center", action="store_true")
    parser.add_argument(
        "--target-max-dimension",
        type=float,
        help="Uniformly scale the baked mesh so its largest dimension is this many metres.",
    )
    parser.add_argument("--object-name", default="environment")
    parser.add_argument("--base-color-texture", type=Path)
    parser.add_argument("--normal-texture", type=Path)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _load_source(source: Path) -> None:
    suffix = source.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source))
        return
    _clear_scene()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.import_scene.obj(filepath=str(source), use_split_objects=False)
    else:
        raise ValueError(f"Unsupported source format: {source}")


def _realize_collection_instances() -> int:
    """Make linked collection instances concrete before baking/joining meshes."""
    instances = [
        obj
        for obj in bpy.context.scene.objects
        if obj.instance_type != "NONE" and obj.instance_collection is not None
    ]
    if not instances:
        return 0
    bpy.ops.object.select_all(action="DESELECT")
    for obj in instances:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = instances[0]
    bpy.ops.object.duplicates_make_real(use_base_parent=True, use_hierarchy=True)
    return len(instances)


def _world_bounds(meshes: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    lower = Vector(min(corner[axis] for corner in corners) for axis in range(3))
    upper = Vector(max(corner[axis] for corner in corners) for axis in range(3))
    return lower, upper


def _object_world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = Vector(min(corner[axis] for corner in corners) for axis in range(3))
    upper = Vector(max(corner[axis] for corner in corners) for axis in range(3))
    return lower, upper


def _bake_world_transforms(
    meshes: list[bpy.types.Object], offset: Vector, uniform_scale: float
) -> None:
    for obj in meshes:
        # Old demo scenes often use linked duplicates and parent hierarchies.
        # A private copy lets us bake each instance safely without editing the source.
        obj.data = obj.data.copy()
        transform = (
            Matrix.Scale(uniform_scale, 4)
            @ Matrix.Translation(offset)
            @ obj.matrix_world
        )
        mirrored = transform.to_3x3().determinant() < 0
        obj.data.transform(transform)
        if mirrored:
            # Baking a negative scale mirrors vertex winding and normals.
            # Correct them before joining; otherwise backface-culling
            # materials make mirrored scene tiles appear to be missing.
            obj.data.flip_normals()
        obj.data.update()
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        obj.hide_set(False)
        obj.hide_render = False


def _bake_light_transforms(
    lights: list[bpy.types.Object], offset: Vector, uniform_scale: float
) -> None:
    """Preserve authored lights in the same normalized coordinate system as meshes."""
    for light in lights:
        light.data = light.data.copy()
        transform = (
            Matrix.Scale(uniform_scale, 4)
            @ Matrix.Translation(offset)
            @ light.matrix_world
        )
        light.parent = None
        light.matrix_world = transform
        light.hide_set(False)
        light.hide_render = False


def _preserve_authored_lighting(
    lights: list[bpy.types.Object], offset: Vector, uniform_scale: float
) -> None:
    """Store source lights and World under stable names for the runtime loader."""
    _bake_light_transforms(lights, offset, uniform_scale)
    existing = bpy.data.collections.get(LIGHTING_COLLECTION_NAME)
    if existing is not None:
        existing.name = f"{LIGHTING_COLLECTION_NAME}__source"
    lighting_collection = bpy.data.collections.new(LIGHTING_COLLECTION_NAME)
    bpy.context.scene.collection.children.link(lighting_collection)
    for light in lights:
        for collection in tuple(light.users_collection):
            collection.objects.unlink(light)
        lighting_collection.objects.link(light)

    world = bpy.context.scene.world
    if world is not None:
        existing_world = bpy.data.worlds.get(WORLD_NAME)
        if existing_world is not None and existing_world != world:
            existing_world.name = f"{WORLD_NAME}__source"
        world.name = WORLD_NAME


def _apply_texture_override(
    meshes: list[bpy.types.Object],
    base_color_texture: Path | None,
    normal_texture: Path | None,
) -> None:
    """Repair a downloaded mesh whose material references missing local files."""
    if base_color_texture is None and normal_texture is None:
        return
    material = bpy.data.materials.new("normalized_asset_material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    if base_color_texture is not None:
        image = bpy.data.images.load(str(base_color_texture.resolve()), check_existing=True)
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.label = "Base Color"
        links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    if normal_texture is not None:
        image = bpy.data.images.load(str(normal_texture.resolve()), check_existing=True)
        image.colorspace_settings.name = "Non-Color"
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.label = "Normal"
        normal_map = nodes.new("ShaderNodeNormalMap")
        links.new(texture.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(material)


def main() -> int:
    args = _arguments()
    source = args.source.resolve()
    output = args.output.resolve()
    _load_source(source)
    realized_instance_count = _realize_collection_instances()

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    lights = [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT"]
    if not meshes:
        raise RuntimeError(f"No mesh objects found in {source}")
    _apply_texture_override(meshes, args.base_color_texture, args.normal_texture)

    source_lower, source_upper = _world_bounds(meshes)
    source_dimensions = source_upper - source_lower
    uniform_scale = 1.0
    if args.target_max_dimension is not None:
        if args.target_max_dimension <= 0:
            raise ValueError("--target-max-dimension must be positive")
        largest_dimension = max(source_dimensions)
        if largest_dimension <= 0:
            raise ValueError("Cannot scale an asset with zero-sized bounds")
        uniform_scale = args.target_max_dimension / largest_dimension
    horizontal_candidates = []
    for obj in meshes:
        obj_lower, obj_upper = _object_world_bounds(obj)
        dimensions = obj_upper - obj_lower
        horizontal_candidates.append(
            {
                "name": obj.name,
                "bounds": {"min": list(obj_lower), "max": list(obj_upper)},
                "dimensions": list(dimensions),
                "xy_area": float(dimensions.x * dimensions.y),
            }
        )
    horizontal_candidates.sort(
        key=lambda item: item["xy_area"] / max(float(item["dimensions"][2]), 0.01),
        reverse=True,
    )
    center_offset = -(source_lower + source_upper) / 2.0 if args.center else Vector((0, 0, 0))
    _bake_world_transforms(meshes, center_offset, uniform_scale)
    lower = (source_lower + center_offset) * uniform_scale
    upper = (source_upper + center_offset) * uniform_scale
    for obj in meshes:
        obj.data.calc_loop_triangles()
    mesh_object_count = len(meshes)
    vertex_count = sum(len(obj.data.vertices) for obj in meshes)
    triangle_count = sum(len(obj.data.loop_triangles) for obj in meshes)
    largest_meshes = [
        {
            "name": obj.name,
            "vertices": len(obj.data.vertices),
            "dimensions": list(obj.dimensions),
            "location": list(obj.location),
        }
        for obj in sorted(meshes, key=lambda item: len(item.data.vertices), reverse=True)[:20]
    ]

    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".blend":
        # A packed Blend keeps older/complex node materials that glTF cannot
        # faithfully represent, while exposing one object to Kubric's append loader.
        bpy.ops.object.make_local(type="ALL")
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        bpy.ops.object.select_all(action="DESELECT")
        for obj in meshes:
            obj.select_set(True)
        # join() retains modifiers from the active object and discards the
        # others. A scatter-plane modifier applied to the complete joined
        # scene can explode its bounds, so use an unmodified mesh as active.
        join_target = next((obj for obj in meshes if not obj.modifiers), None)
        if join_target is None:
            raise RuntimeError("No unmodified mesh is available as a safe join target")
        bpy.context.view_layer.objects.active = join_target
        bpy.ops.object.join()
        visual_object = bpy.context.view_layer.objects.active
        visual_object.name = args.object_name
        visual_object.data.name = f"{args.object_name}_mesh"
        _preserve_authored_lighting(lights, center_offset, uniform_scale)
        # Blender's glTF importer uses this global node-group name as an API.
        # A Blend saved by another importer/version may contain an incompatible
        # group with the same name, which then breaks later GLB imports after
        # the environment is appended. Keep the source material wiring but
        # isolate its node group under an asset-owned name.
        for node_group in bpy.data.node_groups:
            if node_group.name == "glTF Material Output":
                node_group.name = f"{args.object_name}__source_glTF_material_output"
        for obj in tuple(bpy.data.objects):
            if obj != visual_object and obj.type != "LIGHT":
                bpy.data.objects.remove(obj, do_unlink=True)
        for image in bpy.data.images:
            if image.source == "FILE" and not image.packed_file:
                try:
                    # pack() can read an unloaded image directly from its path.
                    image.pack()
                except RuntimeError as exc:
                    print(f"IMAGE_PACK_WARNING name={image.name!r} error={exc}")
        bpy.ops.outliner.orphans_purge(do_recursive=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    elif output.suffix.lower() == ".glb":
        bpy.ops.export_scene.gltf(
            filepath=str(output),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_cameras=False,
            export_lights=False,
        )
    else:
        raise ValueError(f"Output must be .glb or .blend, got {output}")

    report = {
        "source": str(source),
        "output": str(output),
        "mesh_objects": mesh_object_count,
        "realized_collection_instances": realized_instance_count,
        "vertices": vertex_count,
        "triangles": triangle_count,
        "source_bounds": {"min": list(source_lower), "max": list(source_upper)},
        "uniform_scale": uniform_scale,
        "bounds": {"min": list(lower), "max": list(upper)},
        "dimensions": list(upper - lower),
        "preserved_light_count": len(lights) if output.suffix.lower() == ".blend" else 0,
        "preserved_lights": [
            {
                "name": light.name,
                "type": light.data.type,
                "energy": float(light.data.energy),
                "position": list(light.matrix_world.translation),
            }
            for light in lights
        ]
        if output.suffix.lower() == ".blend"
        else [],
        "preserved_world": (
            bpy.context.scene.world.name if bpy.context.scene.world is not None else None
        ),
        "horizontal_candidates": horizontal_candidates[:30],
        "largest_meshes": largest_meshes,
    }
    text = json.dumps(report, indent=2)
    print(f"ASSET_REPORT={text}")
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
