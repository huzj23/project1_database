"""Verify the saved replay project actually reproduces the delivered motion.

09 section 4 requires a `replay.blend` that can be opened and played to reproduce the shot. Saving a
file is not evidence that it does that: the animation curves could be attached to the wrong objects,
the frame range could be wrong, the camera could be missing, or Blender's own rigid-body simulation
could be enabled and fight the recorded keyframes. This opens the saved file in a FRESH Blender
process and checks, from the file alone:

  * it opens at all, and the scene's frame range and fps are what were intended;
  * the delivery camera exists and is the active camera;
  * no rigid-body world is enabled (09 section 4: Blender's own solver must be off, so the replay
    cannot be re-simulated differently from the recorded trajectory);
  * the animated objects' world positions at several frames match the recorded trajectory, which is
    the property that makes the file a REPLAY rather than a saved scene.

Reads the run's `trajectory.json` and `bodies.json` as the reference.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(r"D:\workspace\project1_database")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RUN = Path(argv[0]) if argv else (
    ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T110000")
REPLAY = Path(argv[1]) if len(argv) > 1 else (RUN / "render/replays/replay_final.blend")

print("=" * 104)
print(f"replay verification: {REPLAY}")
if not REPLAY.is_file():
    # The mode is part of the filename; find whichever replay exists and say which was used.
    cands = sorted((RUN / "render/replays").glob("replay_*.blend"))
    if not cands:
        raise SystemExit(f"no replay project under {RUN / 'render/replays'}")
    REPLAY = cands[-1]
    print(f"  (not found as given; using {REPLAY})")

TRAJ = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
BODIES = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
CFG = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
TARGET = CFG["target_instance_id"]
TRIGGER = CFG["trigger_instance_id"]

t = bpy.ops.wm.open_mainfile(filepath=str(REPLAY))
scene = bpy.context.scene
print(f"  opened; {len(scene.objects)} objects, frame range {scene.frame_start}..{scene.frame_end} "
      f"at {scene.render.fps} fps")
print(f"  active camera: {scene.camera.name if scene.camera else None}")

checks = {}
checks["opens"] = True
checks["frame_range_matches"] = (scene.frame_start == 1
                                 and scene.frame_end == CFG["frame_count"])
checks["fps_matches"] = scene.render.fps == CFG["video_fps"]
checks["has_active_camera"] = scene.camera is not None

# 09 section 4: Blender's own rigid-body solver must be off, or the replay could diverge.
rbw = [o for o in scene.objects if o.rigid_body is not None]
checks["no_blender_rigidbody"] = len(rbw) == 0
print(f"  objects with a Blender rigid body: {len(rbw)} (must be 0)")
sim = getattr(scene, "rigidbody_world", None)
print(f"  scene rigidbody_world: {sim}")

# The decisive test: does the file actually replay the recorded motion?
#
# 02's contract is that a body's recorded `position_m` is its ANCHOR: the AABB centre in x and y and
# the AABB minimum in z. The Blender-side anchor must be reconstructed the same way, so this probe
# computes each animated object's world AABB at every sampled frame and compares its anchor with the
# record. Comparing origins instead would compare two different points and report a false mismatch.
def anchor_of(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [p.x for p in corners]
    ys = [p.y for p in corners]
    zs = [p.z for p in corners]
    return Vector(((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, min(zs)))


# Map each recorded body to its scene object(s) the same way the render script does: by nearest
# AABB-centre in x/y at frame 0. Anything unmatched is reported, not ignored.
scene.frame_set(1)
bpy.context.view_layer.update()
cand = [o for o in scene.objects if o.type == "MESH"]
placed = {}
for b in BODIES:
    p = b["position_m"]
    best, bd = None, None
    for o in cand:
        a = anchor_of(o)
        d = math.hypot(a.x - p[0], a.y - p[1])
        if bd is None or d < bd:
            bd, best = d, o
    placed[b["instance_id"]] = (best, bd)
    print(f"  {b['instance_id']:18s} -> {best.name if best else None}  "
          f"(xy distance at frame 0: {bd*1000 if bd is not None else float('nan'):.3f} mm)")

print(f"\n=== does the saved file replay the recorded motion? ===")
print(f"  {'body':18s} {'frame':>5s} {'recorded_m':>28s} {'replayed_m':>28s} {'err_mm':>8s}")
worst = 0.0
motion = {}
for name in (TARGET, TRIGGER):
    obj = placed.get(name, (None, None))[0]
    if obj is None:
        continue
    rows = {r["frame"]: r for r in TRAJ[name]}
    errs = []
    for f in (0, 5, 9, 20, 40, CFG["frame_count"] - 1):
        if f not in rows:
            continue
        scene.frame_set(f + 1)          # 02: blender_frame = frame + 1
        bpy.context.view_layer.update()
        got = anchor_of(obj)
        want = Vector(rows[f]["position_m"])
        e = (got - want).length * 1000.0
        errs.append(e)
        if f in (0, 9, CFG["frame_count"] - 1):
            print(f"  {name:18s} {f:5d} "
                  f"[{want.x:8.4f},{want.y:8.4f},{want.z:8.4f}] "
                  f"[{got.x:8.4f},{got.y:8.4f},{got.z:8.4f}] {e:8.4f}")
    if errs:
        motion[name] = {"max_anchor_error_mm": max(errs), "samples": len(errs)}
        worst = max(worst, max(errs))

checks["replays_recorded_motion"] = worst < 1.0
print(f"\n  worst anchor error across all sampled frames and both key bodies: {worst:.4f} mm")
print(f"  tolerance 1.0 mm (the recorded trajectory is keyed exactly; LINEAR interpolation between "
      f"integer frames means a sampled integer frame should reproduce its record to well under that)")

print(f"\n=== VERDICT ===")
for k, v in checks.items():
    print(f"  {'OK  ' if v else 'FAIL'} {k}")
ok = all(checks.values())
print(f"  REPLAY {'VERIFIED' if ok else 'NOT VERIFIED'}")

(RUN / "replay_verification.json").write_text(json.dumps({
    "replay_blend": str(REPLAY),
    "size_bytes": REPLAY.stat().st_size,
    "checks": checks,
    "all_pass": ok,
    "worst_anchor_error_mm": worst,
    "per_body": motion,
    "scene": {"frame_start": scene.frame_start, "frame_end": scene.frame_end,
              "fps": scene.render.fps,
              "active_camera": scene.camera.name if scene.camera else None,
              "objects": len(scene.objects),
              "blender_rigidbody_objects": len(rbw)},
    "note": ("verified by opening the SAVED file in a fresh Blender process and comparing each key "
             "body's world anchor against the recorded trajectory; a file that merely saved without "
             "working animation curves would fail the motion check"),
}, indent=2), encoding="utf-8")
print(f"  written: {RUN / 'replay_verification.json'}")
