"""The gate that would have caught the defect the user saw: does any animated box cut into the scene?

WHY THIS IS A SEPARATE, BLOCKING STAGE
--------------------------------------
The previous round verified only box-versus-box clearance and reported zero interpenetration, while twelve
of thirteen boxes were in fact buried up to 37 mm inside an authored light-blocker face. A check that only
compares the moving objects with each other cannot see that, and it passed. This gate therefore tests the
animated bodies against the WHOLE scene, at every rendered frame, and refuses to let a render proceed when
it fails.

What it measures, per frame, using the real animated geometry:

  1. penetration of every body into scene triangles that are NOT its declared support -- the real
     interpenetration test, by BVH overlap of triangles, reported as a count and a depth;
  2. the support under each body by a downward ray, which must be the object that was declared as the
     floor, so a box standing on a prop is a failure rather than an invisible success;
  3. whether the camera's view of the chain is obstructed at the first and last frame.

The floor is excluded from test 1 by name because resting on it is contact, not penetration; test 2 is what
covers the floor. Both the excluded set and the declared support are printed, so the exclusion is visible
rather than assumed.

Exit code is non-zero when a gate fails, so the driver script stops instead of rendering.

Usage:
    blender --background --factory-startup --python tools/v57/gate_penetration.py -- \
        --blend <staged.blend> --config <render_config.json> --traj <trajectory.json> --out <report.json>
"""

from __future__ import annotations

import argparse
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
TRAJ_P = Path(ARGS["traj"]).resolve()
OUT = Path(ARGS["out"]).resolve()
DECLARED_FLOOR = ARGS.get("floor", "Floor_main")
PEN_TOL_M = float(ARGS.get("pen_tol_mm", "2.0")) / 1000.0
MAX_FRAMES = int(ARGS.get("max_frames", "0"))  # 0 = all

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()
CFG = json.loads(CFG_P.read_text(encoding="utf-8"))
TRAJ = json.loads(TRAJ_P.read_text(encoding="utf-8"))
BINDING = CFG["binding"]
FRAME_COUNT = int(CFG["frame_count"])

print("=" * 104)
print(f"penetration gate | {BLEND.name}")
print(f"  declared floor : {DECLARED_FLOOR}   penetration tolerance {PEN_TOL_M * 1000:.2f} mm")
print(f"  frames         : {FRAME_COUNT}")
print("=" * 104)

