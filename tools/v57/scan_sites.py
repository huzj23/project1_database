"""Find a chain site whose boxes touch nothing but the declared floor, in WORLD space.

THE MISTAKE THIS TOOL IS BUILT TO AVOID
---------------------------------------
Choosing a site went wrong three times, always the same way: the tool described the boxes with a model of its
own instead of with the geometry that actually gets built. In order:

  1. only the floor under each box CENTRE was tested, so a stone beside the centre passed -- while the
     authoritative check later found a box overlapping `stones` 304 times;
  2. the asset's local frame was guessed and a yaw divided out of it, but `import_asset_object` permutes and
     scales axes, so the guessed frame described a box rotated 90 degrees from the real one;
  3. `BVHTree.overlap` returns `(index_in_self, index_in_other)` and the pair was read backwards, which made
     the test compare the probe with itself and call every site clear.

So this version does the one thing that cannot drift from the build: it calls `import_asset_object` itself,
takes the resulting local frame, composes the placement exactly as `preview_arc.py` does, and asks
`BVHTree.overlap` whether the resulting world-space box actually intersects the obstacles. The box tested is
the visual's oriented AABB, which CONTAINS the visual mesh, so clearing it is the conservative condition.

VALIDATION IS BUILT IN
----------------------
`--expect` names a site whose overlap pattern is already known from an independent measurement. The tool
compares its own result against it and exits non-zero on disagreement, so a silent regression in this file
cannot be mistaken for a clean site. The known case is the site now in use, measured independently by
tools/v57/clearance_check.py against the built blend:

    (-1.20, +12.20) chord +30  ->  overlap on boxes 2, 3, 6, 7, 8 with `stones`

Usage:
    blender --background --factory-startup --python tools/v57/scan_sites.py -- \
        --blend <source blend> --proxies <dir> --out report.json \
        [--n 9] [--arc-r 2.0] [--pitch-m 0.155] [--expect "-1.20,12.20,30,2,3,6,7,8"]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "v56"))
from box_visual import import_asset_object  # noqa: E402

BLEND = Path(ARGS["blend"]).resolve()
PROXY_DIR = Path(ARGS["proxies"]).resolve()
OUT = Path(ARGS["out"]).resolve() if ARGS.get("out") else None
FLOOR = ARGS.get("floor", "Floor_main")
N = int(ARGS.get("n", "9"))
ARC_R = float(ARGS.get("arc_r", "2.0"))
PITCH = float(ARGS.get("pitch_m", "0.155"))
# The rendered pose is the SETTLED one, and `place_and_settle` spawns each body 2 mm above its seat.
SPAWN_CLEARANCE_M = float(ARGS.get("spawn_clearance_mm", "2.0")) / 1000.0
# Every box is also tested this far above and below the seated height, because a toppling box sweeps through
# that band. Requiring clearance across the band keeps the whole motion clean, not only frame 0.
BAND_M = float(ARGS.get("band_mm", "15.0")) / 1000.0
# INFLATION turns "does not overlap" into "does not overlap by at least this much". It exists because an
# exact-contact test is not enough in practice: at (-1.10,+11.70) the enclosing-box test reported zero
# overlap while the built geometry grazed a decorative `leaves` surface in 16 triangle pairs. A few
# millimetres of separation is the difference between a box resting on the floor and a box touching foliage,
# and requiring it costs nothing but a slightly smaller set of acceptable sites.
INFLATE_M = float(ARGS.get("inflate_mm", "0.0")) / 1000.0
SCAN = ARGS.get("scan", "1") in ("1", "true", "yes")

ASSET_ROOT = ROOT / "models" / "gso"
DIMS = {
    "Supernatural_Ouija_Board_Game": [0.062496879194, 0.275466365908, 0.408406312812],
    "Hasbro_Trivial_Pursuit_Family_Edition_Game": [0.073462, 0.209265, 0.272852],
    "Hasbro_Cranium_Performance_and_Acting_Game": [0.055838, 0.207669099, 0.272573856],
    "LEGO_Star_Wars_Advent_Calendar": [0.0782, 0.2659, 0.3871],
}
ORDER = ["Supernatural_Ouija_Board_Game",
         "Hasbro_Trivial_Pursuit_Family_Edition_Game",
         "Hasbro_Cranium_Performance_and_Acting_Game"]
TRIGGER = "LEGO_Star_Wars_Advent_Calendar"
SHORT = {"Supernatural_Ouija_Board_Game": "Ouija",
         "Hasbro_Trivial_Pursuit_Family_Edition_Game": "Trivial",
         "Hasbro_Cranium_Performance_and_Acting_Game": "Cranium",
         "LEGO_Star_Wars_Advent_Calendar": "Trigger"}

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene

print("=" * 104)
print(f"clear-site scan | {BLEND.name}")
print("=" * 104)

# ---------------------------------------------------------------------------------------------
# Import each asset once, through the SAME function the build uses, and keep its raw frame and local AABB.
# ---------------------------------------------------------------------------------------------
asset_frame = {}
for aid in list(DIMS):
    proxy = PROXY_DIR / f"{aid}__proxy_collision.obj"
    if not proxy.is_file():
        raise SystemExit(f"FATAL: proxy missing for {aid}: {proxy}")
    o, rep = import_asset_object(aid, ASSET_ROOT, DIMS[aid], f"scan_{aid}")
    if o is None:
        raise SystemExit(f"FATAL: import failed for {aid}")
    lws = [v.co.copy() for v in o.data.vertices]
    lo = Vector((min(p[i] for p in lws) for i in range(3)))
    hi = Vector((max(p[i] for p in lws) for i in range(3)))
    asset_frame[aid] = {"M_import": o.matrix_world.copy(), "lo": lo, "hi": hi, "size": hi - lo}
    print(f"  {aid:46s} local size {[round(v, 4) for v in (hi - lo)]}")
    bpy.data.objects.remove(o, do_unlink=True)

# ---------------------------------------------------------------------------------------------
# Obstacle BVH, world space, everything except the floor.
# ---------------------------------------------------------------------------------------------
deps = bpy.context.evaluated_depsgraph_get()
ov, ot, owners = [], [], []
for ob in scene.objects:
    if ob.type != "MESH" or ob.name == FLOOR:
        continue
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        mw = ev.matrix_world
        base = len(ov)
        ov.extend([mw @ v.co for v in me.vertices])
        for p in me.polygons:
            vs = list(p.vertices)
            for k in range(1, len(vs) - 1):
                ot.append((base + vs[0], base + vs[k], base + vs[k + 1]))
                owners.append(ob.name)
    finally:
        ev.to_mesh_clear()
OBVH = BVHTree.FromPolygons(ov, ot, all_triangles=True)
print(f"  obstacle triangles {len(ot):,}  meshes {len(set(owners))}")


def floor_z(x, y):
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 2.0), (0, 0, -1), distance=8.0)
    return loc.z if (ok and obj.name == FLOOR) else None


def box_overlap(centre, yaw_rad, aid):
    """(overlap pairs, obstacle mesh names) for one placed box, in world space.

    `overlap` returns (index_in_self, index_in_other); self is OBVH, so the FIRST element indexes the
    obstacle triangles and `owners` is indexed by it.
    """
    fr = asset_frame[aid]
    M_world = (Matrix.Translation(Vector(centre))
               @ Matrix.Rotation(yaw_rad, 4, "Z")
               @ fr["M_import"])
    lo, hi = fr["lo"], fr["hi"]
    # The box is inflated by INFLATE_M on every side, so a clearance of zero here means the real box has at
    # least INFLATE_M of air around it. With the default of 0 the test is exact contact.
    lo = lo - Vector((INFLATE_M, INFLATE_M, INFLATE_M))
    hi = hi + Vector((INFLATE_M, INFLATE_M, INFLATE_M))
    half = (hi - lo) / 2.0
    ctr = (lo + hi) / 2.0
    corners = [(ctr.x + sx * half.x, ctr.y + sy * half.y, ctr.z + sz * half.z)
               for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    wc = [M_world @ Vector(c) for c in corners]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for f in faces:
        tris.append((f[0], f[1], f[2]))
        tris.append((f[0], f[2], f[3]))
    box_bvh = BVHTree.FromPolygons(wc, tris, all_triangles=True)
    hits = OBVH.overlap(box_bvh)
    return len(hits), sorted({owners[a] for a, b in hits})


def eval_site(cx, cy, chord_deg):
    chord = math.radians(chord_deg)
    total = (N - 1) * PITCH
    phi0 = -total / (2.0 * ARC_R)
    acx = cx - ARC_R * math.sin(phi0 + chord)
    acy = cy + ARC_R * math.cos(phi0 + chord)
    zs, off, all_who = [], 0, set()
    worst_pairs, worst_box = 0, None
    per_box = {}
    for i in range(N):
        aid = ORDER[i % len(ORDER)]
        ang = chord + phi0 + (i * PITCH) / ARC_R
        px = acx + ARC_R * math.sin(ang)
        py = acy - ARC_R * math.cos(ang)
        z = floor_z(px, py)
        if z is None:
            off += 1
            continue
        zs.append(z)
        seat = z + DIMS[aid][2] / 2.0 + SPAWN_CLEARANCE_M
        pairs, who = 0, set()
        for extra in (0.0, BAND_M, -BAND_M):
            p2, w2 = box_overlap([px, py, seat + extra], ang, aid)
            pairs = max(pairs, p2)
            who.update(w2)
        per_box[i] = {"asset": SHORT[aid], "overlap_pairs": pairs, "obstacles": sorted(who)}
        all_who.update(who)
        if pairs > worst_pairs:
            worst_pairs, worst_box = pairs, i
    # The trigger, one pitch and a little behind box 0 along the tangent.
    ang_t = chord + phi0 - (PITCH * 1.05) / ARC_R
    tx = acx + ARC_R * math.sin(ang_t)
    ty = acy - ARC_R * math.cos(ang_t)
    tz = floor_z(tx, ty)
    tpairs, twho = 0, set()
    if tz is None:
        off += 1
    else:
        seat = tz + DIMS[TRIGGER][2] / 2.0 + SPAWN_CLEARANCE_M
        for extra in (0.0, BAND_M, -BAND_M):
            p2, w2 = box_overlap([tx, ty, seat + extra], ang_t, TRIGGER)
            tpairs = max(tpairs, p2)
            twho.update(w2)
        all_who.update(twho)
    per_box["trigger"] = {"asset": "Trigger", "overlap_pairs": tpairs, "obstacles": sorted(twho)}
    return {"cx": cx, "cy": cy, "chord_deg": chord_deg,
            "worst_overlap_pairs": max(worst_pairs, tpairs),
            "obstacles": sorted(all_who), "n_off_floor": off,
            "height_spread_m": (max(zs) - min(zs)) if len(zs) >= 2 else None,
            "n_boxes_on_floor": len(zs), "per_box": per_box,
            "worst_box": worst_box}


# ---------------------------------------------------------------------------------------------
# VALIDATION against an independently measured site. A regression in this file must not look like a clean
# site, so the known case is checked before anything is chosen.
# ---------------------------------------------------------------------------------------------
EXPECT = ARGS.get("expect", "").strip()
validated = None
if EXPECT:
    parts = EXPECT.split(",")
    ecx, ecy, ech = float(parts[0]), float(parts[1]), float(parts[2])
    eboxes = [int(v) for v in parts[3:]]
    r = eval_site(ecx, ecy, ech)
    got = sorted(i for i, v in r["per_box"].items()
                 if i != "trigger" and v["overlap_pairs"] > 0)
    ok = got == sorted(eboxes)
    print("")
    print(f"  VALIDATION at the site in use ({ecx:+.2f},{ecy:+.2f}) chord {ech:+.1f}:")
    print(f"    expected overlapping boxes {sorted(eboxes)}")
    print(f"    this scan measured        {got}")
    print(f"    boxes on the floor        {r['n_boxes_on_floor']}/9")
    for i, v in sorted(r["per_box"].items(), key=lambda kv: str(kv[0])):
        print(f"      {str(i):>7s} {v['asset']:8s} pairs {v['overlap_pairs']:>5d}  {v['obstacles'][:3]}")
    print(f"    VALIDATION {'PASSED' if ok else 'FAILED'}")
    validated = ok
    if not ok:
        print("  FATAL: this scan does not reproduce the independently measured overlap pattern; its")
        print("         verdicts cannot be trusted. Refusing to scan.")
        if OUT:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps({"validation_failed": True, "site": r}, indent=2),
                           encoding="utf-8")
        sys.exit(2)

results = []
if SCAN:
    # The grid is parameterised so the search can be widened to find ANY clear site and then narrowed to
    # find the clear site CLOSEST to the approved view. A single fixed grid cannot do both: the wide grid
    # that found 67 clear sites stepped in 0.5 m jumps and so could not tell whether a clear site existed a
    # few centimetres from the approved one, which is the question that decides how much the look changes.
    gx = [float(v) for v in ARGS.get("gx", "-2.0,-1.6,-1.2,-0.8,-0.4,0.0,0.4,0.8,1.2,1.6,2.0").split(",")]
    gy = [float(v) for v in ARGS.get(
        "gy", "6.5,7.0,7.5,8.0,8.5,9.0,9.5,10.0,10.5,11.0,11.5,12.0,12.5,13.0,13.5,14.0,14.5,15.0,15.5"
    ).split(",")]
    gc = [float(v) for v in ARGS.get(
        "gc", "0.0,15.0,30.0,45.0,60.0,75.0,-15.0,-30.0,-45.0").split(",")]
    print("")
    print(f"  scanning {len(gx)}x{len(gy)}x{len(gc)} = {len(gx) * len(gy) * len(gc)} sites...")
    for cx in gx:
        for cy in gy:
            for chord in gc:
                results.append(eval_site(cx, cy, chord))

clear = [r for r in results if r["worst_overlap_pairs"] == 0 and r["n_off_floor"] == 0]
print("")
print(f"  sites scanned            : {len(results)}")
print(f"  every body on the floor  : {sum(1 for r in results if r['n_off_floor'] == 0)}")
print(f"  CLEAR of all obstacles   : {len(clear)}   (zero overlapping triangle pairs at all 3 heights)")

if clear:
    for r in clear:
        r["_d"] = math.hypot(r["cx"] + 1.20, r["cy"] - 12.20)
    clear.sort(key=lambda r: (r["height_spread_m"] if r["height_spread_m"] is not None else 9))
    print("")
    print(f"  {'centre (x,y)':20s} {'chord':>7s} {'height spread':>14s} {'dist from approved':>19s}")
    for r in clear[:20]:
        hs = r["height_spread_m"]
        print(f"  ({r['cx']:+6.2f},{r['cy']:+6.2f})   {r['chord_deg']:+7.1f} "
              f"{(('%.2f mm' % (hs * 1000)) if hs is not None else 'n/a'):>14s} "
              f"{r['_d']:>19.2f}")
    flattest = [r for r in clear if r["height_spread_m"] is not None
                and r["height_spread_m"] <= 1e-4]
    if flattest:
        flattest.sort(key=lambda r: r["_d"])
        b = flattest[0]
        print("")
        print(f"  NEAREST FULLY FLAT CLEAR SITE to the approved one: centre ({b['cx']:+.2f},{b['cy']:+.2f}) "
              f"chord {b['chord_deg']:+.1f}  height spread {b['height_spread_m'] * 1000:.3f} mm  "
              f"{b['_d']:.2f} m from the approved centre")
        for i, v in sorted(b["per_box"].items(), key=lambda kv: str(kv[0])):
            print(f"      {str(i):>7s} {v['asset']:8s} pairs {v['overlap_pairs']}  {v['obstacles'][:3]}")
    else:
        print("")
        print("  No fully flat clear site; the flattest clear sites are listed above.")
else:
    results.sort(key=lambda r: (r["n_off_floor"], r["worst_overlap_pairs"]))
    print("")
    print("  NO clear site found. Least-bad:")
    print(f"  {'centre (x,y)':20s} {'chord':>7s} {'off floor':>10s} {'pairs':>7s}  obstacles")
    for r in results[:16]:
        print(f"  ({r['cx']:+6.2f},{r['cy']:+6.2f})   {r['chord_deg']:+7.1f} {r['n_off_floor']:>10d} "
              f"{r['worst_overlap_pairs']:>7d}  {r['obstacles'][:4]}")

if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "n": N, "arc_r": ARC_R, "pitch_m": PITCH, "band_m": BAND_M,
        "spawn_clearance_m": SPAWN_CLEARANCE_M,
        "method": "world-space BVHTree.overlap of the oriented visual AABB against all non-floor triangles",
        "validated": validated,
        "asset_frames": {k: {"local_size_m": [round(v, 6) for v in v["size"]]}
                         for k, v in asset_frame.items()},
        "n_scanned": len(results), "n_clear": len(clear),
        "clear": [{k: v for k, v in r.items() if k != "per_box"} for r in clear],
        "all": [{k: v for k, v in r.items() if k != "per_box"} for r in results],
    }, indent=2), encoding="utf-8")
    print(f"\nreport written: {OUT}")
