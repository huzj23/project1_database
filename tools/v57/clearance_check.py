"""Authoritative clearance gate: do the built bodies overlap anything but the declared floor?

WHY THIS IS THE ONE TO TRUST
----------------------------
Three tools gave three different answers about the same site -- 0 mm, 9.91 mm and 0 mm -- because each
computed the bodies' poses itself and then transformed obstacle vertices into a body frame. Every one of
those steps is a place for a frame error, and a frame error here is silent: it produces a plausible number
with the wrong sign or the wrong body.

This check removes the arithmetic entirely. Both sides of the test are WORLD-SPACE TRIANGLES taken from
Blender's own evaluated meshes:

    * the obstacle set, as one BVH over every mesh except the floor and the animated bodies;
    * each animated body, as its own BVH, built from that object's evaluated mesh with its own matrix_world
      applied -- the same matrices Blender uses to draw it.

`BVHTree.overlap` then answers the question directly, in Blender's own code, with no pose model, no local
frame and no axis mapping to get wrong. A non-empty overlap means the body's surface genuinely meets the
obstacle's surface.

Touching counts as a failure here, deliberately. The plan requires every box to stand on the real support
surface and nothing else, so a box resting against a stone, a leaf or a wall is a defect whether it is
1 mm or 20 mm deep; distinguishing "resting on" from "buried in" would only matter if leaning were allowed.

Usage:
    blender --background --factory-startup --python tools/v57/clearance_check.py -- \
        --blend <built.blend> [--floor Floor_main] [--out report.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"]).resolve()
FLOOR = ARGS.get("floor", "Floor_main")
OUT = Path(ARGS["out"]).resolve() if ARGS.get("out") else None
TRAJ_P = Path(ARGS["traj"]).resolve() if ARGS.get("traj") else None
MAX_FRAMES = int(ARGS.get("max_frames", "0"))

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()

ANIM_PREFIX = ("box", "trigger_")
anims = [o for o in scene.objects
         if o.type == "MESH" and o.name.startswith(ANIM_PREFIX)
         and not o.name.startswith("gate_proxy_")]


def tris_of(obj, dg):
    """(vertices, triangles) in WORLD space, from the object's evaluated mesh."""
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
        return vs, ts
    finally:
        ev.to_mesh_clear()


# --- obstacles: everything except the floor and the animated bodies ---------------------------------
ov, ot, owners = [], [], []
for o in scene.objects:
    if o.type != "MESH" or o.name == FLOOR or o in anims:
        continue
    vs, ts = tris_of(o, deps)
    base = len(ov)
    ov.extend(vs)
    for t in ts:
        ot.append((base + t[0], base + t[1], base + t[2]))
        owners.append(o.name)
OBVH = BVHTree.FromPolygons(ov, ot, all_triangles=True)

# A SEPARATE BVH holding ONLY the declared floor, for the support test. Ray-casting the whole scene returns
# the first surface hit, which for a box is the box itself -- that reported all ten bodies as "not standing
# on Floor_main". Restricting the ray to the floor makes the test answer the question it is asked.
fv, ft = [], []
for o in scene.objects:
    if o.type == "MESH" and o.name == FLOOR:
        vs, ts = tris_of(o, deps)
        base = len(fv)
        fv.extend(vs)
        ft.extend((base + t[0], base + t[1], base + t[2]) for t in ts)
FBVH = BVHTree.FromPolygons(fv, ft, all_triangles=True) if ft else None
if FBVH is None:
    raise SystemExit(f"FATAL: no geometry found for the declared floor '{FLOOR}'")
print("=" * 112)
print(f"AUTHORITATIVE clearance check | {BLEND.name}")
print(f"  floor '{FLOOR}' excluded from obstacles (standing on it is the requirement, not a defect)")
print(f"  obstacle meshes {len(set(owners))}  triangles {len(ot):,}")
print(f"  animated bodies {len(anims)}: {[o.name for o in anims]}")
print("=" * 112)

if TRAJ_P:
    _raw = json.loads(TRAJ_P.read_text(encoding="utf-8"))
    # The render input wraps the rows under "bodies"; the solver's own record is a bare mapping. Both are
    # accepted so the check can be run against either without a conversion step that could differ.
    TRAJ = _raw["bodies"] if isinstance(_raw, dict) and "bodies" in _raw else _raw
else:
    TRAJ = None
