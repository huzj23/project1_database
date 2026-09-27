"""Extract a low-poly static collision mesh from one environment component.

This is intended for selected semantic surfaces such as an irregular student
desktop.  It realizes one linked collection instance, keeps only the named
mesh components, bakes their world transforms, and writes a static URDF.  The
source Blend is opened read-only and is never saved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--instance")
    parser.add_argument("--component", action="append")
    parser.add_argument("--object", action="append", dest="objects")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--urdf-output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-faces", type=int, default=2048)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _triangles(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def _write_urdf(path: Path, mesh_name: str, surface_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0"?>
<robot name="{surface_id}">
  <link name="surface">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="0"/>
      <inertia ixx="0" ixy="0" ixz="0" iyy="0" iyz="0" izz="0"/>
    </inertial>
    <collision>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><mesh filename="{mesh_name}" scale="1 1 1"/></geometry>
    </collision>
  </link>
</robot>
""",
        encoding="utf-8",
    )


def main() -> int:
    args = _arguments()
    if args.max_faces < 32:
        raise ValueError("--max-faces must be at least 32")
    source = args.source.resolve()
    output = args.output.resolve()
    urdf_output = args.urdf_output.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(source))

    if bool(args.instance) == bool(args.objects):
        raise ValueError("Specify either --instance/--component or one or more --object")
    if args.instance:
        if not args.component:
            raise ValueError("--instance requires at least one --component")
        instance = bpy.data.objects.get(args.instance)
        if instance is None or instance.instance_collection is None:
            raise ValueError(f"No linked collection instance named {args.instance!r}")
        bpy.ops.object.select_all(action="DESELECT")
        instance.select_set(True)
        bpy.context.view_layer.objects.active = instance
        bpy.ops.object.duplicates_make_real(use_base_parent=True, use_hierarchy=True)
        requested = set(args.component)
        components = [
            obj
            for obj in bpy.context.selected_objects
            if obj.type == "MESH" and obj.name in requested
        ]
    else:
        requested = set(args.objects)
        components = [
            obj
            for name in args.objects
            if (obj := bpy.data.objects.get(name)) is not None and obj.type == "MESH"
        ]
    missing = requested - {obj.name for obj in components}
    if missing:
        raise ValueError(f"Missing realized components: {sorted(missing)}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in components:
        obj.data = obj.data.copy()
        obj.data.transform(obj.matrix_world)
        obj.matrix_world = Matrix.Identity(4)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = components[0]
    bpy.ops.object.join()
    collision = bpy.context.view_layer.objects.active
    collision.name = "surface_collision"
    source_triangles = _triangles(collision)
    if source_triangles > args.max_faces:
        modifier = collision.modifiers.new("low_poly", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = args.max_faces / source_triangles
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.context.view_layer.objects.active = collision
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
    bpy.ops.object.mode_set(mode="OBJECT")
    final_triangles = _triangles(collision)
    if final_triangles > args.max_faces:
        raise RuntimeError(
            f"Surface collision has {final_triangles} triangles, over cap {args.max_faces}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.obj(
        filepath=str(output),
        use_selection=True,
        use_materials=False,
        use_triangles=True,
        axis_forward="Y",
        axis_up="Z",
    )
    _write_urdf(urdf_output, output.name, output.stem)

    world_vertices = [collision.matrix_world @ vertex.co for vertex in collision.data.vertices]
    lower = [min(vertex[axis] for vertex in world_vertices) for axis in range(3)]
    upper = [max(vertex[axis] for vertex in world_vertices) for axis in range(3)]
    report = {
        "source": str(source),
        "instance": args.instance,
        "components": args.component or args.objects,
        "source_triangles": source_triangles,
        "max_faces": args.max_faces,
        "vertices": len(collision.data.vertices),
        "triangles": final_triangles,
        "bounds": {"min": lower, "max": upper},
        "mesh": str(output),
        "mesh_sha256": _sha256(output),
        "simulation": str(urdf_output),
        "simulation_sha256": _sha256(urdf_output),
    }
    text = json.dumps(report, indent=2)
    print("SURFACE_COLLISION_REPORT=" + text)
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
