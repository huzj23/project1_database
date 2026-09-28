"""V5.5 stage 03: local baseline render of the Hidden Alley scene.

Why
---
The server can only run Blender 3.4.1, and ``ph_hidden_alley.blend`` is a Blender 4.0
file that 3.4.1 cannot read (it segfaults inside the file read; header bytes are
"BLENDER-v400REND").  06 section 4 designates the validated local Blender 4.2.23 as the
render route, and local compute must run under tmux.

This script renders a single low-cost frame from the AUTHORED camera with the AUTHORED
lighting, at reduced resolution/samples, to prove the route works and to capture a
baseline for the compatibility check 06 section 4 requires ("不能仅凭打开没报错视为兼容").

It deliberately does NOT modify the source: it opens the file, changes only render
settings in memory, renders, and exits.  Nothing is saved back to the .blend.

Run:
    blender.exe --background --factory-startup \
        --python tools/v55_local_baseline_render.py -- --scene hidden_alley --out <png>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent

SCENES = {
    "italian_flat": ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend",
    "hidden_alley": ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend",
    "the_shed": ROOT / "models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend",
}


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=sorted(SCENES))
    ap.add_argument("--out", required=True)
    ap.add_argument("--camera", default=None, help="camera object name; default = active")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--samples", type=int, default=8)
    args = ap.parse_args(argv)

    path = SCENES[args.scene]
    out_png = Path(args.out)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    print(f"opening {path}", flush=True)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=str(path))
    open_s = time.time() - t0

    scene = bpy.context.scene

    # Use the authored camera unless one is named explicitly.
    camera = bpy.data.objects.get(args.camera) if args.camera else scene.camera
    if camera is None:
        print("ERROR: no camera available", flush=True)
        return 2
    scene.camera = camera

    # The authored Fog compositor is known to need ~25.8 GiB; 06 s.1 records that it was
    # already reviewed and turned OFF for the accepted single frame.  Reproduce that
    # reviewed state here rather than inventing a new one.
    scene.use_nodes = False
    compositor_state = "disabled"

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = False
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(out_png)

    # A fixed frame keeps the baseline reproducible.
    scene.frame_set(scene.frame_start)

    lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    print(f"camera={camera.name} lights={len(lights)} meshes={len(meshes)}", flush=True)
    print(f"world={scene.world.name if scene.world else None} compositor={compositor_state}", flush=True)
    print(f"res={args.width}x{args.height} samples={args.samples} frame={scene.frame_current}", flush=True)

    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    render_s = time.time() - t1

    record = {
        "scene": args.scene,
        "source": str(path),
        "blender": bpy.app.version_string,
        "camera": camera.name,
        "light_count": len(lights),
        "mesh_count": len(meshes),
        "world": scene.world.name if scene.world else None,
        "compositor": compositor_state,
        "resolution": [args.width, args.height],
        "samples": args.samples,
        "frame": scene.frame_current,
        "open_seconds": round(open_s, 2),
        "render_seconds": round(render_s, 2),
        "output": str(out_png),
        "output_exists": out_png.is_file(),
        "output_bytes": out_png.stat().st_size if out_png.is_file() else 0,
    }
    print("BASELINE_RECORD " + json.dumps(record), flush=True)

    side = out_png.with_suffix(".json")
    side.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
