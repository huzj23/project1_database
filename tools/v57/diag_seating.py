"""Per-box seating diagnostic: where are the body, the proxy and the VISUAL relative to the floor?

WHY
---
The penetration gate's gap column showed the three Ouija boxes 68.9 mm above the floor while the Trivial and
Cranium boxes sat within 2 mm. That is too large to be a settling artefact, and the two possible causes have
very different consequences:

  * the body is seated correctly and the VISUAL is offset, so the picture shows a floating box;
  * the body itself is seated high, so the physics started from a drop and the recorded motion includes a
    fall that a viewer would read as the box being dropped rather than toppled.

The report distinguishes them by measuring the geometry rather than by inferring it: for every box it prints
the body origin, the proxy's world extent, the visual's world extent, and the floor height under the box.

Usage:
    blender --background --factory-startup --python tools/v57/diag_seating.py -- --blend <staged.blend>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"]).resolve()
FLOOR = ARGS.get("floor", "Floor_main")
PROXY_DIR = Path(ARGS["proxies"]).resolve() if ARGS.get("proxies") else None

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()

# The proxy collision meshes, read straight from the OBJ files the solver used, so the body dimensions are
# compared against the same files rather than against a number copied from a report.
proxy_dims = {}
if PROXY_DIR and PROXY_DIR.is_dir():
    for f in PROXY_DIR.glob("*__proxy_collision.obj"):
        aid = f.name.replace("__proxy_collision.obj", "")
        vs = []
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("v "):
                p = line.split()
                vs.append((float(p[1]), float(p[2]), float(p[3])))
        if vs:
            lo = [min(v[i] for v in vs) for i in range(3)]
            hi = [max(v[i] for v in vs) for i in range(3)]
            proxy_dims[aid] = {"size_m": [hi[i] - lo[i] for i in range(3)],
                               "min_m": lo, "max_m": hi, "n_verts": len(vs)}

print("=" * 112)
print(f"seating diagnostic | {BLEND.name}")
print("=" * 112)
if proxy_dims:
    print("  collision proxy OBJ dimensions (the body the solver simulated):")
    for aid, d in sorted(proxy_dims.items()):
        print(f"    {aid:46s} size {[round(v, 5) for v in d['size_m']]}")

rows = []
for o in sorted(bpy.data.objects, key=lambda x: x.name):
    if o.type != "MESH" or not (o.name.startswith("box") or o.name.startswith("trigger_")):
        continue
    if o.name.startswith("gate_proxy_"):
        continue
    mw = o.matrix_world
    ws = [mw @ v.co for v in o.data.vertices]
    vlo = Vector((min(p[i] for p in ws) for i in range(3)))
    vhi = Vector((max(p[i] for p in ws) for i in range(3)))
    origin = mw.translation
    # The floor directly under the object's own origin.
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (origin.x, origin.y, origin.z + 1.0),
                                                 (0, 0, -1), distance=4.0)
    fz = loc.z if ok else None
    rows.append({
        "object": o.name,
        "body_origin_z": round(origin.z, 6),
        "visual_min_z": round(vlo.z, 6),
        "visual_max_z": round(vhi.z, 6),
        "visual_height_m": round(vhi.z - vlo.z, 6),
        "visual_footprint_m": [round(vhi.x - vlo.x, 6), round(vhi.y - vlo.y, 6)],
        "floor_z": (round(fz, 6) if fz is not None else None),
        "visual_gap_to_floor_m": (round(vlo.z - fz, 6) if fz is not None else None),
        "floor_object": obj.name if ok else None,
    })

print("")
hdr = (f"  {'object':24s} {'origin z':>10s} {'visual z-range':>20s} {'height':>9s} "
       f"{'floor z':>9s} {'gap':>9s}  footprint")
print(hdr)
for r in rows:
    gap = r["visual_gap_to_floor_m"]
    flag = ""
    if gap is not None and abs(gap) > 0.005:
        flag = "  <== FLOATING" if gap > 0 else "  <== SUNK"
    print(f"  {r['object']:24s} {r['body_origin_z']:10.5f} "
          f"[{r['visual_min_z']:8.5f},{r['visual_max_z']:8.5f}] {r['visual_height_m']:9.5f} "
          f"{(r['floor_z'] if r['floor_z'] is not None else float('nan')):9.5f} "
          f"{(gap if gap is not None else float('nan')):9.5f}  "
          f"{[round(v, 3) for v in r['visual_footprint_m']]}{flag}")

# The visual height should equal the proxy's HEIGHT axis, whichever axis the import mapped it to. Reporting
# both makes a mapping error obvious instead of leaving it to be discovered in the footage.
print("")
print("  visual height vs collision proxy extents (a mismatch means the import mapped a different axis up):")
for r in rows:
    aid = r["object"].split("_", 1)[1]
    # Map the short name back to the full asset id.
    full = next((k for k in proxy_dims if aid.lower() in k.lower()), None)
    if not full:
        continue
    d = proxy_dims[full]
    srt = sorted(d["size_m"])
    vh = r["visual_height_m"]
    nearest = min(srt, key=lambda s: abs(s - vh))
    verdict = "OK" if abs(nearest - vh) < 0.02 else "MISMATCH"
    print(f"    {r['object']:24s} visual height {vh:.5f}  proxy extents "
          f"{[round(v, 5) for v in d['size_m']]}  nearest {nearest:.5f}  {verdict}")

out = Path(ARGS.get("out", "")).resolve() if ARGS.get("out") else None
if out:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"blend": str(BLEND), "proxy_dims": proxy_dims, "rows": rows},
                              indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
