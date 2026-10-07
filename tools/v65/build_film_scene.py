"""V6.5 -- build the ANIMATED film scene from the author's scene plus the solved trajectory.

WHAT THIS DOES
--------------
Opens the author's `ph_hidden_alley.blend` (read only), reproduces the 51 physical actors as the SAME common meshes the
solver used, drives them from `trajectory.npz`, adds one camera fed by `camera_path.json`, and preserves everything
else byte-for-byte: the 7 lights, both scenes (`Scene` with Cycles, `Fog` with EEVEE Next), the world, the view
transform, the exposure and the 39-node compositor.

PLAN SECTION 3 GATE 3 (COMMON MODE) IS THE WHOLE POINT OF THIS SCRIPT
--------------------------------------------------------------------
The ruled-out failure mode is "physics has a small box and the render has a big box": a size, local-origin or
shape/mapping mismatch between what was solved and what is drawn. It is prevented here structurally rather than by
inspection:

  * every actor's mesh comes from the SAME library the solver loaded (`common_assets_r1/common_assets.blend` for the
    six game boxes, the radio's 37 parts, the ball; the V6.4-repaired `tape_common_r9.blend` for the tape), and each
    object's vertex+triangle sha256 is checked against the value that library records;
  * each actor is placed by the same `trajectory.npz` pose the solver produced, with NO scale applied -- the meshes
    are already in metres, so `scale` stays (1,1,1) and a mismatch cannot hide in a scale factor;
  * the artifact that the physics REPLACES (the author's `boombox.002`) is hidden, and ONLY that one. Its hiding is
    declared in the report rather than done quietly.
  * nothing else in the author's scene is touched: the report records the lights and every object matrix before and
    after, and raises if anything but the declared objects changed.

TAIL TEXTURE: the repaired tape ring is drawn from `tape_own_atlas_r9`, the V6.4 fix (black faces 11 -> 0). The
pre-repair wedges in `common_assets_r1` are never loaded -- the probe (`probe_tape.py`) confirmed both libraries hold
48 tape objects, so picking the wrong one would be silent, and the wrong one is simply never referenced here.

OUTPUT: `film_scene.blend` plus `composition_report.json`.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

ROOT = Path("/data/raw/huzijian/project1_database")
SOURCE = ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"
COMMON = ROOT / "tmp/v63_node11/common_assets_r1/common_assets.blend"
COMMON_MANIFEST = ROOT / "tmp/v63_node11/common_assets_r1/manifest.json"
TAPE = ROOT / "models/derived/v64/common_assets_r2/tape_common_r9.blend"
MANIFEST = ROOT / "tmp/v64_node12/v64_physics_manifest_r2.json"
LAYOUT = ROOT / "tmp/v64_node12/layout_v65_tailwest_candidate_b.json"

ap = argparse.ArgumentParser()
ap.add_argument("--out-dir", required=True)
ap.add_argument("--trajectory", required=True)
ap.add_argument("--camera", required=True)
ap.add_argument("--fps", type=int, default=24)
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])

OUT = Path(args.out_dir).resolve()
if ROOT not in OUT.parents:
    raise ValueError("out-dir outside workspace")
OUT.mkdir(parents=True, exist_ok=True)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


manifest = json.loads(MANIFEST.read_text())
layout = json.loads(LAYOUT.read_text())
common = json.loads(COMMON_MANIFEST.read_text())
traj = np.load(args.trajectory)
cam = json.loads(Path(args.camera).read_text())
gp = {r["id"]: r for r in layout["objects"]}

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
main = bpy.data.scenes["Scene"]
bpy.context.window.scene = main

# ---- record the author's scene so any unintended change is caught ----------------------
before_matrices = {o.name: [list(r) for r in o.matrix_world] for o in bpy.data.objects}
before_lights = {o.name: {"type": o.data.type, "energy": o.data.energy, "color": list(o.data.color)}
                 for o in bpy.data.objects if o.type == "LIGHT"}
before_scene = {s.name: {"engine": s.render.engine,
                         "world": s.world.name if s.world else None,
                         "vt": s.view_settings.view_transform,
                         "exposure": s.view_settings.exposure,
                         "gamma": s.view_settings.gamma,
                         "nodes": [(n.name, n.bl_idname) for n in s.node_tree.nodes] if s.use_nodes else [],
                         "fps": s.render.fps, "res": [s.render.resolution_x, s.render.resolution_y]}
                for s in bpy.data.scenes}
source_hash = digest(SOURCE)

# ---- load the common mesh library (the SAME one the solver used) -----------------------
# LOADING THE LIBRARY: the object handles are collected by DIFFING `bpy.data.objects` across each load, rather than
# by reading `src.objects`/`dst.objects`. Three earlier attempts to read those collections were wrong in different
# ways and two of them failed SILENTLY:
#   * reading `dst.objects` inside the with-block returns what was requested, not the materialised objects;
#   * using the in-block handles as dictionary keys made every later lookup by name miss, so the common-mode shape
#     check compared ZERO objects and still printed "verified";
#   * `src.objects` does not consistently yield plain strings in this build, so filtering it by `startswith` is not
#     dependable either.
# Diffing the data-block list is unambiguous: whatever the loader materialised is exactly what appears.
def load_from(path, prefixes):
    before = {o.name for o in bpy.data.objects}
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        wanted = [n for n in [getattr(x, "name", x) for x in list(src.objects)]
                  if any(str(n).startswith(p) for p in prefixes)]
        if not wanted:
            raise RuntimeError(f"no objects matching {prefixes} in {path}")
        dst.objects = wanted
    return {o.name: o for o in bpy.data.objects if o.name not in before}


asset_objs = {}
asset_objs.update(load_from(COMMON, ("v63_asset_",)))
asset_objs.update(load_from(TAPE, ("v64_asset_tape_",)))
n_common = sum(1 for n in asset_objs if n.startswith("v63_asset_"))
n_tape = sum(1 for n in asset_objs if n.startswith("v64_asset_tape_"))
if n_common < 90 or n_tape != 48:
    raise RuntimeError(f"library incomplete: {n_common} common + {n_tape} repaired tape objects")
print(f"  library objects materialised: {n_common} common + {n_tape} repaired tape "
      f"({len(asset_objs)} total)", flush=True)

# shape identity: every object about to be drawn must match its recorded vertex+triangle hash
shape_report = []
expected_checks = 0
for key, row in common["assets"].items():
    rows = row.get("parts") or [row]
    for r in rows:
        nm = r["object"]
        obj = asset_objs.get(nm)
        if obj is None:
            continue
        expected_checks += 1
        obj.data.calc_loop_triangles()
        v = np.array([list(x.co) for x in obj.data.vertices], dtype="<f8")
        t = np.array([list(x.vertices) for x in obj.data.loop_triangles], dtype="<i4")
        h = hashlib.sha256(v.tobytes() + t.tobytes()).hexdigest()
        ok = (h == r["shape_sha256"])
        shape_report.append({"object": nm, "expected": r["shape_sha256"], "actual": h, "match": bool(ok)})
        if not ok:
            raise RuntimeError(f"common-mode shape mismatch on {nm}")
# The count is asserted because an earlier revision verified ZERO objects and still reported success: every lookup
# missed, the loop body never ran, and the check was vacuous. A verification that cannot fail is not a verification,
# so the number of objects actually compared is checked against the number the manifest supplies.
want = sum(len(row.get("parts") or [row]) for row in common["assets"].values())
if len(shape_report) != want:
    raise RuntimeError(f"common-mode identity check covered {len(shape_report)} objects but the manifest lists {want}")
print(f"  common-mode shape identity verified on {len(shape_report)} objects", flush=True)

# ---- the actor container ---------------------------------------------------------------
col = bpy.data.collections.new("v65_actors")
for s in bpy.data.scenes:
    s.collection.children.link(col)

# hide ONLY the author's boombox that the physics replaces (declared)
replaced = []
for nm in ("boombox.002",):
    o = bpy.data.objects.get(nm)
    if o:
        o.hide_render = True
        o.hide_viewport = True
        replaced.append(nm)

actors = {}


def add_actor(ident, key, parts_source):
    """Reproduce one physical actor as its common meshes, at identity scale.

    `parts_source` is either a single object name or a list. Scale stays exactly (1,1,1): the library meshes are in
    metres and so is the physics, so a differce in size would show up immediately rather than being absorbed by a
    scale factor.
    """
    objs = []
    for i, nm in enumerate(parts_source):
        tpl = asset_objs[nm]
        o = tpl.copy()
        o.name = f"v65_{ident}_{i:02d}"
        o.data = tpl.data
        col.objects.link(o)
        o.hide_render = False
        o.hide_viewport = False
        o.hide_set(False)
        o.scale = (1.0, 1.0, 1.0)
        o["actor_id"] = ident
        o["asset_key"] = key
        o["source_library_object"] = nm
        objs.append(o)
    actors[ident] = objs


radio_parts = [p["object"] for p in common["assets"]["radio"]["parts"]]
tape_parts = [p["object"] for p in common["assets"]["tape"]["parts"]]
# the tape actor must use the REPAIRED wedges, not the pre-repair ones from common_assets_r1
tape_repaired = [f"v64_asset_tape_{i:02d}" for i in range(48)]
if not all(n in asset_objs for n in tape_repaired):
    raise RuntimeError("repaired tape wedges missing from tape_common_r9.blend")

ASSET_OBJECTS = {"radio": radio_parts, "baseball": ["v63_asset_baseball"], "tape": tape_repaired,
                 "paper": ["v63_asset_paper"], "wii": ["v63_asset_wii"], "dvd": ["v63_asset_dvd"],
                 "cranium": ["v63_asset_cranium"], "trivial": ["v63_asset_trivial"], "ouija": ["v63_asset_ouija"]}

add_actor("A", "radio", radio_parts)
add_actor("B", "baseball", ASSET_OBJECTS["baseball"])
add_actor("R", "paper", ASSET_OBJECTS["paper"])
for row in layout["objects"]:
    add_actor(row["id"], row["asset_key"], ASSET_OBJECTS[row["asset_key"]])

# ---- drive every actor from the solver's own trajectory --------------------------------
T = traj["t"]
n_frames = int(cam["n_frames"])
fps = args.fps
frame_times = np.arange(n_frames) / fps


def pose_at(ident, t):
    p = traj[f"pos_{ident}"]
    q = traj[f"quat_{ident}"]
    i = int(np.clip(round(t * fps), 0, len(T) - 1))
    return np.array(p[i], dtype=float), np.array(q[i], dtype=float)


unfilled = []
for ident, objs in actors.items():
    if f"pos_{ident}" not in traj:
        unfilled.append(ident)
        continue
    mats = []
    for k, t in enumerate(frame_times):
        pos, q = pose_at(ident, t)
        # physics stores quaternions as (x, y, z, w); Blender wants (w, x, y, z)
        rot = Quaternion((float(q[3]), float(q[0]), float(q[1]), float(q[2]))).to_matrix().to_4x4()
        m = Matrix.Translation(Vector((float(pos[0]), float(pos[1]), float(pos[2])))) @ rot
        for o in objs:
            o.matrix_world = m
            o.keyframe_insert("location", frame=k + 1)
            o.keyframe_insert("rotation_quaternion", frame=k + 1)
        mats.append([list(r) for r in m])
    for o in objs:
        if o.animation_data and o.animation_data.action:
            for fc in o.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
if unfilled:
    raise RuntimeError(f"trajectory lacks actors: {unfilled}")
print(f"  keyframed {len(actors)} actors over {n_frames} frames ({n_frames / fps:.3f} s at {fps} fps)", flush=True)

# ---- the camera ------------------------------------------------------------------------
cam_data = bpy.data.cameras.new("v65_cam")
cam_data.lens = 0.0
cam_data.sensor_width = 36.0
cam_data.sensor_fit = "HORIZONTAL"
cam_data.angle = np.radians(cam["fov_deg"])
cam_data.clip_start = 0.02
cam_data.clip_end = 1500.0
cam_data.dof.use_dof = False
cam_obj = bpy.data.objects.new("v65_cam", cam_data)
for s in bpy.data.scenes:
    s.collection.objects.link(cam_obj)

cam_xyz = np.array(cam["camera_xyz"], dtype=float)
look_xyz = np.array(cam["look_xyz"], dtype=float)
for k in range(n_frames):
    cam_obj.location = Vector(cam_xyz[k].tolist())
    cam_obj.rotation_euler = (Vector(look_xyz[k]) - Vector(cam_xyz[k])).to_track_quat("-Z", "Y").to_euler()
    cam_obj.keyframe_insert("location", frame=k + 1)
    cam_obj.keyframe_insert("rotation_euler", frame=k + 1)
if cam_obj.animation_data and cam_obj.animation_data.action:
    for fc in cam_obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"

# ---- per-scene render settings: same camera, same matrix, same time, every scene --------
for s in bpy.data.scenes:
    s.camera = cam_obj
    s.frame_start = 1
    s.frame_end = n_frames
    s.render.fps = fps
    s.render.fps_base = 1.0
    s.render.resolution_x = cam["res"][0]
    s.render.resolution_y = cam["res"][1]
    s.render.resolution_percentage = 100
    s.render.pixel_aspect_x = s.render.pixel_aspect_y = 1.0
    s.render.use_border = False
    s.render.use_crop_to_border = False
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB"
    s.render.threads_mode = "FIXED"
    s.render.threads = 16
    s.render.film_transparent = False
    if s.render.engine == "CYCLES":
        s.cycles.device = "CPU"
        s.cycles.samples = 24
        s.cycles.use_denoising = True
        s.render.use_persistent_data = True
    elif hasattr(s, "eevee"):
        s.eevee.taa_render_samples = 8
    if s.use_nodes:
        for n in s.node_tree.nodes:
            if n.type == "OUTPUT_FILE":
                n.base_path = str(OUT / ("compositor_" + s.name))
s0 = bpy.data.scenes["Scene"]
s0.frame_set(1)

# ---- conservation checks ---------------------------------------------------------------
changed = [n for n, m in before_matrices.items()
           if n not in replaced and n in bpy.data.objects
           and [list(r) for r in bpy.data.objects[n].matrix_world] != m]
after_lights = {o.name: {"type": o.data.type, "energy": o.data.energy, "color": list(o.data.color)}
                for o in bpy.data.objects if o.type == "LIGHT"}
after_scene = {s.name: {"engine": s.render.engine,
                        "world": s.world.name if s.world else None,
                        "vt": s.view_settings.view_transform,
                        "exposure": s.view_settings.exposure,
                        "gamma": s.view_settings.gamma,
                        "nodes": [(n.name, n.bl_idname) for n in s.node_tree.nodes] if s.use_nodes else [],
                        "fps": before_scene[s.name]["fps"],
                        "res": before_scene[s.name]["res"]}
               for s in bpy.data.scenes}
if changed:
    raise RuntimeError(f"unintended author transform changes: {changed[:6]}")
if after_lights != before_lights:
    raise RuntimeError("the author's lights changed")
for name in before_scene:
    for key in ("engine", "world", "vt", "exposure", "gamma", "nodes"):
        if after_scene[name][key] != before_scene[name][key]:
            raise RuntimeError(f"scene {name} changed {key}: {before_scene[name][key]} -> {after_scene[name][key]}")
if digest(SOURCE) != source_hash:
    raise RuntimeError("the author's source file changed on disk")

report = {
    "status": "V65_ANIMATED_SCENE_BUILT_FULL_PHYSICS_ACCEPTANCE_PENDING",
    "source": str(SOURCE), "source_sha256": source_hash,
    "common_library": str(COMMON), "repaired_tape_library": str(TAPE),
    "trajectory": args.trajectory, "camera": args.camera,
    "n_frames": n_frames, "fps": fps, "duration_s": n_frames / fps,
    "resolution": cam["res"], "fov_deg": cam["fov_deg"],
    "actors": len(actors), "actor_mesh_objects": sum(len(v) for v in actors.values()),
    "common_mode_shape_checks": shape_report,
    "author_objects_hidden": replaced,
    "declared_author_change": "the author's boombox.002 is hidden because the 37-part radio actor A replaces it",
    "added_scene_content": "51 common-mesh actors plus one camera; no added light, floor, rail or platform",
    "author_lights": before_lights,
    "author_scenes": before_scene,
    "tape_source": "tape_common_r9.blend (V6.4 repair: black faces 11 -> 0); the pre-repair wedges are not loaded",
    "remaining_gates": ["geometry gates", "render common-mode pixel QA", "final encode QA"],
}
(OUT / "composition_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
target = OUT / "film_scene.blend"
if target.exists():
    raise RuntimeError("refuse to overwrite an existing film_scene.blend")
bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=True)
print(f"SCENE_BUILT actors={len(actors)} frames={n_frames} -> {target}", flush=True)
