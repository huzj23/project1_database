"""Generate a low-poly convex collision OBJ from a normalized visual mesh."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--urdf-output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--target-faces", type=int, default=512)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def _load(source: Path) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    suffix = source.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.import_scene.obj(filepath=str(source), use_split_objects=False)
    elif suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source))
    else:
        raise ValueError(f"Unsupported source format: {source}")


def _triangles(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_urdf(path: Path, mesh_name: str, dimensions: list[float]) -> None:
    x, y, z = dimensions
    ixx = (y * y + z * z) / 12.0
    iyy = (x * x + z * z) / 12.0
    izz = (x * x + y * y) / 12.0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0"?>
<robot name="collision_mesh">
  <link name="body">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="1.0"/>
      <inertia ixx="{ixx:.9f}" ixy="0" ixz="0" iyy="{iyy:.9f}" iyz="0" izz="{izz:.9f}"/>
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
    if args.target_faces < 8:
        raise ValueError("--target-faces must be at least 8")
    source = args.source.resolve()
    output = args.output.resolve()
    _load(source)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No mesh objects found in {source}")

    points = [
        mesh.matrix_world @ vertex.co
        for mesh in meshes
        for vertex in mesh.data.vertices
    ]
    collision_mesh = bpy.data.meshes.new("collision_mesh")
    collision_mesh.from_pydata(points, [], [])
    collision = bpy.data.objects.new("collision", collision_mesh)
    bpy.context.collection.objects.link(collision)
    bpy.context.view_layer.objects.active = collision
    collision.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.convex_hull(delete_unused=True)
    bpy.ops.object.mode_set(mode="OBJECT")

    initial_faces = _triangles(collision)
    for _ in range(4):
        current_faces = _triangles(collision)
        if current_faces <= args.target_faces:
            break
        modifier = collision.modifiers.new("low_poly", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = min(1.0, args.target_faces / current_faces)
        modifier.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = collision
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        # A dynamic PyBullet mesh must remain convex after simplification.
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.convex_hull(delete_unused=True)
        bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
        bpy.ops.object.mode_set(mode="OBJECT")
    final_faces = _triangles(collision)
    if final_faces > args.target_faces:
        raise RuntimeError(
            f"Collision mesh has {final_faces} triangles, over cap {args.target_faces}"
        )

    bpy.ops.object.select_all(action="DESELECT")
    collision.select_set(True)
    bpy.context.view_layer.objects.active = collision
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.obj(
        filepath=str(output),
        use_selection=True,
        use_materials=False,
        use_triangles=True,
        axis_forward="Y",
        axis_up="Z",
    )

    corners = [collision.matrix_world @ Vector(corner) for corner in collision.bound_box]
    lower = [min(corner[axis] for corner in corners) for axis in range(3)]
    upper = [max(corner[axis] for corner in corners) for axis in range(3)]
    dimensions = [upper[index] - lower[index] for index in range(3)]
    if args.urdf_output:
        _write_urdf(args.urdf_output.resolve(), output.name, dimensions)
    report = {
        "source": str(source),
        "output": str(output),
        "source_vertices": len(points),
        "initial_convex_hull_triangles": initial_faces,
        "vertices": len(collision.data.vertices),
        "triangles": final_faces,
        "bounds": {"min": lower, "max": upper},
        "dimensions": dimensions,
        "bounding_radius": max(
            (collision.matrix_world @ vertex.co).length
            for vertex in collision.data.vertices
        ),
        "support_height": -lower[2],
        "mesh_sha256": _sha256(output),
        "simulation": str(args.urdf_output.resolve()) if args.urdf_output else None,
        "simulation_sha256": (
            _sha256(args.urdf_output.resolve()) if args.urdf_output else None
        ),
    }
    text = json.dumps(report, indent=2)
    print("COLLISION_REPORT=" + text)
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