BIND = None
if TRAJ:
    # With a trajectory the bodies are posed per frame, so the check tests the whole animation rather than
    # only the pose the blend was saved in. Without one it tests the saved pose.
    from mathutils import Matrix, Quaternion

    def q_b(q):
        x, y, z, w = (float(c) for c in q)
        return Quaternion((w, x, y, z))

    def t_wb(row):
        return (Matrix.Translation(Vector(row["position_m"]))
                @ q_b(row["quaternion_xyzw"]).to_matrix().to_4x4())

    BIND = {o.name: o for o in anims}
    name_of = {}
    for obj in anims:
        for bid in TRAJ:
            # Bodies are bound by the object name the build gave them; recover by prefix.
            if obj.name.startswith("box" + bid + "_") or obj.name.startswith("trigger_"):
                if bid != "-1" and obj.name.startswith("box" + bid + "_"):
                    name_of[bid] = obj
                elif bid == "-1" and obj.name.startswith("trigger_"):
                    name_of[bid] = obj
    scene.frame_set(1)
    bpy.context.view_layer.update()
    t_wv0 = {bid: o.matrix_world.copy() for bid, o in name_of.items()}
    t_wb0 = {bid: t_wb(TRAJ[bid][0]) for bid in name_of}
    print(f"  trajectory supplied: {len(name_of)} bodies will be posed per frame")

frames = []
if TRAJ:
    n = len(TRAJ[next(iter(TRAJ))])
    idx = list(range(n))
    if MAX_FRAMES:
        idx = idx[:MAX_FRAMES]
        if n - 1 not in idx:
            idx.append(n - 1)
    print(f"  testing {len(idx)} frames")
else:
    idx = [0]

worst = {"overlap_tris": 0, "body": None, "frame": None, "obstacles": {}}
bad_support = []
for f in idx:
    if TRAJ:
        scene.frame_set(f + 1)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        for bid, o in name_of.items():
            row = min(TRAJ[bid], key=lambda r: abs(int(r["frame"]) - f))
            o.matrix_world = t_wb(row) @ t_wb0[bid].inverted() @ t_wv0[bid]
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
    else:
        dg = deps

    frame_rec = {"frame": f, "bodies": {}}
    for o in anims:
        vs, ts = tris_of(o, dg)
        bvh = BVHTree.FromPolygons(vs, ts, all_triangles=False)
        hits = bvh.overlap(OBVH)
        by = {}
        # `overlap` returns (index_in_self, index_in_other) with self = the BODY, so the obstacle triangle
        # index is the second element and `owners` is indexed by it.
        for a, b in hits:
            by[owners[b]] = by.get(owners[b], 0) + 1
        # Support: cast against the FLOOR-ONLY BVH, so the ray cannot land on the body itself.
        cx = sum(v.x for v in vs) / len(vs)
        cy = sum(v.y for v in vs) / len(vs)
        hit = FBVH.ray_cast(Vector((cx, cy, 3.0)), Vector((0, 0, -1)), 10.0)
        sup = FLOOR if hit[0] is not None else "<nothing>"
        frame_rec["bodies"][o.name] = {"overlap_tris": len(hits), "overlap_obstacles": by,
                                       "support": sup}
        if len(hits) > worst["overlap_tris"]:
            worst = {"overlap_tris": len(hits), "body": o.name, "frame": f, "obstacles": by}
        if sup != FLOOR:
            bad_support.append({"frame": f, "body": o.name, "support": sup})
    frames.append(frame_rec)
    if f in (idx[0], idx[-1]):
        print(f"    frame {f:3d}: " + "  ".join(
            f"{o.name.split('_')[0]}:{frame_rec['bodies'][o.name]['overlap_tris']}t"
            f"/{frame_rec['bodies'][o.name]['support']}" for o in sorted(anims, key=lambda x: x.name)))

print("")
print("=" * 112)
if worst["body"]:
    print(f"  worst overlap: {worst['body']} at frame {worst['frame']} -> "
          f"{worst['overlap_tris']} triangle pairs with {worst['obstacles']}")
else:
    print("  worst overlap: none")
print(f"  bodies not standing on '{FLOOR}': {len(bad_support)}"
      f"{'' if not bad_support else '  e.g. ' + json.dumps(bad_support[:4])}")
failed = bool(worst["overlap_tris"]) or bool(bad_support)
report = {"blend": str(BLEND), "floor": FLOOR, "obstacle_meshes": len(set(owners)),
          "obstacle_triangles": len(ot), "bodies": [o.name for o in anims],
          "frames_tested": len(idx), "worst_overlap": worst,
          "support_violations": bad_support[:40], "n_support_violations": len(bad_support),
          "frames": frames, "passed": not failed}
print(f"  VERDICT: {'FAIL' if failed else 'PASS'}")
print("=" * 112)
if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
sys.exit(1 if failed else 0)
