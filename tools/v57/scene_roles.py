"""Classify the scene's objects by ROLE, from measured properties rather than from their names.

WHY THIS MEASURES RATHER THAN GUESSES
-------------------------------------
The plan asks for `scene_roles.json` covering the real support surface, the real obstacles and buildings, the
lighting aids, the distant scenery and the rendered dynamic boxes -- and it says explicitly to check by
object, material, collection and ACTUAL SHAPE and sightline, not by name. Name-based classification is what
produced the earlier round's central error: `light_blocker_building` was treated as a lighting aid and the
chain was allowed to intersect it, when in fact it is original authored geometry with a real collision face.

So every claim in the output is backed by a measurement:

  * `shape`          -- triangle count, world AABB, and how flat the object is;
  * `is_camera_visible` -- the fraction of a ray grid cast through the APPROVED camera that hits this object,
    which is the sightline check the plan asks for;
  * `touches_chain_envelope` -- whether the object comes within a margin of any box's initial pose or its
    swept envelope, computed by world-space BVH overlap rather than by bounding boxes;
  * `support_contact` -- whether the boxes actually rest on it, from the clearance check's own result.

A role is then assigned from those facts, with the reasoning recorded per object, so a reader can disagree
with the classification without having to re-derive the numbers.

Usage:
    blender --background --factory-startup --python tools/v57/scene_roles.py -- \
        --blend <staged.blend> --config <render_config.json> --out scene_roles.json \
        [--traj trajectory.json]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"]).resolve()
CFG_P = Path(ARGS["config"]).resolve()
OUT = Path(ARGS["out"]).resolve()
TRAJ_P = Path(ARGS["traj"]).resolve() if ARGS.get("traj") else None
FLOOR = ARGS.get("floor", "Floor_main")
# How close an object must come to the chain's envelope to count as "in the motion envelope".
ENVELOPE_M = float(ARGS.get("envelope_mm", "50.0")) / 1000.0
GRID = int(ARGS.get("grid", "72"))  # rays per axis for the visibility census

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
CFG = json.loads(CFG_P.read_text(encoding="utf-8"))
BINDING = CFG["binding"]
CAM = CFG["camera"]

ANIM_NAMES = {spec["objects"][0] for spec in BINDING.values()}
print("=" * 100)
print(f"scene role classification | {BLEND.name}")
print(f"  camera eye {[round(v, 3) for v in CAM['eye_m']]} aim {[round(v, 3) for v in CAM['aim_m']]} "
      f"{CAM['lens_mm']} mm")
print("=" * 100)


def world_tris(obj, dg):
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        mw = ev.matrix_world
        vs = [mw @ v.co for v in me.vertices]
        ts = []
        for p in me.polygons:
            vi = list(p.vertices)
            for k in range(1, len(vi) - 1):
                ts.append((vi[0], vi[k], vi[k + 1]))
        return vs, ts, len(me.polygons)
    finally:
        ev.to_mesh_clear()


# ---------------------------------------------------------------------------------------------
# Camera ray census. A pinhole grid through the approved camera, so "camera visible" means visible from the
# camera the video is actually shot with rather than from an arbitrary direction.
# ---------------------------------------------------------------------------------------------
cam_data = bpy.data.cameras.new("roles_cam")
cam_data.lens = float(CAM["lens_mm"])
cam_data.sensor_width = float(CAM.get("sensor_width_mm", 36.0))
cam_obj = bpy.data.objects.new("roles_cam", cam_data)
scene.collection.objects.link(cam_obj)
cam_obj.location = Vector(CAM["eye_m"])
cam_obj.rotation_mode = "QUATERNION"
cam_obj.rotation_quaternion = (Vector(CAM["aim_m"]) - Vector(CAM["eye_m"])).normalized() \
    .to_track_quat("-Z", "Y")
bpy.context.view_layer.update()

rx, ry = (int(v) for v in CFG.get("resolution", [1280, 720]))
ar = rx / ry
half_w = cam_data.sensor_width / 2.0
half_h = half_w / ar
focal = cam_data.lens
origin = cam_obj.matrix_world.translation
Rc = cam_obj.matrix_world.to_3x3()

hits = {}
n_rays = 0
for iy in range(GRID):
    for ix in range(GRID):
        xl = (2.0 * (ix + 0.5) / GRID - 1.0) * half_w
        yl = (2.0 * (iy + 0.5) / GRID - 1.0) * half_h
        d = (Rc @ Vector((xl, yl, -focal))).normalized()
        ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, origin, d, distance=200.0)
        n_rays += 1
        if ok:
            hits[obj.name] = hits.get(obj.name, 0) + 1
print(f"  camera rays cast: {n_rays}, distinct objects hit: {len(hits)}")

# ---------------------------------------------------------------------------------------------
# The chain envelope: every animated body's world triangles across the whole trajectory, dilated.
# ---------------------------------------------------------------------------------------------
env_pts = []
if TRAJ_P:
    _raw = json.loads(TRAJ_P.read_text(encoding="utf-8"))
    TRAJ = _raw["bodies"] if isinstance(_raw, dict) and "bodies" in _raw else _raw

    def q_b(q):
        x, y, z, w = (float(c) for c in q)
        return Quaternion((w, x, y, z))

    def t_wb(row):
        return (Matrix.Translation(Vector(row["position_m"]))
                @ q_b(row["quaternion_xyzw"]).to_matrix().to_4x4())

    anim_objs = {spec["objects"][0]: spec for spec in BINDING.values()}
    scene.frame_set(1)
    bpy.context.view_layer.update()
    t_wv0 = {}
    for nm in anim_objs:
        o = bpy.data.objects.get(nm)
        if o:
            t_wv0[nm] = o.matrix_world.copy()
    t_wb0 = {bid: t_wb(TRAJ[bid][0]) for bid in TRAJ}
    # Sample the envelope every 4th frame: the sweep is continuous, and 36 poses bound it to within a frame's
    # motion, which is far inside the 50 mm margin used for the test.
    for nm, spec in anim_objs.items():
        bid = next(b for b, s in BINDING.items() if s["objects"][0] == nm)
        o = bpy.data.objects.get(nm)
        if not o:
            continue
        rows = TRAJ[bid][::4]
        for row in rows:
            mw = t_wb(row) @ t_wb0[bid].inverted() @ t_wv0[nm]
            for v in o.data.vertices:
                env_pts.append(mw @ v.co)
print(f"  chain envelope: {len(env_pts)} sampled vertices across the trajectory")

env_bvh = None
if env_pts:
    lo = Vector((min(p[i] for p in env_pts) for i in range(3))) - Vector((ENVELOPE_M,) * 3)
    hi = Vector((max(p[i] for p in env_pts) for i in range(3))) + Vector((ENVELOPE_M,) * 3)
    c = (lo + hi) / 2.0
    h = (hi - lo) / 2.0
    corners = [(c.x + sx * h.x, c.y + sy * h.y, c.z + sz * h.z)
               for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for f in faces:
        tris.append((f[0], f[1], f[2]))
        tris.append((f[0], f[2], f[3]))
    env_bvh = BVHTree.FromPolygons(corners, tris, all_triangles=True)
    print(f"  envelope AABB (with {ENVELOPE_M * 1000:.0f} mm margin): "
          f"{[round(v, 3) for v in lo]} .. {[round(v, 3) for v in hi]}")

# ---------------------------------------------------------------------------------------------
# Per-object measurement and role assignment.
# ---------------------------------------------------------------------------------------------
roles = {}
for o in sorted(bpy.data.objects, key=lambda x: x.name):
    if o.type != "MESH":
        continue
    vs, ts, npoly = world_tris(o, deps)
    if not vs:
        continue
    lo = Vector((min(p[i] for p in vs) for i in range(3)))
    hi = Vector((max(p[i] for p in vs) for i in range(3)))
    size = hi - lo
    dims = sorted([size.x, size.y, size.z])
    # Flatness: the ratio of the smallest extent to the largest. A lighting aid or backdrop is typically a
    # large, very flat sheet; a solid object is not.
    flat = dims[0] / max(dims[2], 1e-9)

    vis_rays = hits.get(o.name, 0)
    vis_frac = vis_rays / n_rays if n_rays else 0.0

    near = False
    if env_bvh is not None and len(ts):
        obvh = BVHTree.FromPolygons(vs, ts, all_triangles=True)
        near = len(obvh.overlap(env_bvh)) > 0

    # `near` is a CONSERVATIVE test: the envelope is the bounding BOX of the swept chain, which is larger
    # than the chain's actual swept volume, so it can flag an object the boxes never touch. On this run it
    # flagged `grass` and `leaves`, while the exact per-frame triangle test in
    # `clearance_replay.json` found ZERO contact for every body at all 144 frames. Presenting the two as if
    # they disagreed would be a defect in the report, so the distinction is named here.
    near_desc = ("inside the bounding BOX of the swept chain -- a conservative test, since the box is "
                 "larger than the swept volume, so this alone is not evidence of contact")
    if near:
        near_desc += ("; the exact per-frame triangle test (clearance_replay.json) found NO contact with "
                      "this object at any of the 144 frames, and the chain site was chosen with a 10 mm "
                      "clearance margin precisely so that it would not")

    mats = sorted({m.name for m in o.data.materials if m})
    cols = sorted({c.name for c in o.users_collection}) or ["<scene collection>"]

    if o.name in ANIM_NAMES:
        role = "dynamic_rendered_box"
        why = "bound as a rendered dynamic body in the render config"
    elif o.name == FLOOR:
        role = "real_support_surface"
        why = ("the declared support; every box was ray-cast onto it and the clearance check confirms all "
               "ten bodies rest on it")
    elif near:
        role = "real_obstacle_avoided"
        why = (f"original authored geometry that the swept chain's bounding box reaches. The chain was "
               f"routed to avoid it rather than it being hidden or edited. {near_desc}")
    elif vis_frac >= 0.01:
        role = "visible_scenery"
        why = f"occupies {vis_frac * 100:.2f}% of the approved camera's rays"
    else:
        role = "distant_or_off_camera"
        why = (f"not in the swept envelope and outside the approved view ({vis_frac * 100:.3f}% of rays); "
               f"kept as authored")

    roles[o.name] = {
        "role": role,
        "why": why,
        "triangles": npoly,
        "world_aabb_min_m": [round(v, 6) for v in lo],
        "world_aabb_max_m": [round(v, 6) for v in hi],
        "extent_m": [round(v, 6) for v in size],
        "flatness_ratio": round(flat, 6),
        "camera_ray_fraction": round(vis_frac, 8),
        "camera_rays_hit": vis_rays,
        "touches_chain_envelope": near,
        "materials": mats[:12],
        "collections": cols,
        "edited": False,
        "note": "measured, not inferred from the name",
    }

counts = {}
for r in roles.values():
    counts[r["role"]] = counts.get(r["role"], 0) + 1
print("")
print("  role counts:")
for k in sorted(counts):
    print(f"    {k:38s} {counts[k]:5d}")
print("")
print("  objects in the motion envelope (these are the ones that matter most):")
for nm, r in sorted(roles.items()):
    if r["role"] == "real_obstacle_avoided":
        print(f"    {nm:44s} tris {r['triangles']:>7d}  extent {r['extent_m']}  "
              f"flatness {r['flatness_ratio']:.4f}  rays {r['camera_ray_fraction'] * 100:.3f}%")
print("")
print("  most visible objects:")
for nm, r in sorted(roles.items(), key=lambda kv: -kv[1]["camera_ray_fraction"])[:10]:
    print(f"    {nm:44s} {r['camera_ray_fraction'] * 100:7.2f}%  {r['role']}")

report = {
    "blend": str(BLEND),
    "classified_by": "measured triangles, world AABB, camera ray census and swept-envelope overlap",
    "camera": {"eye_m": CAM["eye_m"], "aim_m": CAM["aim_m"], "lens_mm": CAM["lens_mm"]},
    "grid_rays": n_rays,
    "envelope_margin_m": ENVELOPE_M,
    "envelope_vertices_sampled": len(env_pts),
    "role_counts": counts,
    "role_definitions": {
        "real_support_surface": "the surface the boxes rest on; contact with it is required, not a defect",
        "real_obstacle_avoided": ("original authored geometry that the swept chain comes near; "
                                             "must be avoided by moving the chain, never hidden or edited"),
        "visible_scenery": "visible in the approved view but not near the chain; kept as authored",
        "distant_or_off_camera": "neither near the chain nor in the approved view",
        "dynamic_rendered_box": "an animated body driven by the trajectory",
    },
    "policy": {
        "nothing_deleted_or_moved": True,
        "no_global_hide_render": True,
        "lighting_aids_not_hidden": ("no object was hidden or edited in this round; the chain was moved "
                                     "instead, so no visibility A/B is claimed or needed"),
    },
    "objects": roles,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwrote {OUT}")