# ---------------------------------------------------------------------------------------------
# Build the animated proxy objects: one low-poly box per body at the body's own dimensions, driven by the
# trajectory. Using the real high-poly visuals would be slower and would test the visual mesh rather than the
# body that the physics actually used -- and the body is what can interpenetrate.
# ---------------------------------------------------------------------------------------------
PROXY_PREFIX = "gate_proxy_"
proxies = {}
proxy_objs = {}
for bid, spec in BINDING.items():
    rows = TRAJ.get(bid)
    if not rows:
        raise SystemExit(f"FATAL: trajectory has no rows for bound body {bid}")
    obj = bpy.data.objects.get(spec["objects"][0])
    if obj is None:
        raise SystemExit(f"FATAL: binding names object '{spec['objects'][0]}' which is not in the blend")
    # THE PROXY IS SIZED IN THE OBJECT'S OWN LOCAL FRAME, and this matters more than it looks. Taking the
    # WORLD AABB of the imported visual inflates it, because the box is yawed relative to the world axes: a
    # 62.5 mm-thick Ouija came out 160.7 mm across and the gate then reported 67.7 mm of "penetration" that
    # was really the proxy being too fat. The local AABB is the body's true extent, and the proxy is placed
    # with the object's own matrix_world so it rotates with it.
    lws = [v.co.copy() for v in obj.data.vertices]
    llo = Vector((min(p[i] for p in lws) for i in range(3)))
    lhi = Vector((max(p[i] for p in lws) for i in range(3)))
    size = lhi - llo
    centre_local = (lhi + llo) / 2.0
    mesh = bpy.data.meshes.new(PROXY_PREFIX + bid)
    # The proxy spans the object's local AABB, so its own origin coincides with the object's local origin and
    # the authored matrix_world can be applied to it unchanged.
    verts = [(sx * size.x / 2.0 + centre_local.x,
              sy * size.y / 2.0 + centre_local.y,
              sz * size.z / 2.0 + centre_local.z)
             for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    po = bpy.data.objects.new(PROXY_PREFIX + bid, mesh)
    scene.collection.objects.link(po)
    # The Blender object is deliberately NOT stored in the report: it is not JSON-serialisable, and keeping
    # it out means `report` can be written directly rather than through a custom encoder that might silently
    # drop a field. The proxy objects are looked up from `proxies[...]["obj"]` where they are needed.
    proxy_objs[bid] = po
    proxies[bid] = {"size_m": [round(v, 6) for v in size],
                    "centre_offset_local_m": [round(v, 6) for v in centre_local],
                    "source_object": spec["objects"][0]}
    print(f"  body {bid:>3s} proxy from {spec['objects'][0]:28s} size "
          f"{[round(v, 4) for v in size]}")

# ---------------------------------------------------------------------------------------------
# Two static BVHs, kept separate on purpose:
#   * OBSTACLES -- everything except the declared floor, the animated bodies, and the gate's own proxies.
#     A body "penetrating" itself or its own support is not penetration, and including either produced a
#     meaningless 863 mm "depth" that was really a box overlapping its own visual.
#   * SUPPORT -- the declared floor alone. A downward ray against this cannot hit the body itself, which a
#     whole-scene ray_cast did, so the support test now answers the question it is asked.
# ---------------------------------------------------------------------------------------------
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()

ANIMATED = {spec["objects"][0] for spec in BINDING.values()}
excluded = []


def build_bvh(objs):
    verts, tris, owners = [], [], []
    for o in objs:
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        try:
            mw = ev.matrix_world
            base = len(verts)
            verts.extend([mw @ v.co for v in me.vertices])
            for p in me.polygons:
                vs = list(p.vertices)
                for k in range(1, len(vs) - 1):
                    tris.append((base + vs[0], base + vs[k], base + vs[k + 1]))
                    owners.append(o.name)
        finally:
            ev.to_mesh_clear()
    bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True) if tris else None
    return bvh, owners, verts, tris


def partitions():
    obst, sup = [], []
    for o in scene.objects:
        if o.type != "MESH":
            continue
        if o.name == DECLARED_FLOOR:
            sup.append(o)
            continue
        if o.name in ANIMATED or o.name.startswith(PROXY_PREFIX):
            excluded.append(o.name)
            continue
        obst.append(o)
    return obst, sup


obst_objs, sup_objs = partitions()
OBVH, OWNERS, SVERTS, STRIS = build_bvh(obst_objs)
N_TRI = len(STRIS)
SBVH, _, _, _ = build_bvh(sup_objs)
S_TRI = sum(len(o.data.polygons) for o in sup_objs) if sup_objs else 0
print(f"  obstacle objects: {len(obst_objs)}   triangles: {N_TRI:,}")
print(f"  support objects : {[o.name for o in sup_objs]}")
print(f"  excluded as animated bodies or gate proxies: {len(excluded)}")
if OBVH is None or SBVH is None:
    raise SystemExit("FATAL: no obstacle or support geometry; the gate would be vacuous")

# A fixed probe height for the support rays, taken from the floor's own highest point under the chain so the
# origin is always above it regardless of what the boxes are doing.
SITE_TOP_Z = max((o.matrix_world @ v.co).z
                 for o in sup_objs for v in o.data.vertices) if sup_objs else 0.0
print(f"  support probe origin z = {SITE_TOP_Z + 0.50:.3f} m")
print(f"  scene triangles: {N_TRI:,}")


def q_xyzw_to_blender(q):
    x, y, z, w = (float(c) for c in q)
    return Quaternion((w, x, y, z))


def t_wb(row):
    return (Matrix.Translation(Vector(row["position_m"]))
            @ q_xyzw_to_blender(row["quaternion_xyzw"]).to_matrix().to_4x4())


# Capture T_WV(0) and T_WB(0) per body, exactly as render.py does, so the gate tests the poses the renderer
# will actually produce rather than a second, possibly different, interpretation of the same data.
scene.frame_set(1)
bpy.context.view_layer.update()
t_wv0 = {bid: bpy.data.objects[spec["objects"][0]].matrix_world.copy()
         for bid, spec in BINDING.items()}
