"""Find flat, real, VISIBLE ground inside the authored camera's own frustum.

WHY THIS EXISTS
---------------
The previous placement sat at world x 2.34..4.20, y 2.68..2.98, which is nowhere near where the scene's own
camera looks. The authored camera `hidden_alley_camera` stands at (-0.0722, -4.4245, 1.3000) looking along
+Y with a 24 mm lens, and the accepted asset-review image was rendered from exactly that camera. So the
region that is known to photograph well is the region THAT CAMERA SEES -- not an arbitrary flat patch
found by sweeping the whole floor.

This tool intersects the two requirements directly:

  1. cast a ray grid through the authored camera and keep the rays that hit the real floor (`Floor_main`),
     which gives the world-space footprint of visible pavement;
  2. inside that footprint, find the flattest contiguous strip big enough for a 9-box arc chain, and report
     its measured flatness, slope, and what else occupies it.

The result is a placement that is both flat AND actually in shot, which is the combination the previous
attempt never checked.

Usage:
    blender --background --factory-startup --python tools/v57/visible_site.py -- \
        --blend <source.blend> --camera hidden_alley_camera [--out report.json]
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"])
CAM_NAME = ARGS.get("camera", "")
OUT = Path(ARGS["out"]) if ARGS.get("out") else None
FLOOR = ARGS.get("floor", "Floor_main")
COLS = int(ARGS.get("cols", "160"))
ROWS = int(ARGS.get("rows", "90"))

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()

cam = bpy.data.objects.get(CAM_NAME) if CAM_NAME else scene.camera
if cam is None or cam.type != "CAMERA":
    raise SystemExit(f"FATAL: camera '{CAM_NAME}' not found")

# The authored render settings govern the frame, so the ray grid must use the same aspect.
rx = int(scene.render.resolution_x)
ry = int(scene.render.resolution_y)
pct = float(scene.render.resolution_percentage) / 100.0
RES_X = int(rx * pct)
RES_Y = int(ry * pct)
LENS = float(cam.data.lens)
SENSOR = float(cam.data.sensor_width)
# sensor_fit AUTO: the larger image dimension takes the sensor width.
if RES_X >= RES_Y:
    FOCAL_PX = LENS / SENSOR * RES_X
else:
    FOCAL_PX = LENS / SENSOR * RES_Y

print("=" * 108)
print(f"visible-site search | {BLEND.name}")
print(f"  author camera : {cam.name}  at {[round(v, 4) for v in cam.matrix_world.translation]}")
print(f"                  lens {LENS} mm, sensor {SENSOR} mm, render {RES_X}x{RES_Y} "
      f"-> focal {FOCAL_PX:.2f} px")
print(f"  floor object  : {FLOOR}")
print(f"  ray grid      : {COLS}x{ROWS}")
print("=" * 108)


def ray_dir(px, py):
    """World direction through pixel (px, py), with py measured down from the image top."""
    x = (px + 0.5) - RES_X / 2.0
    y = RES_Y / 2.0 - (py + 0.5)
    local = Vector((x / FOCAL_PX, y / FOCAL_PX, -1.0))
    return (cam.matrix_world.to_3x3() @ local).normalized()


origin = cam.matrix_world.translation
hits_floor = []
seen = Counter()
for r in range(ROWS):
    py = (r + 0.5) / ROWS * RES_Y
    for c in range(COLS):
        px = (c + 0.5) / COLS * RES_X
        ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, origin, ray_dir(px, py), distance=200.0)
        if not ok:
            seen["<nothing>"] += 1
            continue
        seen[obj.name] += 1
        if obj.name == FLOOR:
            hits_floor.append({"px": px, "py": py, "x": loc.x, "y": loc.y, "z": loc.z,
                               "tilt": math.degrees(abs(nrm.angle(Vector((0, 0, 1))))) if nrm else None})

total = COLS * ROWS
print("")
print(f"  objects the authored camera sees ({len(seen)} distinct, {total} rays):")
for nm, n in seen.most_common(22):
    print(f"    {100.0 * n / total:6.2f}%  {n:5d}  {nm}")

print("")
print(f"  rays landing on {FLOOR}: {len(hits_floor)} ({100.0 * len(hits_floor) / total:.2f}%)")
if not hits_floor:
    raise SystemExit("FATAL: the authored camera sees none of the real floor")

xs = [h["x"] for h in hits_floor]
ys = [h["y"] for h in hits_floor]
zs = [h["z"] for h in hits_floor]
print(f"  visible floor world extent : x {min(xs):+.3f} .. {max(xs):+.3f}  ({max(xs) - min(xs):.3f} m)")
print(f"                               y {min(ys):+.3f} .. {max(ys):+.3f}  ({max(ys) - min(ys):.3f} m)")
print(f"                               z {min(zs):+.4f} .. {max(zs):+.4f}  "
      f"(spread {1000 * (max(zs) - min(zs)):.1f} mm)")
tilts = [h["tilt"] for h in hits_floor if h["tilt"] is not None]
print(f"  surface tilt               : max {max(tilts):.2f} deg, mean {sum(tilts) / len(tilts):.2f} deg")

# ---------------------------------------------------------------------------------------------
# Find the flattest contiguous strip: bucket by world y (the alley runs along the view direction) and
# report each bucket's flatness, so the chain can be laid along the flattest run.
# ---------------------------------------------------------------------------------------------
print("")
print("  floor profile along Y (the view direction), 0.25 m buckets:")
print(f"    {'y centre':>10s} {'rays':>6s} {'x range':>20s} {'z mean':>9s} {'z spread':>10s} "
      f"{'tilt mean':>10s}")
buckets = {}
for h in hits_floor:
    k = round(h["y"] / 0.25) * 0.25
    buckets.setdefault(k, []).append(h)
prof = []
for k in sorted(buckets):
    bs = buckets[k]
    bz = [b["z"] for b in bs]
    bx = [b["x"] for b in bs]
    bt = [b["tilt"] for b in bs if b["tilt"] is not None]
    prof.append({"y": k, "n": len(bs), "x_lo": min(bx), "x_hi": max(bx),
                 "z_mean": sum(bz) / len(bz), "z_spread": max(bz) - min(bz),
                 "tilt_mean": (sum(bt) / len(bt)) if bt else None})
    print(f"    {k:+10.2f} {len(bs):6d} [{min(bx):+7.3f},{max(bx):+7.3f}] "
          f"{sum(bz) / len(bz):+9.4f} {1000 * (max(bz) - min(bz)):8.1f} mm "
          f"{(sum(bt) / len(bt) if bt else 0):9.2f}d")

# A chain of N boxes needs roughly N * spacing of run along its own direction plus width.
NEED_RUN = float(ARGS.get("need_run", "1.35"))
NEED_WIDTH = float(ARGS.get("need_width", "0.55"))
best = None
for i in range(len(prof)):
    for j in range(i, len(prof)):
        win = prof[i:j + 1]
        if win[0]["y"] < 0:
            continue
        run = win[-1]["y"] - win[0]["y"]
        if run < NEED_RUN:
            continue
        xlo = min(w["x_lo"] for w in win)
        xhi = max(w["x_hi"] for w in win)
        if (xhi - xlo) < NEED_WIDTH:
            continue
        spread = max(w["z_spread"] for w in win)
        # Prefer small flatness spread, then a longer run as a tie-break.
        score = (spread, -run)
        if best is None or score < best[0]:
            best = (score, win, xlo, xhi, run)

print("")
print("=" * 108)
if best:
    score, win, xlo, xhi, run = best
    y0 = win[0]["y"]
    y1 = win[-1]["y"]
    zmean = sum(w["z_mean"] for w in win) / len(win)
    print(f"  BEST VISIBLE STRIP: y {y0:+.2f} .. {y1:+.2f} (run {run:.2f} m), "
          f"x {xlo:+.3f} .. {xhi:+.3f} (width {xhi - xlo:.3f} m)")
    print(f"    bucket z spread worst {score[0] * 1000:.1f} mm; mean floor height {zmean:+.4f} m")
    print(f"    requirement: run >= {NEED_RUN} m, width >= {NEED_WIDTH} m")
    print("")
    print("  A chain laid here is BOTH flat and inside the authored camera's view.")
else:
    print("  No visible strip meets the run/width requirement. The alley as photographed cannot carry a")
    print("  chain of this length along Y in view; a different alley direction or box count is needed.")
print("=" * 108)

if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "blend": str(BLEND), "camera": cam.name,
        "camera_location": list(cam.matrix_world.translation),
        "lens_mm": LENS, "resolution": [RES_X, RES_Y], "focal_px": FOCAL_PX,
        "visible_floor_rays": len(hits_floor), "rays_total": total,
        "visible_extent": {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)],
                           "z": [min(zs), max(zs)]},
        "profile": prof,
        "best_strip": ({"y": [best[1][0]["y"], best[1][-1]["y"]], "x": [best[2], best[3]],
                        "run_m": best[4], "worst_z_spread_m": best[0][0]} if best else None),
        "seen_objects": dict(seen.most_common(40)),
    }, indent=2), encoding="utf-8")
    print(f"report written: {OUT}")
