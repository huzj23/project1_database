"""A2 recon: measure the Hidden Alley geometry around the chosen board.

Read-only Blender pass. Opens ph_hidden_alley.blend (a Blender 4.0 file, opened
by local Blender 4.2.23), and reports in world metres:

  * every mesh object whose world AABB intersects a probe box around the board;
  * exact AABB / tri-count for the named support objects;
  * a ray bank at a grid of (y, z) firing -X from x = +3, reporting the FIRST
    exposed surface a can travelling in -X would meet, and which object it
    belongs to.  This is the question the whole task turns on: does the 50 mm
    plinth kerb stop a rolling can before it reaches the board's face?
  * the same bank firing +Y and -Y along the wall, to map the plinth profile;
  * scatter intrusion: triangles of stones / grass / leaves inside the corridor.

Uses mathutils.bvhtree (C speed).  No render.  Writes JSON only.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[0]) if ARGV else Path("recon.json")

BLEND = ("D:/workspace/project1_database/models/backgrounds/candidates/"
         "hidden_alley/extracted/ph_hidden_alley.blend")

BOARD_MIN = Vector((-2.152816, 1.426557, 0.009686))
BOARD_MAX = Vector((-2.017358, 2.887637, 0.399251))

SUPPORT = ["Floor_main", "apartment_walls", "base_tripple_01.003",
           "dado_tripple_01.003", "wooden_boards.001", "wooden_boards",
           "stones", "grass", "leaves", "Floor", "floor_main"]

T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def obj_world_aabb(ob):
    mw = ob.matrix_world
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    for c in ob.bound_box:
        p = mw @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], p[i])
            mx[i] = max(mx[i], p[i])
    return mn, mx


def build_bvh(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    mw = ev.matrix_world
    vs = [mw @ v.co for v in me.vertices]
    me.calc_loop_triangles()
    ts = [tuple(t.vertices) for t in me.loop_triangles]
    bvh = None
    if ts:
        bvh = BVHTree.FromPolygons([tuple(v) for v in vs], ts, all_triangles=True)
    ev.to_mesh_clear()
    return vs, ts, bvh


def main() -> int:
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    log(f"opened {BLEND}")
    scn = bpy.context.scene
    log(f"unit scale_length={scn.unit_settings.scale_length} "
        f"fps={scn.render.fps} frames {scn.frame_start}..{scn.frame_end}")

    probe_min = Vector((-4.5, -0.3, -1.5))
    probe_max = Vector((0.5, 5.3, 2.8))

    report = {"blend": BLEND, "objects": [], "named": {}, "rays_negx": [],
              "rays_posy": [], "rays_negy": [], "scatter": {}}

    report["objects"] = []
    n_mesh = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        n_mesh += 1
        try:
            mn, mx = obj_world_aabb(ob)
        except Exception as exc:  # noqa: BLE001
            log(f"  skip {ob.name}: {exc}")
            continue
        if not (mx.x >= probe_min.x and mn.x <= probe_max.x and
                mx.y >= probe_min.y and mn.y <= probe_max.y and
                mx.z >= probe_min.z and mn.z <= probe_max.z):
            continue
        report["objects"].append({
            "name": ob.name,
            "aabb_min": list(mn), "aabb_max": list(mx),
            "verts": len(ob.data.vertices), "faces": len(ob.data.polygons),
            "materials": [m.name if m else None for m in ob.data.materials],
            "scale": list(ob.scale), "location": list(ob.location),
            "hide_render": bool(ob.hide_render),
        })
    report["objects"].sort(
        key=lambda r: -((r["aabb_max"][0] - r["aabb_min"][0]) *
                        (r["aabb_max"][1] - r["aabb_min"][1])))
    log(f"{n_mesh} mesh objects in file; {len(report['objects'])} intersect probe box")

    dg = bpy.context.evaluated_depsgraph_get()
    surfaces = []
    for name in SUPPORT:
        ob = bpy.data.objects.get(name)
        if ob is None:
            report["named"][name] = {"present": False}
            continue
        vs, ts, bvh = build_bvh(ob, dg)
        mn = [min(v[i] for v in vs) for i in range(3)] if vs else None
        mx = [max(v[i] for v in vs) for i in range(3)] if vs else None
        report["named"][name] = {"present": True, "n_verts": len(vs),
                                 "n_tris": len(ts),
                                 "aabb_min": mn, "aabb_max": mx}
        surfaces.append((name, vs, ts, bvh))
        log(f"{name}: {len(vs)}v {len(ts)}t")
        if mn:
            log(f"    x[{mn[0]:+.4f},{mx[0]:+.4f}] y[{mn[1]:+.4f},{mx[1]:+.4f}] "
                f"z[{mn[2]:+.4f},{mx[2]:+.4f}]")

    def first_hit(origin: Vector, direction: Vector):
        best = None
        for name, vs, ts, bvh in surfaces:
            if bvh is None:
                continue
            loc, nrm, idx, dist = bvh.ray_cast(origin, direction)
            if loc is None:
                continue
            if best is None or dist < best[0]:
                best = (dist, loc, name, nrm)
        return best

    probe_zs = [-0.10, -0.045, -0.035, -0.025, -0.015, 0.0, 0.008, 0.010,
                0.012, 0.020, 0.030, 0.040, 0.060, 0.090, 0.120, 0.160,
                0.200, 0.250, 0.300, 0.350, 0.390, 0.450]
    probe_ys = [1.30, 1.437, 1.50, 1.60, 1.80, 2.00, 2.20, 2.40, 2.60,
                2.75, 2.877, 2.95, 3.10]

    log("ray bank: -X from x=+3.0")
    for y in probe_ys:
        row = {"y": y, "hits": {}}
        for z in probe_zs:
            h = first_hit(Vector((3.0, y, z)), Vector((-1.0, 0.0, 0.0)))
            if h is not None:
                row["hits"][f"{z:+.4f}"] = {"x": h[1].x, "object": h[2],
                                            "normal_x": h[3].x, "dist": h[0]}
        report["rays_negx"].append(row)

    print()
    print("[recon] FIRST surface met by a -X ray from x=+3  ->  x coordinate")
    print("  y\\z    " + "".join(f"{z:+8.4f}" for z in probe_zs))
    for row in report["rays_negx"]:
        cells = []
        for z in probe_zs:
            h = row["hits"].get(f"{z:+.4f}")
            cells.append(f"{h['x']:+8.4f}" if h else "    none")
        print(f"  {row['y']:.3f} " + "".join(cells))
    print()
    print("[recon] object that surface belongs to")
    print("  y\\z    " + "".join(f"{z:+8.4f}" for z in probe_zs))
    for row in report["rays_negx"]:
        cells = []
        for z in probe_zs:
            h = row["hits"].get(f"{z:+.4f}")
            cells.append(f"{h['object'][:8]:>8s}" if h else "    none")
        print(f"  {row['y']:.3f} " + "".join(cells))

    # ---- vertical profile: +Z rays from below at fixed (x, y) ---------------
    # Finds the TOP surface height of the plinth/floor at that (x,y).
    log("vertical scan: top surface z at a grid of (x,y)")
    vscan = []
    xs = [-2.30, -2.25, -2.20, -2.18, -2.16, -2.14, -2.12, -2.10, -2.08,
          -2.06, -2.04, -2.02, -2.00, -1.98, -1.95, -1.90, -1.80, -1.60,
          -1.40, -1.20, -1.00]
    ys = [1.40, 1.50, 1.80, 2.20, 2.60, 2.90, 3.20, 3.60, 4.00, 4.60]
    for y in ys:
        row = {"y": y, "top": {}}
        for x in xs:
            h = first_hit(Vector((x, y, -1.0)), Vector((0.0, 0.0, 1.0)))
            if h is not None:
                row["top"][f"{x:+.4f}"] = {"z": h[1].z, "object": h[2]}
        vscan.append(row)
    report["vertical_scan"] = vscan
    print()
    print("[recon] top surface z for a +Z ray from z=-1  (blank = no hit)")
    print("  y\\x    " + "".join(f"{x:+8.3f}" for x in xs))
    for row in vscan:
        cells = []
        for x in xs:
            h = row["top"].get(f"{x:+.4f}")
            cells.append(f"{h['z']:+8.4f}" if h else "        ")
        print(f"  {row['y']:.2f}  " + "".join(cells))
    print()
    print("[recon] object owning that top surface")
    print("  y\\x    " + "".join(f"{x:+8.3f}" for x in xs))
    for row in vscan:
        cells = []
        for x in xs:
            h = row["top"].get(f"{x:+.4f}")
            cells.append(f"{h['object'][:8]:>8s}" if h else "        ")
        print(f"  {row['y']:.2f}  " + "".join(cells))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"written {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