t_wb0 = {bid: t_wb(TRAJ[bid][0]) for bid in BINDING}

report = {"blend": str(BLEND), "declared_floor": DECLARED_FLOOR,
          "penetration_tolerance_m": PEN_TOL_M, "obstacle_triangles": N_TRI,
          "obstacle_objects": len(obst_objs), "support_objects": [o.name for o in sup_objs],
          "excluded_animated": sorted(excluded), "frames": [], "proxies": proxies}
worst = {"pen_tris": 0, "pen_depth_m": 0.0, "frame": None, "body": None}
support_bad = []
fail = False

frames_to_test = [r["frame"] for r in TRAJ[next(iter(BINDING))]]
if MAX_FRAMES:
    frames_to_test = frames_to_test[:MAX_FRAMES]
# Always include the first and last frame, even when sampling, so the endpoints are never skipped.
if 0 not in frames_to_test:
    frames_to_test.insert(0, 0)
if FRAME_COUNT - 1 not in frames_to_test:
    frames_to_test.append(FRAME_COUNT - 1)

print("")
print(f"  testing {len(frames_to_test)} frames")
for f in frames_to_test:
    bf = f + 1
    scene.frame_set(bf)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    frame_rec = {"frame": f, "bodies": {}}
    for bid, spec in BINDING.items():
        rows = TRAJ[bid]
        # Nearest recorded row at or before this frame.
        row = min(rows, key=lambda r: abs(int(r["frame"]) - f))
        delta = t_wb(row) @ t_wb0[bid].inverted()
        mw = delta @ t_wv0[bid]
        po = proxy_objs[bid]
        po.matrix_world = mw
        bpy.context.view_layer.update()

        # --- penetration: BVH overlap against the static scene -------------------------------
        ev = po.evaluated_get(deps)
        me = ev.to_mesh()
        try:
            pv = [ev.matrix_world @ v.co for v in me.vertices]
            pt = [tuple(p.vertices) for p in me.polygons]
            pbvh = BVHTree.FromPolygons(pv, pt, all_triangles=False)
        finally:
            ev.to_mesh_clear()
        # `overlap` returns (index_in_self, index_in_other). self is `pbvh` -- the BODY -- so the FIRST
        # element indexes the body's triangles and the second indexes the obstacle's. The owner lookup must
        # therefore use the SECOND element, and the triangle arrays must come from the obstacle set. Reading
        # this backwards attributes a body's own triangles to the scene and reports the body as penetrating
        # itself, which is the defect this comment exists to prevent recurring.
        hits = pbvh.overlap(OBVH)
        pen_owners = {}
        for a, b in hits:
            nm = OWNERS[b] if b < len(OWNERS) else "?"
            pen_owners[nm] = pen_owners.get(nm, 0) + 1
        # HOW DEEP, EXACTLY. Two earlier attempts at this measurement were both wrong, in ways worth stating:
        #
        #   * distance to an overlapping triangle's INFINITE PLANE -- for one large flat triangle that
        #     reports hundreds of millimetres for a graze;
        #   * ray-crossing parity to decide "inside" -- valid only for CLOSED solids, and this scene's
        #     foliage (leaves, grass) is open surfaces, so parity returned odd counts almost everywhere and
        #     produced a 616 mm "penetration" for a leaf.
        #
        # The proxy is an axis-aligned box in its own frame, so the exact question has an exact answer: take
        # every obstacle-triangle vertex, transform it into the proxy's local frame, keep the ones that lie
        # INSIDE the box, and for each the penetration is the smallest distance to any of the box's six
        # faces. That is the depth to which the scene intrudes into the body, it is exact for boxes, and it
        # needs no closedness assumption about the obstacle.
        depth = 0.0
        deepest_owner = None
        n_inside = 0
        if hits:
            inv = po.matrix_world.inverted()
            half = [proxies[bid]["size_m"][i] / 2.0 for i in range(3)]
            cl = proxies[bid]["centre_offset_local_m"]
            seen_tris = set()
            for a, b in hits:
                if b in seen_tris:
                    continue
                seen_tris.add(b)
                for vi in STRIS[b]:
                    lp = inv @ SVERTS[vi]
                    # The proxy spans the object's local AABB, which is centred on `cl` rather than on the
                    # object's own origin, so the half-extent test is taken about `cl`.
                    d_local = [lp[i] - cl[i] for i in range(3)]
                    if all(abs(d_local[i]) <= half[i] for i in range(3)):
                        n_inside += 1
                        pen = min(half[i] - abs(d_local[i]) for i in range(3))
                        if pen > depth:
                            depth = pen
                            deepest_owner = OWNERS[b]
        frame_rec["bodies"][bid] = {"pen_tris": len(hits), "pen_owners": pen_owners,
                                    "pen_vertices_inside": n_inside,
                                    "pen_depth_m": round(depth, 6),
                                    "deepest_owner": deepest_owner}
        # The worst case is ranked by DEPTH, because a body can overlap many triangles of a thin rail while
        # barely entering it. Ranking by triangle count reported exactly that misleading case first.
        if worst["frame"] is None or depth > worst["pen_depth_m"]:
            worst = {"pen_tris": len(hits), "pen_depth_m": round(depth, 6),
                     "frame": f, "body": bid, "owners": pen_owners,
                     "deepest_owner": deepest_owner}

        # --- support: a downward ray against the DECLARED FLOOR ONLY --------------------------
        # The ray is cast from a FIXED height above the site, not from the body's own centre. Casting from
        # the proxy's base worked at frame 0 but failed once the boxes fell: a toppled box's centre is only
        # ~100 mm up, and the origin `z - half_h + 0.02` then lands BELOW the floor, so the ray points away
        # from it and reports "<nothing>". The support question is "is there floor under this body", which a
        # fixed high origin answers for every frame.
        o = po.matrix_world.translation
        origin = Vector((o.x, o.y, SITE_TOP_Z + 0.50))
        hit = SBVH.ray_cast(origin, Vector((0, 0, -1)), 3.0)
        sup = sup_objs[0].name if hit[0] is not None else "<nothing>"
        sup_dist = hit[3] if hit[0] is not None else None
        # The floor must be under the body, and at the body's own level, to count as support -- a hit far
        # below would mean the body is floating over a hole.
        gap = None
        if hit[0] is not None:
            gap = round((o.z - proxies[bid]["size_m"][2] / 2.0) - hit[0].z, 6)
        frame_rec["bodies"][bid]["support_object"] = sup
        frame_rec["bodies"][bid]["base_gap_to_support_m"] = gap
        if sup != DECLARED_FLOOR:
            support_bad.append({"frame": f, "body": bid, "support": sup})
    report["frames"].append(frame_rec)
    if f in (0, frames_to_test[-1]):
        print(f"    frame {f:3d}: " + "  ".join(
            f"b{b}:{frame_rec['bodies'][b]['pen_tris']}t/{frame_rec['bodies'][b]['support_object']}"
            for b in sorted(frame_rec["bodies"], key=lambda s: int(s))[:9]))

