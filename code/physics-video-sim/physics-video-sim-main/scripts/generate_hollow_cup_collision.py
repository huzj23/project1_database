"""Generate a compound collision model that keeps a cup cavity hollow."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--body-center-y", type=float, default=-0.01754)
    parser.add_argument("--outer-radius", type=float, default=0.0393)
    parser.add_argument("--inner-radius", type=float, default=0.0330)
    parser.add_argument("--bottom-z", type=float, default=-0.0600)
    parser.add_argument("--top-z", type=float, default=0.0600)
    parser.add_argument("--base-thickness", type=float, default=0.0060)
    parser.add_argument("--wall-segments", type=int, default=32)
    parser.add_argument("--handle-segments", type=int, default=12)
    parser.add_argument("--handle-center-y", type=float, default=0.0218)
    parser.add_argument("--handle-radius-y", type=float, default=0.0370)
    parser.add_argument("--handle-radius-z", type=float, default=0.0350)
    parser.add_argument("--handle-tube-radius", type=float, default=0.0045)
    parser.add_argument("--report", type=Path)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()


def _mesh_text(
    name: str,
    vertices: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
) -> str:
    lines = [f"o {name}"]
    lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices)
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in triangles)
    return "\n".join(lines) + "\n"


def _prism_faces() -> list[tuple[int, int, int]]:
    return [
        (0, 2, 1), (0, 3, 2),
        (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4),
        (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6),
        (3, 0, 4), (3, 4, 7),
    ]


def _wall_part(
    index: int,
    segments: int,
    center_y: float,
    inner_radius: float,
    outer_radius: float,
    bottom_z: float,
    top_z: float,
) -> tuple[str, list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    angles = (2 * math.pi * index / segments, 2 * math.pi * (index + 1) / segments)
    ring = []
    for radius, angle in (
        (outer_radius, angles[0]),
        (outer_radius, angles[1]),
        (inner_radius, angles[1]),
        (inner_radius, angles[0]),
    ):
        ring.append((radius * math.cos(angle), center_y + radius * math.sin(angle)))
    vertices = [(x, y, bottom_z) for x, y in ring] + [
        (x, y, top_z) for x, y in ring
    ]
    return f"wall_{index:02d}", vertices, _prism_faces()


def _cylinder_part(
    segments: int,
    center_y: float,
    radius: float,
    bottom_z: float,
    top_z: float,
) -> tuple[str, list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices = [
        (radius * math.cos(2 * math.pi * i / segments), center_y + radius * math.sin(2 * math.pi * i / segments), bottom_z)
        for i in range(segments)
    ]
    vertices += [(x, y, top_z) for x, y, _ in vertices]
    bottom_center = len(vertices)
    vertices.append((0.0, center_y, bottom_z))
    top_center = len(vertices)
    vertices.append((0.0, center_y, top_z))
    triangles = []
    for i in range(segments):
        j = (i + 1) % segments
        triangles.extend(
            [
                (bottom_center, j, i),
                (top_center, segments + i, segments + j),
                (i, j, segments + j),
                (i, segments + j, segments + i),
            ]
        )
    return "base", vertices, triangles


def _handle_part(
    index: int,
    segments: int,
    center_y: float,
    radius_y: float,
    radius_z: float,
    tube_radius: float,
) -> tuple[str, list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    angle_a = -math.pi / 2 + math.pi * index / segments
    angle_b = -math.pi / 2 + math.pi * (index + 1) / segments
    a = (center_y + radius_y * math.cos(angle_a), radius_z * math.sin(angle_a))
    b = (center_y + radius_y * math.cos(angle_b), radius_z * math.sin(angle_b))
    tangent_y, tangent_z = b[0] - a[0], b[1] - a[1]
    length = math.hypot(tangent_y, tangent_z)
    tangent_y, tangent_z = tangent_y / length, tangent_z / length
    normal_y, normal_z = -tangent_z, tangent_y
    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    vertices = []
    for x_sign, tangent_sign, normal_sign in (
        (-1, -1, -1), (-1, 1, -1), (-1, 1, 1), (-1, -1, 1),
        (1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1),
    ):
        y = (
            center[0]
            + tangent_sign * tangent_y * length / 2
            + normal_sign * normal_y * tube_radius
        )
        z = (
            center[1]
            + tangent_sign * tangent_z * length / 2
            + normal_sign * normal_z * tube_radius
        )
        vertices.append((x_sign * tube_radius, y, z))
    return f"handle_{index:02d}", vertices, _prism_faces()


def main() -> int:
    args = _parser().parse_args()
    if args.inner_radius <= 0 or args.inner_radius >= args.outer_radius:
        raise ValueError("inner radius must be positive and smaller than outer radius")
    if args.wall_segments < 16 or args.handle_segments < 6:
        raise ValueError("Use at least 16 wall and 6 handle segments")
    output_dir = args.output_dir.resolve()
    parts_dir = output_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    parts = [
        _wall_part(
            index,
            args.wall_segments,
            args.body_center_y,
            args.inner_radius,
            args.outer_radius,
            args.bottom_z + args.base_thickness,
            args.top_z,
        )
        for index in range(args.wall_segments)
    ]
    parts.append(
        _cylinder_part(
            args.wall_segments,
            args.body_center_y,
            args.outer_radius,
            args.bottom_z,
            args.bottom_z + args.base_thickness,
        )
    )
    parts.extend(
        _handle_part(
            index,
            args.handle_segments,
            args.handle_center_y,
            args.handle_radius_y,
            args.handle_radius_z,
            args.handle_tube_radius,
        )
        for index in range(args.handle_segments)
    )

    part_paths = []
    combined_vertices: list[tuple[float, float, float]] = []
    combined_triangles: list[tuple[int, int, int]] = []
    for name, vertices, triangles in parts:
        part_path = parts_dir / f"{name}.obj"
        part_path.write_text(_mesh_text(name, vertices, triangles), encoding="utf-8")
        part_paths.append(part_path)
        offset = len(combined_vertices)
        combined_vertices.extend(vertices)
        combined_triangles.extend(
            (a + offset, b + offset, c + offset) for a, b, c in triangles
        )

    model_path = output_dir / "model.obj"
    model_path.write_text(
        _mesh_text("hollow_cup_compound", combined_vertices, combined_triangles),
        encoding="utf-8",
    )
    collisions = "\n".join(
        "    <collision>\n"
        "      <origin xyz=\"0 0 0\" rpy=\"0 0 0\"/>\n"
        f"      <geometry><mesh filename=\"parts/{path.name}\" scale=\"1 1 1\"/></geometry>\n"
        "    </collision>"
        for path in part_paths
    )
    urdf_path = output_dir / "model.urdf"
    urdf_path.write_text(
        f"""<?xml version="1.0"?>
<robot name="hollow_coffee_cup_collision">
  <link name="body">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="1.0"/>
      <inertia ixx="0.0012" ixy="0" ixz="0" iyy="0.0012" iyz="0" izz="0.0010"/>
    </inertial>
{collisions}
  </link>
</robot>
""",
        encoding="utf-8",
    )
    bounding_radius = max(math.sqrt(x * x + y * y + z * z) for x, y, z in combined_vertices)
    report = {
        "collision_strategy": "compound_hollow_shell",
        "wall_segments": args.wall_segments,
        "handle_segments": args.handle_segments,
        "convex_parts": len(parts),
        "vertices": len(combined_vertices),
        "triangles": len(combined_triangles),
        "outer_radius": args.outer_radius,
        "inner_radius": args.inner_radius,
        "cavity_diameter": args.inner_radius * 2,
        "bounding_radius": bounding_radius,
        "support_height": -args.bottom_z,
        "mesh": str(model_path),
        "mesh_sha256": _sha256(model_path),
        "simulation": str(urdf_path),
        "simulation_sha256": _sha256(urdf_path),
    }
    text = json.dumps(report, indent=2)
    print("HOLLOW_CUP_COLLISION_REPORT=" + text)
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
