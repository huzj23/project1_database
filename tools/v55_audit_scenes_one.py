"""V5.5 stage 03: audit ONE source scene, chosen by ``--scene <name>``.

Split from ``v55_audit_scenes.py`` so each scene runs in its own Blender process.
Blender 3.4.1 segfaulted (rc=139) when Hidden Alley was opened after Italian Flat in a
single process, so process isolation is required for reliable evidence.

Run:
    blender --background --factory-startup \
        --python tools/v55_audit_scenes_one.py -- --scene hidden_alley
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mathutils
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes" / "v55" / "bootstrap" / "20260928T194500"

SCENES = {
    "italian_flat": ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend",
    "hidden_alley": ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend",
    "the_shed": ROOT / "models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend",
}

V53 = {
    "italian_flat": {"mesh": 476, "camera": 7, "light": 13,
                     "sha256": "0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25"},
    "hidden_alley": {"mesh": 1367, "camera": 1, "light": 7,
                     "sha256": "3dd51c6dc7aad321e6cd4bada26785d87cdf376e649f20aa4f87ef5cf127e151"},
    "the_shed": {"mesh": 1081, "camera": 22, "light": 4,
                 "sha256": "18b007e0f55c4bb3b5f746c698b6c524508253cb763f2b7b14345cbefb81c8d0"},
}
V5REVIEW = {
    "italian_flat": {"mesh": 476, "camera": 7, "light": 13,
                     "sha256": "0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25"},
    "hidden_alley": {"mesh": 1367, "camera": 1, "light": 7,
                     "sha256": "be1247889cee3ce10028ee1ef1066a96728b3c2aa191ad12b51cc3b578fa4ae9"},
    "the_shed": {"mesh": 1081, "camera": 22, "light": 4,
                 "sha256": "fe6294a84839e2225f2d9702a05ff5bc4472ff78743daabbcc60a7a95761c6e1"},
}


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

    # Raw mesh data only -- never the evaluated depsgraph (it segfaulted).
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

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    bbox_errors = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        try:
            for corner in obj.bound_box:
                world = obj.matrix_world @ mathutils.Vector(corner)
                for i in range(3):
                    lo[i] = min(lo[i], world[i])
                    hi[i] = max(hi[i], world[i])
        except Exception:
            bbox_errors += 1

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
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "blender_version": bpy.app.version_string,
        "object_counts": counts,
        "mesh_objects": counts.get("MESH", 0),
        "light_objects": counts.get("LIGHT", 0),
        "camera_objects": counts.get("CAMERA", 0),
        "other_objects": {k: v for k, v in counts.items() if k not in ("MESH", "LIGHT", "CAMERA")},
        "light_types": light_types,
        "light_energies_sorted": sorted(energies)[:40],
        "active_camera": scene.camera.name if scene.camera else None,
        "camera_names_first10": [c.name for c in cameras[:10]],
        "world": scene.world.name if scene.world else None,
        "world_count": len(bpy.data.worlds),
        "collection_count": len(bpy.data.collections),
        "collections_first20": sorted(c.name for c in bpy.data.collections)[:20],
        "total_triangles": triangles,
        "mesh_read_errors": mesh_read_errors,
        "bbox_errors": bbox_errors,
        "bbox_world_m": bbox,
        "unit_system": unit.system,
        "scale_length": unit.scale_length,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=sorted(SCENES))
    args = ap.parse_args(argv)

    name = args.scene
    path = SCENES[name]
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "03_scene_content_audit.jsonl"

    print(f"===== {name} =====", flush=True)
    if not path.is_file():
        record = {"name": name, "path": str(path), "error": "absent"}
    else:
        try:
            record = audit(name, path)
            v53, v5 = V53[name], V5REVIEW[name]
            record["content_matches_v53_record"] = (
                record["mesh_objects"] == v53["mesh"]
                and record["camera_objects"] == v53["camera"]
                and record["light_objects"] == v53["light"]
            )
            record["content_matches_v5review_record"] = (
                record["mesh_objects"] == v5["mesh"]
                and record["camera_objects"] == v5["camera"]
                and record["light_objects"] == v5["light"]
            )
            record["sha_matches_v53_baseline"] = record["sha256"] == v53["sha256"]
            record["sha_matches_v5review_source"] = record["sha256"] == v5["sha256"]
        except Exception as exc:
            traceback.print_exc()
            record = {"name": name, "path": str(path),
                      "error": f"{type(exc).__name__}: {exc}"}

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")

    print("AUDIT_RECORD " + json.dumps(record), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