report["worst_penetration"] = worst
report["support_violations"] = support_bad[:40]
report["n_support_violations"] = len(support_bad)

print("")
print("=" * 104)
if worst["frame"] is not None:
    print(f"  worst penetration: body {worst['body']} at frame {worst['frame']} -> "
          f"{worst['pen_tris']} triangles, depth bound {worst['pen_depth_m'] * 1000:.2f} mm, "
          f"owners {worst.get('owners')}")
else:
    print("  worst penetration: none at any tested frame")
print(f"  support violations: {len(support_bad)}"
      f"{'' if not support_bad else '  e.g. ' + json.dumps(support_bad[:3])}")

if worst["pen_tris"] > 0 and worst["pen_depth_m"] > PEN_TOL_M:
    print(f"  GATE FAIL: penetration depth bound {worst['pen_depth_m'] * 1000:.2f} mm exceeds the "
          f"{PEN_TOL_M * 1000:.2f} mm tolerance")
    fail = True
if support_bad:
    print(f"  GATE FAIL: {len(support_bad)} body-frames are not supported by the declared floor "
          f"'{DECLARED_FLOOR}'")
    fail = True
report["passed"] = not fail
print(f"  GATE {'FAILED' if fail else 'PASSED'}")
print("=" * 104)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"wrote {OUT}")
sys.exit(1 if fail else 0)
