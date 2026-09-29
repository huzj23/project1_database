"""a_probe_view.py -- V5.6: what does the Hidden Alley camera actually see?

Because we cannot look at the reference PNG, we reconstruct a low-resolution
"object id map" of the frame by ray casting from the active camera through a
grid of pixels, and we project every wooden_boards* component's AABB corners
into camera-normalised device coordinates.

Also reports the camera's true world matrix / forward vector (rotation_euler
alone is not trustworthy if the object is parented or uses quaternions) and
casts a ray at each board component's centroid.

Read-only. Writes JSON + a plain-text ASCII map.

Run:
  & '<blender.exe>' --background --factory-startup --python a_probe_view.py -- \
        --blend <scene.blend> --out <report.json> --map <map.txt> \
        [--cols 40] [--rows 20] [--scene Scene]
"""

import argparse
import json
import math
import os
import sys

import numpy as np

import bpy
from bpy_extras.object_utils import world_to_camera_view


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--map", default="")
    ap.add_argument("--names", default="wooden_boards")
    ap.add_argument("--cols", type=int, default=44)
    ap.add_argument("--rows", type=int, default=22)
    A = ap.parse_args(args)

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    cam = sc.camera
    out = {"blend": A.blend, "scene": sc.name, "camera": cam.name}

    mw = np.array(cam.matrix_world, dtype=np.float64)
    fwd = -mw[:3, 2]
    up = mw[:3, 1]
    right = mw[:3, 0]
    out["camera_world_matrix"] = [[round(float(v), 6) for v in row] for row in mw]
    out["camera_location_world"] = [round(float(v), 6) for v in mw[:3, 3]]
    out["camera_forward_world"] = [round(float(v), 6) for v in fwd]
    out["camera_up_world"] = [round(float(v), 6) for v in up]
    out["camera_right_world"] = [round(float(v), 6) for v in right]
    out["camera_rotation_mode"] = cam.rotation_mode
    out["camera_rotation_euler"] = [round(float(v), 8) for v in cam.rotation_euler]
    out["camera_rotation_quaternion"] = [round(float(v), 8) for v in cam.rotation_quaternion]
    out["camera_parent"] = cam.parent.name if cam.parent else None
    out["camera_scale"] = [round(float(v), 8) for v in cam.scale]
    out["camera_lens_mm"] = cam.data.lens
    out["camera_sensor_width_mm"] = cam.data.sensor_width
    out["camera_clip"] = [cam.data.clip_start, cam.data.clip_end]
    out["render_aspect"] = sc.render.resolution_x / sc.render.resolution_y
    out["render_resolution"] = [sc.render.resolution_x, sc.render.resolution_y]
    out["resolution_percentage"] = sc.render.resolution_percentage

    dg = bpy.context.evaluated_depsgraph_get()

    # ---------------- board component projection ----------------
    boards = []
    for ob in sorted([o for o in bpy.data.objects if o.name.startswith(A.names)],
                     key=lambda o: o.name):
        me = ob.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        obmw = np.array(ob.matrix_world, dtype=np.float64)
        wco = co @ obmw[:3, :3].T + obmw[:3, 3]

        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for e in me.edges:
            a, b = find(e.vertices[0]), find(e.vertices[1])
            if a != b:
                parent[a] = b
        comp = [find(i) for i in range(n)]
        roots = sorted(set(comp))
        recs = []
        for ci, r in enumerate(roots):
            ids = [i for i in range(n) if comp[i] == r]
            c = wco[ids]
            mn, mx = c.min(axis=0), c.max(axis=0)
            cen = (mn + mx) / 2.0
            # project the 8 bbox corners
            ndc = []
            for sx in (mn[0], mx[0]):
                for sy in (mn[1], mx[1]):
                    for sz in (mn[2], mx[2]):
                        p = world_to_camera_view(sc, cam, __import__("mathutils").Vector((float(sx), float(sy), float(sz))))
                        ndc.append([round(p.x, 4), round(p.y, 4), round(p.z, 4)])
            xs = [p[0] for p in ndc]
            ys = [p[1] for p in ndc]
            zs = [p[2] for p in ndc]
            in_frame = (max(xs) > 0 and min(xs) < 1 and max(ys) > 0 and min(ys) < 1 and min(zs) > 0)
            # ray from camera toward centroid
            d = cen - mw[:3, 3]
            dist = float(np.linalg.norm(d))
            hit_name, hit_d, hit_loc, hit_nrm = None, None, None, None
            if dist > 0:
                res = sc.ray_cast(dg, __import__("mathutils").Vector([float(v) for v in mw[:3, 3]]),
                                  __import__("mathutils").Vector([float(v / dist) for v in d]))
                if res[0]:
                    hit_name = res[4].name if hasattr(res[4], "name") else str(res[4])
                    hit_loc = [round(float(v), 5) for v in res[1]]
                    hit_d = round(float((np.array(res[1]) - mw[:3, 3]) @ fwd), 5)
                    hit_nrm = [round(float(v), 5) for v in res[2]]
            recs.append({
                "component_index": ci,
                "centroid": [round(float(v), 5) for v in cen],
                "bbox_min": [round(float(v), 5) for v in mn],
                "bbox_max": [round(float(v), 5) for v in mx],
                "ndc_bbox": [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)],
                "ndc_depth_min": round(min(zs), 4),
                "in_frame": bool(in_frame),
                "dist_to_centroid_m": round(dist, 5),
                "ray_hit_object": hit_name,
                "ray_hit_depth_m": hit_d,
                "ray_hit_location": hit_loc,
                "ray_hit_normal": hit_nrm,
            })
        boards.append({"object": ob.name, "components": recs})
    out["board_components"] = boards

    # frame fraction occupied by each component (clipped NDC area)
    total = 0.0
    per_comp = []
    for b in boards:
        for c in b["components"]:
            x0, y0, x1, y1 = c["ndc_bbox"]
            cx0, cy0 = max(0.0, x0), max(0.0, y0)
            cx1, cy1 = min(1.0, x1), min(1.0, y1)
            a = max(0.0, cx1 - cx0) * max(0.0, cy1 - cy0)
            total += a
            per_comp.append({"object": b["object"], "component_index": c["component_index"],
                             "clipped_ndc_area": round(a, 5)})
    out["clipped_ndc_area_sum"] = round(total, 5)
    out["clipped_ndc_area_per_component"] = per_comp

    # ---------------- coarse object-id map ----------------
    if A.map:
        cols, rows = A.cols, A.rows
        grid = []
        counts = {}
        for j in range(rows):
            row = []
            for i in range(cols):
                px = (i + 0.5) / cols
                py = 1.0 - (j + 0.5) / rows
                o = cam.data.view_frame(scene=sc)
                # view_frame returns 4 corners at the clip_start plane in camera space
                # corners order: top-right, bottom-right, bottom-left, top-left
                tr, br, bl, tl = [np.array(v, dtype=np.float64) for v in o]
                pos = (tl + (tr - tl) * px) + ((bl + (br - bl) * px) - (tl + (tr - tl) * px)) * py
                origin = mw[:3, 3]
                direction = mw[:3, :3] @ pos
                direction = direction / np.linalg.norm(direction)
                res = sc.ray_cast(dg, __import__("mathutils").Vector([float(v) for v in origin]),
                                  __import__("mathutils").Vector([float(v) for v in direction]))
                nm = res[4].name if res[0] and hasattr(res[4], "name") else ("MISS" if not res[0] else "?")
                row.append(nm)
                counts[nm] = counts.get(nm, 0) + 1
            grid.append(row)
        # write ascii map with a legend
        legend = {}
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        ordered = sorted(counts.items(), key=lambda kv: -kv[1])
        lines = []
        for idx, (nm, ct) in enumerate(ordered):
            legend[chars[idx] if idx < len(chars) else "?"] = nm
        for row in grid:
            lines.append("".join(
                [k for k, v in legend.items() if v == nm][0] if nm in legend.values() else "." for nm in row))
        txt = ["ROWS=%d COLS=%d  (origin top-left; each char = %.4f x %.4f of the frame)" %
               (rows, cols, 1.0 / cols, 1.0 / rows), ""]
        txt += lines
        txt += ["", "LEGEND:"]
        for k, v in legend.items():
            txt.append("  %s = %s   (%d cells, %.2f%%)" % (k, v, counts[v], 100.0 * counts[v] / (rows * cols)))
        os.makedirs(os.path.dirname(A.map), exist_ok=True)
        with open(A.map, "w", encoding="utf-8") as fh:
            fh.write("\n".join(txt))
        out["object_id_map_legend"] = {k: v for k, v in legend.items()}
        out["object_id_map_counts"] = counts
        print("[a_probe_view] wrote", A.map)

    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("[a_probe_view] wrote", A.out)
    print("[a_probe_view] camera loc", out["camera_location_world"],
          "fwd", out["camera_forward_world"], "parent", out["camera_parent"],
          "mode", out["camera_rotation_mode"])


main()
