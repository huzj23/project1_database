"""V5.6 generic replay renderer, shared by video A and video B.

One entry point, two scene configs -- as the plan's section 9 asks, instead of more one-off scripts.

WHAT IT DOES, in order:

  1. opens the scene's runtime copy (opened FRESH, before any layer build);
  2. binds scene objects to solver bodies by STABLE ID from the config, never by nearest-in-XY.
     A body with no bound object is a hard failure: rendering a partial replay is worse than not
     rendering;
  3. captures `T_WV(0)` per body from the file and keeps it fixed, then drives the visual with
     `T_WV(t) = T_WB(t) @ inverse(T_WB(0)) @ T_WV(0)`. No AABB of the visual is ever consulted for
     the body frame, which is what removes the 52 mm lift class of error;
  4. picks >=8 fixed local reference points per body and records them, so verification compares the
     same material points at every frame rather than a bounding box;
  5. FAILS STOP if the built animation does not reproduce the record within 1 mm -- it does not
     proceed to render, so a broken animation can never reach a delivered frame;
  6. renders the requested pass, with the modes and cost discipline section 8 asks for.

Reference points are taken from the VISUAL mesh's own vertices spread across its extent, so they are
real material points. The verification in `verify_replay.py` then re-derives their world positions
from the matrix chain and compares against what the saved file produces.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

# ---------------------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------------------

argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
ARGS = {"mode": "probe", "threads": "8", "res": "960x540", "spp": "16", "framelist": ""}
i = 0
while i < len(argv):
    if argv[i].startswith("--"):
        k = argv[i][2:]
        v = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else "1"
        ARGS[k] = v
        i += 2
    else:
        i += 1

RUN = Path(ARGS["run"])
CFG_P = Path(ARGS.get("config", str(RUN / "resolved_config.json")))
MODE = ARGS["mode"]
THREADS = int(ARGS["threads"])
RES_X, RES_Y = (int(v) for v in ARGS["res"].lower().split("x"))
SPP = int(ARGS["spp"])

CFG = json.loads(CFG_P.read_text(encoding="utf-8"))
OUT = Path(ARGS.get("out", str(RUN / "render")))
OUT.mkdir(parents=True, exist_ok=True)

FRAME_COUNT = int(CFG["frame_count"])
VIDEO_FPS = int(CFG["video_fps"])
RUNTIME_BLEND = Path(CFG["runtime_blend"])

FRAME_LIST = ([int(v) for v in ARGS["framelist"].split(",") if v.strip()]
              if ARGS["framelist"] else list(range(FRAME_COUNT)))

print("=" * 104)
print(f"V5.6 replay render | mode={MODE} {RES_X}x{RES_Y} {SPP}spp threads={THREADS}")
print(f"  run     {RUN}")
print(f"  config  {CFG_P}")
print(f"  scene   {CFG['scene_id']}  runtime {RUNTIME_BLEND.name}")
print(f"  frames  0..{FRAME_COUNT - 1} at {VIDEO_FPS} fps -> {FRAME_COUNT / VIDEO_FPS:.3f} s")

TRAJ = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
BINDING_CFG = CFG["binding"]                 # body_id -> {"objects": [...], "collision_obj": name}

# ---------------------------------------------------------------------------------------
# open the runtime copy
# ---------------------------------------------------------------------------------------

if not RUNTIME_BLEND.is_file():
    raise SystemExit(f"FATAL: runtime copy missing: {RUNTIME_BLEND}")
print(f"\n=== opening {RUNTIME_BLEND.name} ({RUNTIME_BLEND.stat().st_size / 1e6:.1f} MB) ===")
bpy.ops.wm.open_mainfile(filepath=str(RUNTIME_BLEND))
scene = bpy.context.scene
print(f"  objects {len(scene.objects)}  frame range {scene.frame_start}..{scene.frame_end}  "
      f"fps {scene.render.fps}")
scene.frame_start = 1
scene.frame_end = FRAME_COUNT
scene.render.fps = VIDEO_FPS

# ---------------------------------------------------------------------------------------
# bind bodies to objects by STABLE ID
# ---------------------------------------------------------------------------------------
#
# Section 3.2 forbids the old "nearest in XY" matching. Binding is read from the config, which names
# the source object id per body, so a rebuild of the scene cannot silently rebind a body to a
# different object. Every body must resolve or the run stops.

print("\n=== binding bodies to objects by stable id ===")
missing_objects = []
binding = {}
for body_id, spec in BINDING_CFG.items():
    objs = []
    for nm in spec["objects"]:
        o = bpy.data.objects.get(nm)
        if o is None:
            missing_objects.append((body_id, nm))
            continue
        objs.append(o)
    collision_obj = spec.get("collision_obj")
    binding[body_id] = {"objects": [o.name for o in objs], "collision_obj": collision_obj,
                       "source_object_id": spec.get("source_object_id")}
    print(f"  {body_id:20s} -> {[o.name for o in objs]}  (collision {collision_obj})")
if missing_objects:
    raise SystemExit(f"FATAL: config names objects that are not in the runtime copy: "
                     f"{missing_objects}. Refusing to render a partial replay.")
for body_id in TRAJ:
    if body_id not in binding:
        raise SystemExit(f"FATAL: trajectory has body '{body_id}' but the config does not bind it; "
                         f"a body that cannot be placed must not be silently skipped")

# Detach animated objects from parents, preserving their world pose, because the trajectory is in
# world space and a parented object's local matrix means something different.
for body_id, spec in binding.items():
    for nm in spec["objects"]:
        o = bpy.data.objects[nm]
        if o.parent is not None:
            keep = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = keep
            print(f"  (detached {o.name} from its parent; world pose unchanged)")

# ---------------------------------------------------------------------------------------
# capture the initial visual matrices T_WV(0) and build the animation
# ---------------------------------------------------------------------------------------

print("\n=== building the animation from the recorded trajectory ===")


def q_xyzw_to_blender(q):
    """The project stores xyzw; Blender wants wxyz. Converted once, explicitly, at the boundary."""
    x, y, z, w = (float(c) for c in q)
    return Quaternion((w, x, y, z))


def t_wb(row):
    return (Matrix.Translation(Vector(row["position_m"]))
            @ q_xyzw_to_blender(row["quaternion_xyzw"]).to_matrix().to_4x4())


anim_report = {}
for body_id, spec in binding.items():
    rows = TRAJ[body_id]
    # T_WV(0) is captured BEFORE anything is animated, from the scene as authored. It carries the
    # authored scale and any local offset, and it is never recomputed.
    scene.frame_set(1)
    bpy.context.view_layer.update()
    t_wv0 = {nm: bpy.data.objects[nm].matrix_world.copy() for nm in spec["objects"]}
    t_wb0 = t_wb(rows[0])

    for nm in spec["objects"]:
        o = bpy.data.objects[nm]
        o.rotation_mode = "QUATERNION"
        for r in rows:
            f = int(r["blender_frame"])
            scene.frame_set(f)                     # FIRST: advance time and re-evaluate
            delta = t_wb(r) @ t_wb0.inverted()      # the body's rigid motion since frame 0
            o.matrix_world = delta @ t_wv0[nm]      # THEN: write this frame's pose
            o.keyframe_insert("location", frame=f)
            o.keyframe_insert("rotation_quaternion", frame=f)
            o.keyframe_insert("scale", frame=f)
    anim_report[body_id] = {"objects": spec["objects"], "keys": len(rows),
                            "frames": [int(rows[0]["blender_frame"]), int(rows[-1]["blender_frame"])]}
    print(f"  {body_id:20s} {len(rows)} keys over {spec['objects']}")

# LINEAR interpolation: the states are already at video-frame resolution and a Bezier curve would
# overshoot between them, so the rendered motion would no longer be the solved motion.
n_curves = 0
for body_id, spec in binding.items():
    for nm in spec["objects"]:
        ad = bpy.data.objects[nm].animation_data
        if not ad or not ad.action:
            continue
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            n_curves += 1
print(f"  {n_curves} f-curves set to LINEAR")

# ---------------------------------------------------------------------------------------
# fixed local reference points, recorded for verification
# ---------------------------------------------------------------------------------------
#
# Section 3.3: >=8 fixed points per body, chosen once in the body's local frame. They are taken from
# the visual mesh's own vertices so each is a real material point, spread across the extent so that a
# rotational error cannot hide. They are written to disk and the verifier re-derives them; the
# renderer does not verify itself against its own numbers.

print("\n=== fixed local reference points ===")
# Points are stored PER OBJECT, in that object's own local frame. A body may be an assembly of
# several visual objects, and each has its own local frame; applying one object's local points to
# another's matrix would compare two different material points. Storing them per object keeps the
# prediction `delta @ T_WV0[obj] @ lp` well defined for every member.
refpts = {}
for body_id, spec in binding.items():
    per_obj = {}
    for nm in spec["objects"]:
        o = bpy.data.objects[nm]
        verts = [v.co for v in o.data.vertices]
        if not verts:
            continue
        # Extreme points along each axis are stable, well-separated material points; choosing them by
        # sorted order avoids depending on vertex ordering or on a mesh being indexed a given way.
        sx = sorted(verts, key=lambda v: v.x)
        sy = sorted(verts, key=lambda v: v.y)
        sz = sorted(verts, key=lambda v: v.z)
        mn = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
        mx = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
        cand = [sx[0], sx[-1], sy[0], sy[-1], sz[0], sz[-1], sx[len(sx) // 2], sy[len(sy) // 2],
                mn, mx, Vector((mn.x, mn.y, mx.z)), Vector((mx.x, mx.y, mn.z)),
                Vector((mn.x, mx.y, mn.z)), Vector((mx.x, mn.y, mx.z))]
        uniq = []
        for v in cand:
            p = [float(v.x), float(v.y), float(v.z)]
            if not any(max(abs(a - b) for a, b in zip(p, s)) < 1e-9 for s in uniq):
                uniq.append(p)
        if len(uniq) < 8:
            raise SystemExit(f"FATAL: object '{nm}' of body '{body_id}' yielded only {len(uniq)} "
                             f"distinct reference points; section 3.3 requires at least 8")
        per_obj[nm] = uniq[:12]
    if not per_obj:
        raise SystemExit(f"FATAL: body '{body_id}' produced no reference points at all")
    total = sum(len(v) for v in per_obj.values())
    refpts[body_id] = {
        "points_per_object": per_obj,
        "object_count": len(per_obj), "point_count": total,
        "note": ("each list is in that object's OWN local frame; the verifier predicts world "
                 "positions from T_WB(t) @ inv(T_WB(0)) @ T_WV0(obj) and compares with the saved "
                 "file, so the comparison is between the same material points at every frame"),
    }
    print(f"  {body_id:20s} {len(per_obj)} object(s), {total} points "
          f"({', '.join(f'{k}:{len(v)}' for k, v in per_obj.items())})")

# ---------------------------------------------------------------------------------------
# FAIL-STOP verification of the built animation, before anything is rendered
# ---------------------------------------------------------------------------------------

print("\n=== animation verification (fail-stop: a failure here renders nothing) ===")
scene.frame_set(1)
bpy.context.view_layer.update()
t_wv0_all = {bid: {nm: bpy.data.objects[nm].matrix_world.copy() for nm in spec["objects"]}
             for bid, spec in binding.items()}

fails = []
anim_checks = {}
for body_id, spec in binding.items():
    rows = TRAJ[body_id]
    t_wb0 = t_wb(rows[0])
    worst = 0.0
    worst_f = None
    for r in rows:
        delta = t_wb(r) @ t_wb0.inverted()
        f = int(r["blender_frame"])
        scene.frame_set(f)
        bpy.context.view_layer.update()
        for nm in spec["objects"]:
            o = bpy.data.objects[nm]
            predicted = delta @ t_wv0_all[body_id][nm]
            for lp in refpts[body_id]["points_per_object"][nm]:
                d = ((predicted @ Vector(lp)) - (o.matrix_world @ Vector(lp))).length
                if d > worst:
                    worst, worst_f = d, f
    ok = worst <= 0.001
    anim_checks[body_id] = {"worst_reference_error_m": worst, "worst_frame": worst_f, "pass": ok}
    print(f"  {'PASS' if ok else 'FAIL'}  {body_id:20s} worst {worst * 1000:.6f} mm"
          + (f" at frame {worst_f}" if worst_f else ""))
    if not ok:
        fails.append(f"{body_id}: {worst * 1000:.3f} mm > 1 mm")

# A frozen animation is the failure an earlier version shipped, so it is checked explicitly: every
# animated object must actually take distinct poses across the clip.
for body_id, spec in binding.items():
    poses = set()
    for f in range(1, FRAME_COUNT + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        for nm in spec["objects"]:
            m = bpy.data.objects[nm].matrix_world
            poses.add(tuple(round(v, 7) for row in m for v in row))
    distinct = len(poses)
    ok = distinct >= 2
    print(f"  {'PASS' if ok else 'FAIL'}  {body_id:20s} {distinct} distinct poses over "
          f"{FRAME_COUNT} frames")
    anim_checks[body_id]["distinct_poses"] = distinct
    if not ok:
        fails.append(f"{body_id}: the animation is frozen ({distinct} distinct pose)")
    # The travel must match the record, measured on a fixed reference point rather than an anchor.
    got = []
    for f in range(1, FRAME_COUNT + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        o = bpy.data.objects[spec["objects"][0]]
        first_nm = spec["objects"][0]
        got.append(o.matrix_world @ Vector(refpts[body_id]["points_per_object"][first_nm][0]))
    rendered_travel = max((p - got[0]).length for p in got)
    rec = [Vector(r["position_m"]) for r in TRAJ[body_id]]
    recorded_travel = max((p - rec[0]).length for p in rec)
    err = abs(rendered_travel - recorded_travel)
    ok = err <= max(2e-4, 0.02 * max(recorded_travel, 1e-4))
    print(f"  {'PASS' if ok else 'FAIL'}  {body_id:20s} rendered travel {rendered_travel * 1000:.4f} mm "
          f"vs recorded {recorded_travel * 1000:.4f} mm")
    anim_checks[body_id]["rendered_travel_m"] = rendered_travel
    anim_checks[body_id]["recorded_travel_m"] = recorded_travel
    if not ok:
        fails.append(f"{body_id}: travel {rendered_travel:.6f} vs {recorded_travel:.6f}")

if fails:
    (RUN / "animation_verification.json").write_text(json.dumps(
        {"pass": False, "failures": fails, "per_body": anim_checks}, indent=2), encoding="utf-8")
    raise SystemExit("FATAL: animation verification failed; NOT rendering. Failures: "
                     + "; ".join(fails))

(RUN / "animation_verification.json").write_text(json.dumps(
    {"pass": True, "failures": [], "per_body": anim_checks}, indent=2), encoding="utf-8")
(RUN / "binding.json").write_text(json.dumps(binding, indent=2), encoding="utf-8")
(RUN / "reference_points.json").write_text(json.dumps(refpts, indent=2), encoding="utf-8")
print(f"  written: binding.json, reference_points.json, animation_verification.json")

# ---------------------------------------------------------------------------------------
# camera: from the config, which the framing step fills in
# ---------------------------------------------------------------------------------------

cam_cfg = CFG.get("camera")
if not cam_cfg:
    raise SystemExit("FATAL: no camera in the config; the framing step must set one before rendering")
cam_data = bpy.data.cameras.new("V56_Camera")
cam_data.lens = float(cam_cfg["lens_mm"])
cam_data.sensor_width = float(cam_cfg.get("sensor_width_mm", 36.0))
cam_obj = bpy.data.objects.new("V56_Camera", cam_data)
scene.collection.objects.link(cam_obj)
eye = Vector(cam_cfg["eye_m"])
aim = Vector(cam_cfg["aim_m"])
cam_obj.location = eye
cam_obj.rotation_mode = "QUATERNION"
cam_obj.rotation_quaternion = (-(aim - eye).normalized()).to_track_quat("Z", "Y")
scene.camera = cam_obj
bpy.context.view_layer.update()
print(f"\n=== camera ===\n  {cam_cfg.get('name', 'V56_Camera')} {cam_data.lens:.1f} mm  "
      f"eye {[round(v, 4) for v in eye]}  aim {[round(v, 4) for v in aim]}")

# ---------------------------------------------------------------------------------------
# redirect external File Output nodes into this run (section 10: nothing outside the workspace)
# ---------------------------------------------------------------------------------------

redirected = []
if getattr(scene, "use_nodes", False) and scene.node_tree is not None:
    comp = OUT / "compositor"
    comp.mkdir(parents=True, exist_ok=True)
    for node in scene.node_tree.nodes:
        if node.type != "OUTPUT_FILE":
            continue
        old = getattr(node, "base_path", "") or ""
        node.base_path = str(comp)
        redirected.append({"node": node.name, "old_base_path": old, "new_base_path": str(comp)})
        print(f"  redirected File Output '{node.name}': '{old}' -> '{comp}'")
if not redirected:
    print("  no File Output nodes; nothing is written outside the run")

# ---------------------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------------------

if MODE == "probe":
    print("\n=== probe mode: scene built and verified, no frames rendered ===")
    (RUN / "probe_report.json").write_text(json.dumps(
        {"pass": True, "camera": cam_cfg, "binding": binding,
         "animation_checks": anim_checks, "compositor_redirect": redirected}, indent=2),
        encoding="utf-8")
    raise SystemExit(0)

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SPP
scene.cycles.use_denoising = True
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = False
scene.cycles.max_bounces = 6
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 3
scene.cycles.transmission_bounces = 6
scene.cycles.transparent_max_bounces = 8
scene.cycles.volume_bounces = 0
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.01
scene.render.use_persistent_data = True
scene.render.threads_mode = "FIXED"
scene.render.threads = THREADS
print(f"\n=== threads FIXED at {THREADS} (plan section 8: one heavy task, <=8 threads; machine has "
      f"{os.cpu_count()} logical) ===")

frame_dir = OUT / f"frames_{MODE}"
frame_dir.mkdir(parents=True, exist_ok=True)
existing = sorted(frame_dir.glob("f_*.png"))
if existing:
    raise SystemExit(f"FATAL: {len(existing)} frames already exist in {frame_dir}; this project "
                     f"deletes nothing, so move them to remove/ first rather than overwriting")

t0 = time.time()
timings = []
for f in FRAME_LIST:
    scene.frame_set(f + 1)
    target = frame_dir / f"f_{f:04d}.png"
    scene.render.filepath = str(target)
    ts = time.time()
    bpy.ops.render.render(write_still=True)
    ok = target.is_file()
    timings.append({"frame": f, "seconds": time.time() - ts, "bytes":
                    target.stat().st_size if ok else 0, "written": ok})
    if not ok:
        raise SystemExit(f"FATAL: frame {f} rendered but {target} was not written")
    if len(timings) <= 3 or len(timings) % 5 == 0 or f == FRAME_LIST[-1]:
        rate = (time.time() - t0) / len(timings)
        print(f"  frame {f:4d} {time.time() - ts:8.2f} s {target.stat().st_size / 1024:8.1f} KB "
              f"mean {rate:7.2f} s/frame elapsed {time.time() - t0:8.1f} s", flush=True)

marginal = ([t["seconds"] for t in timings][1:] or [timings[0]["seconds"]])
rate = sum(marginal) / len(marginal)
budget = {"mode": MODE, "resolution": [RES_X, RES_Y], "spp": SPP, "frames": len(timings),
          "total_seconds": time.time() - t0, "marginal_seconds_per_frame": rate,
          "threads": THREADS, "persistent_data": True, "per_frame": timings}
(OUT / f"render_timings_{MODE}.json").write_text(json.dumps(budget, indent=2), encoding="utf-8")
print(f"\n  rendered {len(timings)} frames in {time.time() - t0:.1f} s "
      f"(marginal {rate:.2f} s/frame)")

# save the replayable project so the clip can be reproduced by opening the file
replay_dir = OUT / "replays"
replay_dir.mkdir(parents=True, exist_ok=True)
replay_p = replay_dir / f"replay_{MODE}.blend"
if replay_p.exists():
    raise SystemExit(f"FATAL: {replay_p} already exists; use a new run_id rather than overwriting")
scene.frame_set(1)
cam_cfg_saved = dict(cam_cfg)
cam_cfg_saved.update({"saved_from": "the replay project's active camera, which is the authority",
                      "location_m": [float(v) for v in cam_obj.matrix_world.translation],
                      "lens_mm": cam_data.lens})
bpy.ops.wm.save_as_mainfile(filepath=str(replay_p), copy=True)
(RUN / "camera.json").write_text(json.dumps(cam_cfg_saved, indent=2), encoding="utf-8")
print(f"  replay project saved: {replay_p} ({replay_p.stat().st_size / 1048576:.1f} MiB)")
print(f"  camera.json written FROM the saved camera, which section 7.6 makes the only authority")
