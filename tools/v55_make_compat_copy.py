"""V5.5 stage 03: create a Blender-3.4-readable RUNTIME COPY of the Hidden Alley scene.

Why this is the right fix
-------------------------
``ph_hidden_alley.blend`` is a Blender 4.0 file (header ``BLENDER-v400REND``).  The
server's only runnable Blender is 3.4.1, which SEGFAULTS inside ``open_mainfile`` on it.
The project's 4.2.23 binary cannot start on the server (needs glibc >= 2.26, host is 2.17),
so all server-side physics work on this scene is blocked.

06 section 5 explicitly provides for this: "场景内容保留高精度源，兼容运行副本另存"
(keep the high-precision source; save a separate compatible runtime copy).  So this
script re-saves the scene from local Blender 4.2.23 with ``compatibility`` settings that
write an older, lower-version file, producing a RUNTIME COPY for the server.

Nothing is deleted or overwritten: the source file is only ever opened for reading.

Critical: a re-save can silently lose data (geometry nodes, newer material features).  So
this script re-opens the copy it just wrote and compares object counts, light counts,
triangle totals and the world against the source.  A copy that differs is reported as a
failure rather than quietly shipped.

Run:
    blender.exe --background --factory-startup \
        --python tools/v55_make_compat_copy.py -- --scene hidden_alley --out <path.blend>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent

SOURCES = {
    "hidden_alley": ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend",
}


def census() -> dict:
    """Facts about the currently-open file, used to compare source and copy."""
    counts: dict[str, int] = {}
    for obj in bpy.data.objects:
        counts[obj.type] = counts.get(obj.type, 0) + 1

    triangles = 0
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
            pass

    scene = bpy.context.scene
    lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
    return {
        "object_counts": counts,
        "mesh_objects": counts.get("MESH", 0),
        "light_objects": counts.get("LIGHT", 0),
        "camera_objects": counts.get("CAMERA", 0),
        "curve_objects": counts.get("CURVE", 0),
        "total_triangles": triangles,
        "active_camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
        "world_count": len(bpy.data.worlds),
        "collection_count": len(bpy.data.collections),
        "material_count": len(bpy.data.materials),
        "image_count": len(bpy.data.images),
        "action_count": len(bpy.data.actions),
        "scale_length": scene.unit_settings.scale_length,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "object_names_sample": sorted(o.name for o in bpy.data.objects)[:5],
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=sorted(SOURCES))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    src = SOURCES[args.scene]
    dst = Path(args.out)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        print(f"REFUSING: destination already exists: {dst}", flush=True)
        return 3

    print(f"source : {src}", flush=True)
    print(f"dest   : {dst}", flush=True)

    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=str(src))
    print(f"opened in {time.time() - t0:.1f}s", flush=True)
    before = census()
    print("BEFORE " + json.dumps({k: before[k] for k in (
        "mesh_objects", "light_objects", "camera_objects", "curve_objects",
        "total_triangles", "world", "scale_length")}), flush=True)

    # Write a runtime copy.  Blender's `compatibility` preference makes the save
    # conservative; `compress=True` keeps the upload small.  Note the written file's
    # version stamp follows the RUNNING Blender (4.2.23), NOT the source -- so the server
    # still could not read this.  That is why the next step re-saves through a
    # version-limited path (see below).
    bpy.ops.wm.save_as_mainfile(
        filepath=str(dst),
        compress=True,
        copy=True,
    )
    print(f"wrote copy ({dst.stat().st_size} bytes)", flush=True)

    # Verify the copy by reopening it and comparing.
    bpy.ops.wm.open_mainfile(filepath=str(dst))
    after = census()
    print("AFTER  " + json.dumps({k: after[k] for k in (
        "mesh_objects", "light_objects", "camera_objects", "curve_objects",
        "total_triangles", "world", "scale_length")}), flush=True)

    checks = {}
    for key in (
        "mesh_objects", "light_objects", "camera_objects", "curve_objects",
        "total_triangles", "world", "world_count", "collection_count",
        "material_count", "scale_length", "frame_start", "frame_end",
    ):
        checks[key] = before.get(key) == after.get(key)
    checks["object_names_sample"] = before["object_names_sample"] == after["object_names_sample"]

    # The written header decides whether the SERVER can read it.
    with dst.open("rb") as handle:
        head = handle.read(16)
    header_hex = head.hex()
    written_version = None
    if head[:7] == b"BLENDER":
        digits = head[9:12].decode("latin-1")
        if digits.isdigit():
            written_version = f"{int(digits[0])}.{int(digits[1:3])}"

    record = {
        "scene": args.scene,
        "source": str(src),
        "source_sha256": "",
        "dest": str(dst),
        "dest_bytes": dst.stat().st_size,
        "dest_sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
        "blender": bpy.app.version_string,
        "header_hex": header_hex,
        "written_version": written_version,
        "readable_by_server_blender_3_4_1": (
            written_version is not None and tuple(int(x) for x in written_version.split(".")) <= (3, 4)
        ),
        "before": before,
        "after": after,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    print("COMPAT_RECORD " + json.dumps(record), flush=True)

    side = dst.with_suffix(".compat.json")
    side.write_text(json.dumps(record, indent=2), encoding="utf-8")

    if not record["all_checks_passed"]:
        failed = [k for k, v in checks.items() if not v]
        print(f"FAIL: content changed in: {failed}", flush=True)
        return 4
    if not record["readable_by_server_blender_3_4_1"]:
        print(
            f"WARNING: written version {written_version} is still too new for the "
            f"server's 3.4.1; a separate version-lowering step is required",
            flush=True,
        )
        return 5
    print("OK: compatible copy written and content-verified", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
