"""Create ready-to-open Blender previews for ReplicaCAD and GSO.

Run with Blender, not the system Python:
    blender.exe --background --factory-startup --python create_blender_previews.py

The ReplicaCAD preview assembles apt_0 from Habitat scene-instance JSON and
assigns Blender rigid bodies.  Articulated URDF assets are listed in a text
block but intentionally not converted because Blender has no native URDF
importer and their joints require a dedicated conversion pass.

The GSO preview imports both the render mesh and the provided convex collision
decomposition, wiring the latter as a Blender compound rigid body.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


DATA_ROOT = Path(r"D:\blender\data_found_online")
REPLICA_ROOT = DATA_ROOT / "ReplicaCAD_Interactive_full"
GSO_ROOT = DATA_ROOT / "GSO_Kubric_PhysicsReady_full"
OUTPUT_ROOT = Path(r"D:\workspace\project1_database\blender_previews")

REPLICA_SCENE = REPLICA_ROOT / "configs" / "scenes" / "apt_0.scene_instance.json"
GSO_OBJECT_NAME = "3D_Dollhouse_Sofa"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def new_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def imported_objects(before: set[str]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.name not in before]


def import_gltf(path: Path) -> list[bpy.types.Object]:
    before = {obj.name for obj in bpy.context.scene.objects}
    bpy.ops.import_scene.gltf(filepath=str(path))
    return imported_objects(before)


def import_obj(path: Path, *, split_objects: bool) -> list[bpy.types.Object]:
    before = {obj.name for obj in bpy.context.scene.objects}
    bpy.ops.wm.obj_import(
        filepath=str(path),
        forward_axis="NEGATIVE_Y",
        up_axis="Z",
        use_split_objects=split_objects,
    )
    return imported_objects(before)


def join_meshes(objects: list[bpy.types.Object], name: str) -> bpy.types.Object | None:
    meshes = [obj for obj in objects if obj.type == "MESH"]
    non_meshes = [obj for obj in objects if obj.type != "MESH"]
    if not meshes:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    result = bpy.context.view_layer.objects.active
    result.name = name
    for obj in non_meshes:
        if obj.name in bpy.context.scene.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    return result


def add_rigid_body(
    obj: bpy.types.Object,
    *,
    body_type: str,
    collision_shape: str,
    mass: float = 1.0,
    friction: float = 0.5,
    restitution: float = 0.0,
    margin: float = 0.002,
) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.rigidbody.object_add()
    rigid_body = obj.rigid_body
    rigid_body.type = body_type
    rigid_body.collision_shape = collision_shape
    rigid_body.mass = max(float(mass), 1e-6)
    rigid_body.friction = float(friction)
    rigid_body.restitution = float(restitution)
    rigid_body.use_margin = True
    rigid_body.collision_margin = float(margin)


def habitat_transform(translation: list[float], rotation: list[float]) -> tuple[Vector, Quaternion]:
    # Habitat/ReplicaCAD and glTF are Y-up. Blender is Z-up. The glTF importer
    # applies the same basis change to mesh data, so scene-instance transforms
    # must be conjugated by this basis matrix.
    basis = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))
    location = basis @ Vector(translation)
    q_habitat = Quaternion((rotation[0], rotation[1], rotation[2], rotation[3]))
    rotation_blender = basis @ q_habitat.to_matrix() @ basis.inverted()
    return location, rotation_blender.to_quaternion()


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_camera_and_lights(*, camera_location: tuple[float, float, float], target: tuple[float, float, float]) -> None:
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.name = "Preview_Camera"
    camera.data.lens = 45
    point_camera(camera, Vector(target))
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.object
    sun.name = "Preview_Sun"
    sun.rotation_euler = (math.radians(25), math.radians(-20), math.radians(25))
    sun.data.energy = 2.0

    bpy.ops.object.light_add(type="AREA", location=(2, -2, 7))
    area = bpy.context.object
    area.name = "Preview_Area"
    area.data.energy = 1200
    area.data.shape = "DISK"
    area.data.size = 5
    point_camera(area, Vector(target))


def configure_scene(title: str) -> None:
    scene = bpy.context.scene
    scene.name = title
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.world.color = (0.045, 0.045, 0.055)
    scene["preview_note"] = "Press Space to run the rigid-body simulation; Esc stops playback."


def create_replica_preview() -> Path:
    clear_scene()
    configure_scene("ReplicaCAD apt_0 interactive preview")
    stage_collection = new_collection("STAGE_PASSIVE_COLLISION")
    dynamic_collection = new_collection("OBJECTS_DYNAMIC")
    static_collection = new_collection("OBJECTS_STATIC")

    scene_data = json.loads(REPLICA_SCENE.read_text(encoding="utf-8"))
    stage_template = scene_data["stage_instance"]["template_name"].split("/")[-1]
    stage_config_path = REPLICA_ROOT / "configs" / "stages" / f"{stage_template}.stage_config.json"
    stage_config = json.loads(stage_config_path.read_text(encoding="utf-8"))
    stage_asset = (stage_config_path.parent / stage_config["render_asset"]).resolve()

    stage_objects = import_gltf(stage_asset)
    stage_meshes = [obj for obj in stage_objects if obj.type == "MESH"]
    for index, obj in enumerate(stage_meshes):
        obj.name = f"STAGE_{index:02d}_{obj.name}"
        move_to_collection(obj, stage_collection)
        add_rigid_body(
            obj,
            body_type="PASSIVE",
            collision_shape="MESH",
            friction=stage_config.get("friction_coefficient", 0.8),
            restitution=stage_config.get("restitution_coefficient", 0.0),
            margin=stage_config.get("margin", 0.01),
        )
        obj["replicacad_role"] = "static_stage"
        obj["source_asset"] = str(stage_asset)

    missing_assets: list[str] = []
    dynamic_count = 0
    static_count = 0
    for index, instance in enumerate(scene_data.get("object_instances", [])):
        template_name = instance["template_name"].split("/")[-1]
        object_config_path = REPLICA_ROOT / "configs" / "objects" / f"{template_name}.object_config.json"
        if not object_config_path.exists():
            missing_assets.append(str(object_config_path))
            continue
        object_config = json.loads(object_config_path.read_text(encoding="utf-8"))
        render_asset = (object_config_path.parent / object_config["render_asset"]).resolve()
        if not render_asset.exists():
            missing_assets.append(str(render_asset))
            continue

        imported = import_gltf(render_asset)
        obj = join_meshes(imported, f"{index:03d}_{template_name}")
        if obj is None:
            missing_assets.append(f"No mesh in {render_asset}")
            continue
        location, rotation = habitat_transform(instance["translation"], instance["rotation"])
        obj.location = location
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = rotation
        scale = float(instance.get("uniform_scale", 1.0))
        obj.scale = (scale, scale, scale)

        motion_type = instance.get("motion_type", "STATIC").upper()
        is_dynamic = motion_type == "DYNAMIC"
        move_to_collection(obj, dynamic_collection if is_dynamic else static_collection)
        add_rigid_body(
            obj,
            body_type="ACTIVE" if is_dynamic else "PASSIVE",
            collision_shape="CONVEX_HULL" if is_dynamic else "MESH",
            mass=object_config.get("mass", 1.0),
            friction=object_config.get("friction_coefficient", 0.5),
            restitution=object_config.get("restitution_coefficient", 0.0),
            margin=object_config.get("margin", 0.002),
        )
        collision_asset = object_config.get("collision_asset")
        if collision_asset:
            obj["source_collision_asset"] = str((object_config_path.parent / collision_asset).resolve())
        obj["source_render_asset"] = str(render_asset)
        obj["replicacad_motion_type"] = motion_type
        obj["replicacad_mass_kg"] = float(object_config.get("mass", 1.0))
        obj["preview_collision_note"] = (
            "Blender preview uses CONVEX_HULL; source_collision_asset points to ReplicaCAD's convex decomposition."
            if is_dynamic
            else "Static object uses triangle-mesh collision."
        )
        if is_dynamic:
            dynamic_count += 1
        else:
            static_count += 1

    articulated = scene_data.get("articulated_object_instances", [])
    report_lines = [
        "ReplicaCAD apt_0 Blender preview",
        f"Scene config: {REPLICA_SCENE}",
        f"Stage meshes: {len(stage_meshes)}",
        f"Dynamic rigid objects: {dynamic_count}",
        f"Static rigid objects: {static_count}",
        "",
        "Articulated URDF instances are not converted in this preview because Blender does not natively import URDF joints:",
    ]
    report_lines.extend(f"- {item['template_name']}" for item in articulated)
    if missing_assets:
        report_lines.extend(["", "Missing assets:", *[f"- {item}" for item in missing_assets]])
    text = bpy.data.texts.new("IMPORT_REPORT.txt")
    text.write("\n".join(report_lines))

    scene = bpy.context.scene
    scene["replicacad_scene_config"] = str(REPLICA_SCENE)
    scene["dynamic_rigid_object_count"] = dynamic_count
    scene["static_rigid_object_count"] = static_count
    scene["articulated_urdf_instance_count_not_converted"] = len(articulated)
    if scene.rigidbody_world:
        scene.rigidbody_world.substeps_per_frame = 10
        scene.rigidbody_world.solver_iterations = 20

    add_camera_and_lights(camera_location=(10.5, -14.0, 8.0), target=(1.0, -2.5, 1.0))
    output = OUTPUT_ROOT / "ReplicaCAD_apt0_interactive_preview.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    print(
        "REPLICA_PREVIEW",
        json.dumps(
            {
                "output": str(output),
                "stage_meshes": len(stage_meshes),
                "dynamic": dynamic_count,
                "static": static_count,
                "articulated_not_converted": len(articulated),
                "missing": len(missing_assets),
            },
            ensure_ascii=False,
        ),
    )
    return output


def create_gso_preview() -> Path:
    clear_scene()
    configure_scene(f"GSO {GSO_OBJECT_NAME} physics-ready preview")
    visual_collection = new_collection("VISUAL_MESH")
    collision_collection = new_collection("COLLISION_HULLS_WIREFRAME")
    environment_collection = new_collection("ENVIRONMENT")

    object_root = GSO_ROOT / "objects" / GSO_OBJECT_NAME
    metadata = json.loads((object_root / "data.json").read_text(encoding="utf-8"))
    mass = float(metadata["kwargs"]["mass"])

    visual_import = import_obj(object_root / "visual_geometry.obj", split_objects=False)
    visual = join_meshes(visual_import, f"VISUAL_{GSO_OBJECT_NAME}")
    if visual is None:
        raise RuntimeError("GSO visual mesh import returned no mesh")
    move_to_collection(visual, visual_collection)

    collision_import = import_obj(object_root / "collision_geometry.obj", split_objects=True)
    hulls = [obj for obj in collision_import if obj.type == "MESH"]

    parent_mesh = bpy.data.meshes.new(f"{GSO_OBJECT_NAME}_compound_parent_mesh")
    parent = bpy.data.objects.new(f"PHYSICS_{GSO_OBJECT_NAME}", parent_mesh)
    collision_collection.objects.link(parent)
    add_rigid_body(
        parent,
        body_type="ACTIVE",
        collision_shape="COMPOUND",
        mass=mass,
        friction=0.5,
        restitution=0.05,
        margin=0.001,
    )

    for hull in hulls:
        move_to_collection(hull, collision_collection)
        world = hull.matrix_world.copy()
        hull.parent = parent
        hull.matrix_parent_inverse = parent.matrix_world.inverted()
        hull.matrix_world = world
        hull.display_type = "WIRE"
        hull.color = (1.0, 0.05, 0.05, 1.0)
        hull.hide_render = True
        add_rigid_body(
            hull,
            body_type="ACTIVE",
            collision_shape="CONVEX_HULL",
            mass=max(mass / max(len(hulls), 1), 1e-6),
            friction=0.5,
            restitution=0.05,
            margin=0.001,
        )

    visual_world = visual.matrix_world.copy()
    visual.parent = parent
    visual.matrix_parent_inverse = parent.matrix_world.inverted()
    visual.matrix_world = visual_world

    # Lift the compound object two metres above a passive floor so pressing
    # Space immediately demonstrates that the asset is physically interactive.
    local_min_z = min((visual.matrix_world @ Vector(corner)).z for corner in visual.bound_box)
    parent.location.z += 2.0 - local_min_z
    parent["gso_id"] = metadata["id"]
    parent["gso_mass_kg"] = mass
    parent["gso_license"] = metadata["license"]
    parent["source_visual_mesh"] = str(object_root / "visual_geometry.obj")
    parent["source_collision_mesh"] = str(object_root / "collision_geometry.obj")
    parent["source_urdf"] = str(object_root / "object.urdf")
    parent["collision_hull_count"] = len(hulls)

    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
    floor = bpy.context.object
    floor.name = "PASSIVE_FLOOR"
    move_to_collection(floor, environment_collection)
    add_rigid_body(floor, body_type="PASSIVE", collision_shape="BOX", friction=0.8, restitution=0.1)
    material = bpy.data.materials.new("Floor_Material")
    material.diffuse_color = (0.12, 0.15, 0.18, 1.0)
    floor.data.materials.append(material)

    text = bpy.data.texts.new("IMPORT_REPORT.txt")
    text.write(
        "\n".join(
            [
                f"GSO object: {GSO_OBJECT_NAME}",
                f"License: {metadata['license']}",
                f"Mass from URDF/data.json: {mass} kg",
                f"Convex collision hulls imported: {len(hulls)}",
                "Press Space: the object should fall onto PASSIVE_FLOOR.",
                "Red wireframe objects are the provided collision decomposition and are hidden in renders.",
            ]
        )
    )

    scene = bpy.context.scene
    if scene.rigidbody_world:
        scene.rigidbody_world.substeps_per_frame = 20
        scene.rigidbody_world.solver_iterations = 30
    add_camera_and_lights(camera_location=(3.2, -4.5, 2.8), target=(0.0, 0.0, 1.0))

    output = OUTPUT_ROOT / f"GSO_{GSO_OBJECT_NAME}_physics_ready.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    print(
        "GSO_PREVIEW",
        json.dumps(
            {"output": str(output), "mass": mass, "collision_hulls": len(hulls)},
            ensure_ascii=False,
        ),
    )
    return output


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    replica_output = create_replica_preview()
    gso_output = create_gso_preview()
    print("CREATED_OUTPUTS", json.dumps([str(replica_output), str(gso_output)], ensure_ascii=False))


if __name__ == "__main__":
    main()
