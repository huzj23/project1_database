"""V5.5 stage 03: content-level audit of the three source scenes.

Why this exists
---------------
The plan's SHA-256 baselines do not match the files on disk for Hidden Alley and The
Shed, but those files come from archives that pass ``unzip -t`` and whose extracted
member sizes equal the archive directory listing.  A byte hash cannot tell us whether
the CONTENT is the planned scene, so this opens each scene and measures object counts,
authored lights, the camera, the World, unit settings and the bounding box.

Engineering notes learned the hard way
--------------------------------------
* ``to_mesh()`` on the evaluated depsgraph SEGFAULTED Blender 3.4.1 on Hidden Alley
  (1367 meshes, rc=139).  A segfault cannot be caught from Python, so this version
  never evaluates the depsgraph: it reads ``obj.data`` directly and wraps every
  per-object access in try/except.
* Results are written after EACH scene and stdout is flushed, so a crash still leaves
  evidence for the scenes that succeeded.

Run under Blender:
    blender --background --factory-startup --python tools/v55_audit_scenes.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes" / "v55" / "bootstrap" / "20260928T194500"

SCENES = [
    ("italian_flat", ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend"),
    ("hidden_alley", ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"),
    ("the_shed", ROOT / "models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend"),
]

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

log_path = OUT / "03_scene_content_audit.jsonl"
report_path = OUT / "03_scene_content_audit.json"


def emit(record: dict) -> None:
    """Append one scene's result and print it, flushing so a crash loses nothing."""
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print("AUDIT_RECORD " + json.dumps({k: record.get(k) for k in (
        "name", "sha256", "mesh_objects", "light_objects", "camera_objects",
        "active_camera", "world", "unit_system", "scale_length",
        "content_matches_v53_record", "content_matches_v5review_record",
        "sha_matches_v53_baseline", "sha_matches_v5review_source", "error",
    )}), flush=True)


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
    active = scene.camera.name if scene.camera else None

    # Raw (non-evaluated) triangle count: obj.data is always safe to read, unlike the
    # evaluated depsgraph which crashed on this scene.
    triangles = 0
    mesh_read_errors = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        try:
            me = obj.data
            if me is not None and hasattr(me, "loop_triangles"):
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
                world = obj.matrix_world @ __import__("mathutils").Vector(corner)
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
        "light_energies": sorted(energies)[:40],
        "active_camera": active,
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
    OUT.mkdir(parents=True, exist_ok=True)
    # Start a fresh JSONL for this attempt without deleting a previous one.
    if log_path.exists():
        log_path.rename(log_path.with_name(log_path.name + ".prev"))
    log_path.write_text("", encoding="utf-8")

    results: dict[str, dict] = {}
    for name, path in SCENES:
        print(f"\n===== {name} =====", flush=True)
        if not path.is_file():
            print(f"  ABSENT: {path}", flush=True)
            record = {"name": name, "path": str(path), "error": "absent"}
            emit(record)
            results[name] = record
            continue
        try:
            info = audit(name, path)
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            record = {"name": name, "path": str(path),
                      "error": f"{type(exc).__name__}: {exc}"}
            emit(record)
            results[name] = record
            continue

        v53, v5 = V53[name], V5REVIEW[name]
        info["content_matches_v53_record"] = (
            info["mesh_objects"] == v53["mesh"]
            and info["camera_objects"] == v53["camera"]
            and info["light_objects"] == v53["light"]
        )
        info["content_matches_v5review_record"] = (
            info["mesh_objects"] == v5["mesh"]
            and info["camera_objects"] == v5["camera"]
            and info["light_objects"] == v5["light"]
        )
        info["sha_matches_v53_baseline"] = info["sha256"] == v53["sha256"]
        info["sha_matches_v5review_source"] = info["sha256"] == v5["sha256"]

        print(f"  sha256        : {info['sha256']}", flush=True)
        print(f"  mesh/light/cam: {info['mesh_objects']} / {info['light_objects']} / {info['camera_objects']}", flush=True)
        print(f"  light types   : {info['light_types']}", flush=True)
        print(f"  active camera : {info['active_camera']}", flush=True)
        print(f"  world         : {info['world']} (worlds={info['world_count']})", flush=True)
        print(f"  collections   : {info['collection_count']}", flush=True)
        print(f"  triangles     : {info['total_triangles']} (read errors={info['mesh_read_errors']})", flush=True)
        print(f"  bbox size m   : {info['bbox_world_m']['size'] if info['bbox_world_m'] else None}", flush=True)
        print(f"  units         : {info['unit_system']} scale_length={info['scale_length']}", flush=True)
        print(f"  content==V5.3 : {info['content_matches_v53_record']}  "
              f"(V5.3 {v53['mesh']}/{v53['camera']}/{v53['light']})", flush=True)
        print(f"  content==V5rev: {info['content_matches_v5review_record']}  "
              f"(V5rev {v5['mesh']}/{v5['camera']}/{v5['light']})", flush=True)
        print(f"  sha==V5.3     : {info['sha_matches_v53_baseline']}", flush=True)
        print(f"  sha==V5rev    : {info['sha_matches_v5review_source']}", flush=True)

        emit(info)
        results[name] = info

    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
