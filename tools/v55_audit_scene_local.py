"""V5.5 stage 03: audit a source scene under the LOCAL Blender 4.2.23.

Rationale
---------
The server's only runnable Blender is 3.4.1 (host is glibc 2.17 / CentOS 7).  Blender
4.2.23 exists in the workspace but cannot start there (needs glibc 2.26/2.27), and
`ph_hidden_alley.blend` was written by Blender 4.0, which 3.4.1 cannot read at all -- it
segfaults inside the file read.  06 section 4 designates exactly this route: solve and
record on the server, then replay/render locally with the validated 4.2.23.

So this script runs the SAME content audit through local Blender 4.2.23, using the local
mirror of the models tree, to prove the file is intact and readable and to capture facts
(light count, camera, world, units, triangles) the server could not measure.

Run:
    blender.exe --background --factory-startup \
        --python tools/v55_audit_scene_local.py -- --scene hidden_alley
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outcomes" / "v55" / "bootstrap" / "20260928T194500"

SCENES = {
    "italian_flat": ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend",
    "hidden_alley": ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend",
    "the_shed": ROOT / "models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend",
}

EXPECT = {
    "italian_flat": {"mesh": 476, "camera": 7, "light": 13, "sha256": "0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25"},
    "hidden_alley": {"mesh": 1367, "camera": 1, "light": 7, "sha256": "be1247889cee3ce10028ee1ef1066a96728b3c2aa191ad12b51cc3b578fa4ae9"},
    "the_shed": {"mesh": 1081, "camera": 22, "light": 4, "sha256": "fe6294a84839e2225f2d9702a05ff5bc4472ff78743daabbcc60a7a95761c6e1"},
}


def sha256_of(path: Path) -> str:
    """Streaming hash: the scenes are up to 481 MB, so reading them whole is wasteful."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(name: str, path: Path) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene = bpy.context.scene

    counts: dict[str, int] = {}
    for obj in bpy.data.objects:
        counts[obj.type] = counts.get(obj.type, 0) + 1

    lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
    light_types: dict[str, int] = {}
    energies: list[float] = []
    for light in lights:
        try:
            lt = light.data.type
            light_types[lt] = light_types.get(lt, 0) + 1
            energies.append(round(float(light.data.energy), 3))
        except Exception:
            light_types["UNREADABLE"] = light_types.get("UNREADABLE", 0) + 1

    cameras = [o for o in bpy.data.objects if o.type == "CAMERA"]

    # Raw mesh data; also count connected components of the wooden board groups,
    # which 06 section 1 requires before any board is selected.
    triangles = 0
    mesh_read_errors = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        try:
            me = obj.data
            if me is not None:
                if len(me.loop_triangles) == 0:
                    me.calc_loop_triangles()
                triangles += len(me.loop_triangles)
        except Exception:
            mesh_read_errors += 1

    boards = {}
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name.lower().startswith("wooden_boards"):
            try:
                me = obj.data
                # Union-find over edges to count connected components (unwelded splits
                # would otherwise inflate the count).
                parent = list(range(len(me.vertices)))

                def find(x: int) -> int:
                    while parent[x] != x:
                        parent[x] = parent[parent[x]]
                        x = parent[x]
                    return x

                def union(a: int, b: int) -> None:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[rb] = ra

                for edge in me.edges:
                    union(edge.vertices[0], edge.vertices[1])
                components = len({find(i) for i in range(len(me.vertices))})
                boards[obj.name] = {
                    "vertices": len(me.vertices),
                    "edges": len(me.edges),
                    "polygons": len(me.polygons),
                    "connected_components": components,
                    "dimensions_m": [round(v, 5) for v in obj.dimensions],
                    "world_location": [round(v, 5) for v in obj.matrix_world.translation],
                    "visible_render": obj.visible_get(),
                }
            except Exception as exc:
                boards[obj.name] = {"error": f"{type(exc).__name__}: {exc}"}

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    from mathutils import Vector

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        try:
            for corner in obj.bound_box:
                world = obj.matrix_world @ Vector(corner)
                for i in range(3):
                    lo[i] = min(lo[i], world[i])
                    hi[i] = max(hi[i], world[i])
        except Exception:
            pass

    bbox = None
    if lo[0] != float("inf"):
        bbox = {
            "min": [round(v, 4) for v in lo],
            "max": [round(v, 4) for v in hi],
            "size": [round(hi[i] - lo[i], 4) for i in range(3)],
        }

    unit = scene.unit_settings
    return {
        "name": name,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        "blender_version": bpy.app.version_string,
        "object_counts": counts,
        "mesh_objects": counts.get("MESH", 0),
        "light_objects": counts.get("LIGHT", 0),
        "camera_objects": counts.get("CAMERA", 0),
        "other_objects": {k: v for k, v in counts.items() if k not in ("MESH", "LIGHT", "CAMERA")},
        "light_types": light_types,
        "light_energies_sorted": sorted(energies),
        "active_camera": scene.camera.name if scene.camera else None,
        "camera_names": [c.name for c in cameras],
        "world": scene.world.name if scene.world else None,
        "world_count": len(bpy.data.worlds),
        "collection_count": len(bpy.data.collections),
        "total_triangles": triangles,
        "mesh_read_errors": mesh_read_errors,
        "bbox_world_m": bbox,
        "unit_system": unit.system,
        "scale_length": unit.scale_length,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "wooden_board_groups": boards,
        "opened_successfully": True,
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=sorted(SCENES))
    args = ap.parse_args(argv)

    name = args.scene
    path = SCENES[name]
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "03_scene_content_audit_local.jsonl"

    print(f"===== LOCAL 4.2.23: {name} =====", flush=True)
    if not path.is_file():
        record = {"name": name, "path": str(path), "error": "absent"}
    else:
        try:
            record = audit(name, path)
            exp = EXPECT[name]
            record["content_matches_planning_record"] = (
                record["mesh_objects"] == exp["mesh"]
                and record["camera_objects"] == exp["camera"]
                and record["light_objects"] == exp["light"]
            )
            record["sha_matches_planning_record"] = record["sha256"] == exp["sha256"]
        except Exception as exc:
            traceback.print_exc()
            record = {"name": name, "path": str(path),
                      "error": f"{type(exc).__name__}: {exc}",
                      "opened_successfully": False}

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print("LOCAL_AUDIT_RECORD " + json.dumps(record), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
