"""b2_ground_inventory.py -- list every mesh object whose name looks like GROUND, with its world AABB.

The full-scene ground survey was dominated by `BG_floor`, an ~810-unit backdrop plane that trivially
satisfies "one object, zero deviation" while being nowhere near the alley set dressing. This probe
lists the candidates with their extents and vertex counts so the survey area can be restricted to the
actual alley floor before any ray budget is spent on it.

Read-only. Writes one JSON.

  & blender.exe --background --factory-startup --python b2_ground_inventory.py -- \
        --blend <scene.blend> --out <report.json>
"""

import argparse
import json
import math
import sys
import time

import numpy as np

import bpy

HINTS = ("floor", "ground", "stones", "gravel", "concrete", "asphalt", "road", "paving",
         "pavement", "dirt", "terrain", "kerb", "curb", "base_", "manhole", "debris", "moss",
         "rock", "brick", "plank", "wall")


def rnd(x, nd=6):
    if x is None:
        return None
    if isinstance(x, (list, tuple, np.ndarray)):
        return [rnd(v, nd) for v in x]
    if isinstance(x, bool):
        return x
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--all", action="store_true", help="also list non-name-matched objects")
    A = ap.parse_args(args)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    rows = []
    n_objs = 0
    for o in sc.objects:
        if o.type != "MESH":
            continue
        n_objs += 1
        low = o.name.lower()
        if not A.all and not any(h in low for h in HINTS):
            continue
        me = o.data
        nv = len(me.vertices)
        if nv == 0:
            continue
        mw = np.array(o.matrix_world, dtype=np.float64)
        co = np.empty((nv, 3), dtype=np.float64)
        me.vertices.foreach_get("co", co.ravel())
        co4 = np.concatenate([co, np.ones((nv, 1))], axis=1)
        w = (mw @ co4.T).T[:, :3]
        amn, amx = w.min(axis=0), w.max(axis=0)
        dims = amx - amn
        rows.append({
            "name": o.name, "verts": nv, "faces": len(me.polygons),
            "world_min": rnd(amn), "world_max": rnd(amx), "dims": rnd(dims),
            "max_dim": rnd(float(dims.max()), 4),
            "z_span": rnd([float(amn[2]), float(amx[2])], 4),
            "materials": [m.name if m else None for m in me.materials],
            "object_scale": rnd([float(v) for v in o.scale], 6),
        })
    rows.sort(key=lambda r: -r["max_dim"])
    out = {"blend": A.blend, "mesh_objects": n_objs, "listed": len(rows),
           "matched": not A.all, "hints": list(HINTS), "objects": rows,
           "runtime_s": rnd(time.time() - t0, 2)}
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"[b2_inv] {len(rows)} of {n_objs} mesh objects listed -> {A.out}")
    for r in rows[:40]:
        print(f"[b2_inv]   {r['name'][:46]:46s} max_dim={r['max_dim']:9.3f} "
              f"min={[round(v,2) for v in r['world_min']]} max={[round(v,2) for v in r['world_max']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
