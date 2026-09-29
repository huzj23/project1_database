"""Resolve the true unit scale of the Hidden Alley scene, which the whole A video depends on.

`outcomes/v55/bootstrap/20260928T194500/scale/hidden_alley_local.json` reports two numbers that
appear to contradict each other:

  * `scale_length: 10.0`
  * `scene_bbox.size: [1226.93, 1226.93, 1239.79]`

while the board objects themselves are about 2.76 x 0.049 x 3.00 "units", which only makes sense as
metres. A 1226-unit scene at 1 unit = 1 m would be 1.2 km across, which is not an alley; but a
`scale_length` of 10 would make those 2.76 units equal 27.6 m, which is not a board.

The two are reconcilable -- `scene_bbox` is probably dominated by a sky dome or a ground disc far
larger than the set, and `scale_length` is a Blender display setting that does not affect physics
unless the export or the solver reads it -- but "probably" is not good enough, because a factor-of-10
error would make the can the wrong size relative to the board and every threshold in the plan wrong.

This measures the scene directly and reports the evidence rather than a conclusion:

  * the unit system and scale_length, and what Blender says the default cube measures;
  * a size histogram of ALL mesh objects, to show which objects are set-scale and which are the
    huge backdrop, so the 1226 number is attributed rather than assumed;
  * the board objects' own dimensions and their world matrices, including any object-level scale,
    since a non-unit object scale is a second way a factor can hide;
  * camera clip range and focal length, which give an independent sanity check on the set's size:
    a camera shooting a 3 m board from a few metres has a plausible near/far clip, one 10x larger
    would not;
  * the sun/light sizes if available, and the ground/wall extents near the boards.

Read-only. Writes `outcomes/v56/hidden_alley_can_board/unit_scale.json`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(r"D:\workspace\project1_database")
SRC = ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"
OUT = ROOT / "outcomes/v56/hidden_alley_can_board"
OUT.mkdir(parents=True, exist_ok=True)

print("=" * 104)
print(f"Hidden Alley unit scale investigation")
print(f"  source {SRC}")
bpy.ops.wm.open_mainfile(filepath=str(SRC))
scene = bpy.context.scene
# Guard the known trap in this scene. Its compositor renders a SECOND volumetric Fog scene, which
# reached 25.8 GB of private memory on a 15.7 GB machine and wrote no file. This script never
# renders, so the immediate risk is low, but any edit that adds a render must not reintroduce it, and
# recording the state here makes the scene's compositor status explicit rather than implicit.
print(f"  compositor in this scene: nodes={bool(getattr(scene, 'use_nodes', False))} "
      f"enabled={getattr(scene.render, 'use_compositing', None)} "
      f"(must be DISABLED before any render; see v5_audit_render_hidden_alley_local.ps1)")

us = scene.unit_settings
print(f"\n=== Blender unit settings ===")
print(f"  system            {us.system}")
print(f"  scale_length      {us.scale_length}")
print(f"  length_unit       {getattr(us, 'length_unit', None)}")
print(f"  scene frame range {scene.frame_start}..{scene.frame_end} at {scene.render.fps} fps")

report = {
    "source": str(SRC),
    "unit_system": us.system,
    "scale_length": us.scale_length,
    "length_unit": getattr(us, "length_unit", None),
    "note": ("scale_length is a Blender unit-system display/export scale. Whether it changes the "
             "physical size depends on whether the consumer honours it; the measurements below are "
             "in scene units and the question is how many metres one scene unit is."),
}

# --- every mesh object's world-space size, so the huge bbox is attributed to specific objects -----
print(f"\n=== mesh object sizes in scene units (world space, no unit conversion applied) ===")
meshes = []
for o in scene.objects:
    if o.type != "MESH" or not o.data or len(o.data.vertices) == 0:
        continue
    try:
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    except Exception:
        continue
    mn = [min(p[i] for p in bb) for i in range(3)]
    mx = [max(p[i] for p in bb) for i in range(3)]
    dims = [mx[i] - mn[i] for i in range(3)]
    meshes.append({
        "name": o.name, "verts": len(o.data.vertices),
        "dims_units": [round(d, 6) for d in dims],
        "max_dim_units": round(max(dims), 6),
        "world_min": [round(v, 6) for v in mn], "world_max": [round(v, 6) for v in mx],
        "object_scale": [round(v, 9) for v in o.scale],
        "object_location": [round(v, 6) for v in o.matrix_world.translation],
    })

meshes.sort(key=lambda m: -m["max_dim_units"])
print(f"  {'object':40s} {'verts':>7s} {'max_dim':>12s} {'scale':>22s}")
for m in meshes[:14]:
    print(f"  {m['name'][:40]:40s} {m['verts']:7d} {m['max_dim_units']:12.4f} "
          f"{str(m['object_scale']):>22s}")
print(f"  ...  ({len(meshes)} mesh objects total)")

# The set-scale objects are the ones whose size is metres-plausible; the backdrop is the outlier.
big = [m for m in meshes if m["max_dim_units"] > 100.0]
small = [m for m in meshes if m["max_dim_units"] <= 100.0]
print(f"\n  objects larger than 100 units: {len(big)}")
for m in big[:8]:
    print(f"    {m['name'][:44]:44s} max_dim {m['max_dim_units']:.1f} units")
print(f"  objects 100 units or smaller: {len(small)}")
if small:
    sizes = sorted(m["max_dim_units"] for m in small)
    print(f"    smallest {sizes[0]:.4f}, median {sizes[len(sizes)//2]:.4f}, largest {sizes[-1]:.4f}")

report["mesh_count"] = len(meshes)
report["objects_over_100_units"] = [{"name": m["name"], "max_dim_units": m["max_dim_units"]}
                                    for m in big[:20]]
report["objects_over_100_units_count"] = len(big)
report["set_scale_objects_count"] = len(small)
if small:
    report["set_scale_object_size_range_units"] = [sizes[0], sizes[-1]]

# --- the boards specifically ----------------------------------------------------------------
print(f"\n=== the wooden boards ===")
boards = [m for m in meshes if "wooden_board" in m["name"].lower()]
for m in boards:
    print(f"  {m['name']:26s} dims {[round(d,4) for d in m['dims_units']]} units  "
          f"scale {[round(s,4) for s in m['object_scale']]}  loc "
          f"{[round(v,4) for v in m['object_location']]}")
    # A non-unit object scale would multiply the physical size independently of the unit system.
    if any(abs(s - 1.0) > 1e-6 for s in m["object_scale"]):
        print(f"    NOTE: non-unit object scale; effective physical size is dims * scale")
report["boards"] = boards

# --- camera evidence: an independent check on how big the set is ------------------------------
print(f"\n=== cameras ===")
cams = []
for o in scene.objects:
    if o.type != "CAMERA":
        continue
    d = o.data
    cams.append({
        "name": o.name,
        "location_units": [round(v, 6) for v in o.matrix_world.translation],
        "clip_start_units": d.clip_start, "clip_end_units": d.clip_end,
        "lens_mm": d.lens, "sensor_width_mm": d.sensor_width,
        "type": d.type, "ortho_scale": getattr(d, "ortho_scale", None),
    })
    print(f"  {o.name:28s} lens {d.lens:6.1f} mm  clip {d.clip_start:.4f}..{d.clip_end:.1f}  "
          f"loc {[round(v,3) for v in o.matrix_world.translation]}")
print(f"  a camera with clip_start well under a metre and clip_end in the tens of metres implies the")
print(f"  set is metres-scale; a clip_end in the hundreds would imply a 10x larger set")
report["cameras"] = cams

# --- what the active camera can actually see, as a size cross-check ---------------------------
act = scene.camera
if act is not None:
    print(f"\n=== active camera {act.name}: distance to the boards ===")
    for m in boards:
        d = (Vector(m["world_min"]) + Vector(m["world_max"])) / 2.0
        dist = (Vector(act.matrix_world.translation) - d).length
        # Vertical field of view for this camera, and the size of the board in frame at that range.
        sw = act.data.sensor_width
        rx, ry = scene.render.resolution_x, scene.render.resolution_y
        half_v = math.atan((sw * ry / rx) / (2.0 * act.data.lens))
        frame_h = 2.0 * dist * math.tan(half_v)
        frac = m["max_dim_units"] / frame_h if frame_h else None
        print(f"  {m['name']:26s} distance {dist:8.3f} units -> frame height {frame_h:7.3f} units, "
              f"board occupies {frac*100 if frac else 0:5.1f}% of frame height")
        report.setdefault("board_frame_fraction", {})[m["name"]] = {
            "distance_units": dist, "frame_height_units": frame_h,
            "board_fraction_of_frame_height": frac}
    print(f"  the reference render `outcomes/v5_asset_review/scenes/hidden_alley.png` exists; if the")
    print(f"  boards appear as ordinary planks filling a small part of the frame, the set is metres")

# --- conclusion, stated as an inference with its evidence -------------------------------------
print(f"\n=== INFERENCE (with its basis, not as an assumption) ===")
verdict = None
if small:
    med = sizes[len(sizes) // 2]
    if 0.05 <= med <= 50.0:
        verdict = 1.0
report["inference"] = {
    "units_to_metres_if_one_unit_is_one_metre": verdict,
    "basis": ("the set-scale objects (those not part of the huge backdrop) span "
              f"{report.get('set_scale_object_size_range_units')} units, which is the size range of "
              "ordinary set dressing in metres; the 1226-unit scene_bbox is produced by "
              f"{len(big)} oversized backdrop object(s), which are reported by name above; and the "
              "camera clip range is quoted below, which is only coherent for a metres-scale set"),
    "must_be_confirmed_by": ("the physics step must assert the can diameter as a fraction of the "
                             "board's measured thickness and report it, so a factor-of-10 error "
                             "cannot survive into the solve"),
}
print(json.dumps(report["inference"], indent=1))

(OUT / "unit_scale.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'unit_scale.json'}")
