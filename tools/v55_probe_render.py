"""Isolate the Cycles render hang: render one frame of the runtime copy with a minimal script.

The stage-05 render script reaches the render call and then produces nothing at all, not even the
first `print` after `bpy.ops.render.render`. That means the call itself is not returning. This probe
reproduces the smallest possible version -- open the runtime copy, point the existing scene camera at
the props, render one small frame -- so the cause can be separated from the animation code.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import bpy

ROOT = Path(r"D:\workspace\project1_database")
RUNTIME = ROOT / "outcomes/v55/scenes/italian_flat/runtime/italian_flat_runtime.blend"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[0]) if argv else (ROOT / "outcomes/v55/italian_flat/box_hits_bottle/probe_frame.png")
ENGINE = argv[1] if len(argv) > 1 else "CYCLES"
RES = int(argv[2]) if len(argv) > 2 else 160
SPP = int(argv[3]) if len(argv) > 3 else 8

print("=" * 90)
print(f"probe: engine={ENGINE} res={RES}x{RES} spp={SPP}")
print(f"opening {RUNTIME.name}")
t = time.time()
bpy.ops.wm.open_mainfile(filepath=str(RUNTIME))
print(f"  opened in {time.time()-t:.1f} s")

scene = bpy.context.scene
print(f"  objects {len(scene.objects)}  engine currently {scene.render.engine}")
print(f"  cameras {[o.name for o in scene.objects if o.type == 'CAMERA']}")

# Use the scene's own camera so nothing about camera creation is involved.
cams = [o for o in scene.objects if o.type == "CAMERA"]
if not cams:
    raise SystemExit("no camera in the runtime copy")
scene.camera = cams[0]
print(f"  using camera {cams[0].name}")

scene.render.engine = ENGINE
scene.render.resolution_x = RES
scene.render.resolution_y = RES
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(OUT)
if ENGINE == "CYCLES":
    scene.cycles.device = "CPU"
    scene.cycles.samples = SPP
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 4
print(f"  configured; calling render now")

t = time.time()
try:
    bpy.ops.render.render(write_still=True)
    print(f"  render RETURNED in {time.time()-t:.1f} s")
except Exception as exc:
    print(f"  render RAISED after {time.time()-t:.1f} s: {type(exc).__name__}: {exc}")
    raise
print(f"  output exists: {OUT.is_file()}  "
      f"size {OUT.stat().st_size if OUT.is_file() else 0} bytes")
print("PROBE DONE")
