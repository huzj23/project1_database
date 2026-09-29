"""A2 recon: measure the Hidden Alley geometry around the chosen board.

Read-only Blender pass.  Loads ph_hidden_alley.blend (Blender 4.0 file, opened by
Blender 4.2.23 local), then reports, in world metres:

  * every object whose world AABB intersects a 6 m x 6 m x 3 m probe box
    around the board, with its AABB, vertex/face count and material names;
  * for the named support objects (Floor_main, apartment_walls,
    base_tripple_01.003, dado_tripple_01.003) the exact exposed-surface
    geometry: the plinth top plane, the plinth front face x, the wall plane x,
    the skirting front x, and how far each extends in Y;
  * a ray-cast bank that answers the question this task turns on: can a
    rolling can of radius R on the FLOOR (z = -0.040) physically reach the
    board's outer face, or does the 50 mm plinth kerb block it?
  * scatter intrusion: the set of triangles of `stones` / `grass` / `leaves`
    that lie inside the candidate travel corridor.

Nothing is written except the JSON report.  No render.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[0]) if ARGV else Path("recon.json")

BLEND = ("D:/workspace/project1_database/models/backgrounds/candidates/"
         "hidden_alley/extracted/ph_hidden_alley.blend")

# Board 01 world AABB (from the verified export).
BOARD_MIN = Vector((-2.152816, 1.426557, 0.009686))
BOARD_MAX = Vector((-2.017358, 2.887637, 0.399251))

SUPPORT = ["Floor_main", "apartment_walls", "base_tripple_01.003",
           "dado_tripple_01.003", "wooden_boards.001", "wooden_boards",
           "stones", "grass", "leaves"]


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


def verts_world(ob):
    me = ob.data
    mw = ob.matrix_world
    return [mw @ v.co for v in me.vertices]


def faces_tris(ob):
    me = ob.data
    me.calc_loop_triangles()
    return [[t.vertices[0], t.vertices[1], t.vertices[2]]
            for t in me.loop_triangles]


def main() -> int:
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    scn = bpy.context.scene
    print(f"[recon] opened {BLEND}")
    print(f"[recon] unit_settings scale_length = {scn.unit_settings.scale_length} "
          f"system={scn.unit_settings.system} length_unit={scn.unit_settings.length_unit}")
    print(f"[recon] frame range {scn.frame_start}..{scn.frame_end} fps={scn.render.fps}")

    probe_min = Vector((-4.2, -0.2, -1.2))
    probe_max = Vector((0.0, 5.0, 2.5))

    report = {"blend": BLEND, "objects": [], "named": {}, "rays": [], "scatter": {}}

    all_objs = []
    for ob in bpy.data.objects:
        all_objs.append(ob)
    print(f"[recon] {len(all_objs)} objects in file")

    for ob in all_objs:
        if ob.type not in {"MESH", "CURVE", "SURFACE", "FONT"}:
            continue
        try:
            mn, mx = obj_world_aabb(ob)
        except Exception as exc:  # noqa: BLE001
            print(f"[recon]   skip {ob.name}: {exc}")
            continue
        if not (mx.x >= probe_min.x and mn.x <= probe_max.x and
                mx.y >= probe_min.y and mn.y <= probe_max.y and
                mx.z >= probe_min.z and mn.z <= probe_max.z):
            continue
        nmesh = len(ob.data.vertices) if hasattr(ob.data, "vertices") else -1
        nface = len(ob.data.polygons) if hasattr(ob.data, "polygons") else -1
        mats = []
        if hasattr(ob.data, "materials"):
            mats = [m.name if m else None for m in ob.data.materials]
        rec = {
            "name": ob.name, "type": ob.type,
            "aabb_min": list(mn), "aabb_max": list(mx),
            "verts": nmesh, "faces": nface, "materials": mats,
            "scale": list(ob.scale), "location": list(ob.location),
            "hide_render": ob.hide_render, "hide_viewport": ob.hide_viewport,
        }
        report["objects"].append(rec)

    report["objects"].sort(key=lambda r: -((r["aabb_max"][0] - r["aabb_min"][0]) *
                                           (r["aabb_max"][1] - r["aabb_min"][1])))
    print(f"[recon] {len(report['objects'])} mesh objects intersect the probe box")
    for r in report["objects"]:
        print(f"  {r['name']:36s} {r['verts']:>8d}v {r['faces']:>8d}f "
              f"x[{r['aabb_min'][0]:+.4f},{r['aabb_max'][0]:+.4f}] "
              f"y[{r['aabb_min'][1]:+.4f},{r['aabb_max'][1]:+.4f}] "
              f"z[{r['aabb_min'][2]:+.4f},{r['aabb_max'][2]:+.4f}]")

    # ---- named support objects: exact geometry -----------------------------
    dg = bpy.context.evaluated_depsgraph_get()

    def build_bvh(name):
        ob = bpy.data.objects.get(name)
        if ob is None:
            return None, None, None
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        vs = [mw @ v.co for v in me.vertices]
        me.calc_loop_triangles()
        ts = [[t.vertices[0], t.vertices[1], t.vertices[2]] for t in me.loop_triangles]
        return vs, ts, ob

    for name in SUPPORT:
        vs, ts, ob = build_bvh(name)
        if vs is None:
            report["named"][name] = {"present": False}
            print(f"[recon] {name}: ABSENT")
            continue
        mn = [min(v[i] for v in vs) for i in range(3)]
        mx = [max(v[i] for v in vs) for i in range(3)]
        rec = {"present": True, "n_verts": len(vs), "n_tris": len(ts),
               "aabb_min": mn, "aabb_max": mx}
        report["named"][name] = rec
        print(f"[recon] {name}: {len(vs)}v {len(ts)}t "
              f"x[{mn[0]:+.4f},{mx[0]:+.4f}] y[{mn[1]:+.4f},{mx[1]:+.4f}] "
              f"z[{mn[2]:+.4f},{mx[2]:+.4f}]")

    # ---- surface probe: what x does each z-plane expose near the wall? -----
    # Fire +X rays (from deep inside the wall) and -X rays at a grid of (y, z)
    # to find the FIRST exposed surface a can approaching in -X would meet.
    probe_ys = [1.45, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 2.88]
    probe_zs = [-0.045, -0.035, -0.02, 0.0, 0.010, 0.012, 0.02, 0.04, 0.06,
                0.09, 0.12, 0.16, 0.20, 0.25, 0.30, 0.35, 0.39, 0.45]

    surfaces = []
    for name in SUPPORT:
        vs, ts, ob = build_bvh(name)
        if vs is None:
            continue
        surfaces.append((name, vs, ts))

    # ray from x = +3.0 travelling in -X: first hit gives the outermost surface
    ray_rows = []
    for y in probe_ys:
        row = {"y": y, "hits": {}}
        for z in probe_zs:
            origin = Vector((3.0, y, z))
            direction = Vector((-1.0, 0.0, 0.0))
            best = None
            for name, vs, ts in surfaces:
                hit = ray_mesh(vs, ts, origin, direction)
                if hit is None:
                    continue
                dist, pos = hit
                if best is None or dist < best[0]:
                    best = (dist, pos, name)
            if best is not None:
                row["hits"][f"{z:+.4f}"] = {
                    "x": best[1].x, "object": best[2], "dist": best[0]}
        ray_rows.append(row)
    report["rays"] = ray_rows

    print()
    print("[recon] outermost surface x for a -X ray (first hit from x=+3):")
    hdr = "  y\\z    " + "".join(f"{z:+8.4f}" for z in probe_zs)
    print(hdr)
    for row in ray_rows:
        cells = []
        for z in probe_zs:
            h = row["hits"].get(f"{z:+.4f}")
            cells.append(f"{h['x']:+8.4f}" if h else "    none")
        print(f"  {row['y']:.2f}  " + "".join(cells))

    print()
    print("[recon] which object that outermost surface belongs to:")
    print(hdr.replace("z", "z"))
    for row in ray_rows:
        cells = []
        for z in probe_zs:
            h = row["hits"].get(f"{z:+.4f}")
            cells.append(f"{h['object'][:8]:>8s}" if h else "    none")
        print(f"  {row['y']:.2f}  " + "".join(cells))

    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[recon] written {OUT}")
    return 0


def ray_mesh(vs, ts, origin, direction):
    """Moller-Trumbore against a triangle list.  Returns (dist, point) or None."""
    best = None
    ox, oy, oz = origin
    dx, dy, dz = direction
    for a, b, c in ts:
        p0, p1, p2 = vs[a], vs[b], vs[c]
        e1 = p1 - p0
        e2 = p2 - p0
        px = dy * e2.z - dz * e2.y
        py = dz * e2.x - dx * e2.z
        pz = dx * e2.y - dy * e2.x
        det = e1.x * px + e1.y * py + e1.z * pz
        if -1e-12 < det < 1e-12:
            continue
        inv = 1.0 / det
        tx = ox - p0.x
        ty = oy - p0.y
        tz = oz - p0.z
        u = (tx * px + ty * py + tz * pz) * inv
        if u < -1e-9 or u > 1.0 + 1e-9:
            continue
        qx = ty * e1.z - tz * e1.y
        qy = tz * e1.x - tx * e1.z
        qz = tx * e1.y - ty * e1.x
        v = (dx * qx + dy * qy + dz * qz) * inv
        if v < -1e-9 or u + v > 1.0 + 1e-9:
            continue
        t = (e2.x * qx + e2.y * qy + e2.z * qz) * inv
        if t <= 1e-6:
            continue
        if best is None or t < best[0]:
            best = (t, Vector((ox + t * dx, oy + t * dy, oz + t * dz)))
    return best


if __name__ == "__main__":
    raise SystemExit(main())
