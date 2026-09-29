"""Measure the source scene's floor candidates so a REAL floor collider can be added.

The production run failed `no_body_below_floor`: the trigger slides off the tray and the table and
then falls forever (origin z reached -17.86 m) because the room's own floor was classified as
backdrop -- `max_size >= 6.0 m` -- and therefore given no collider at all. The world is unbounded,
so a body that leaves the table is simply gone.

Inventing a floor plane is a patch floor and is forbidden. What is required instead is the scene's
OWN floor geometry, extracted to a bounded collision mesh, which is what 03 section 5 asks for when
it says a support surface needs extracted static mesh collision. This script measures each floor
candidate (top z, extent, triangle count, whether it spans the interaction region) so the rebuild can
name the real object rather than guess.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SRC = Path(r"D:\workspace\project1_database\models\backgrounds\candidates\italian_flat\source\flat-archiviz.blend")
OUT = Path(r"D:\workspace\project1_database\outcomes\v55\scenes\italian_flat")
OUT.mkdir(parents=True, exist_ok=True)

# The interaction region, from the layer report's reach_box, widened to cover where a sliding
# trigger can travel before it is off the table entirely.
REACH = {"x": (0.6, 2.5), "y": (6.4, 8.4), "z": (0.4, 1.2)}

bpy.ops.wm.open_mainfile(filepath=str(SRC))
scene = bpy.context.scene

print("=" * 100)
print(f"source: {SRC}")
print(f"objects: {len(bpy.data.objects)}")

KEYS = ("floor", "plane", "ground", "pavimento", "green floor", "outdoor", "basement")
cands = []
for obj in scene.objects:
    if obj.type != "MESH":
        continue
    if not any(k in obj.name.lower() for k in KEYS):
        continue
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    cands.append({
        "name": obj.name,
        "aabb_min": [round(v, 6) for v in lo],
        "aabb_max": [round(v, 6) for v in hi],
        "size_m": [round(v, 6) for v in (hi - lo)],
        "top_z": round(hi.z, 6),
        "bottom_z": round(lo.z, 6),
        "triangles": len(obj.data.polygons),
        "vertices": len(obj.data.vertices),
        "collections": [c.name for c in obj.users_collection],
        "has_modifiers": len(obj.modifiers) > 0,
    })

cands.sort(key=lambda c: -c["top_z"])
print("\n" + "=" * 100)
print("=== floor / plane candidates, by top z ===")
print(f"  {'name':34s} {'top_z':>10s} {'bot_z':>10s} {'tris':>8s}  size (x, y, z)")
for c in cands:
    print(f"  {c['name']:34s} {c['top_z']:10.4f} {c['bottom_z']:10.4f} {c['triangles']:8d}  "
          f"({c['size_m'][0]:.3f}, {c['size_m'][1]:.3f}, {c['size_m'][2]:.3f})")

# Which candidates actually span the interaction region in x/y AND sit at or below the table base?
print("\n" + "=" * 100)
print("=== which candidate can be the support the table stands on? ===")
print("    (Table.001's base is z = 0.000, so the room floor top must be about z = 0)")
spans = []
for c in cands:
    lo, hi = c["aabb_min"], c["aabb_max"]
    covers = (lo[0] <= REACH["x"][0] and hi[0] >= REACH["x"][1]
              and lo[1] <= REACH["y"][0] and hi[1] >= REACH["y"][1])
    at_zero = abs(c["top_z"]) < 0.05
    print(f"  {c['name']:34s} spans reach x/y {str(covers):5s}  top_z near 0 {str(at_zero):5s}")
    if covers:
        spans.append(c["name"])

# Also report the true minimum z of every mesh vertex near the interaction region, so the actual
# floor level is measured rather than inferred from a bound box.
print("\n" + "=" * 100)
print("=== ray cast DOWN through the interaction region to find the real floor level ===")
from mathutils import Vector as V  # noqa: E402

depsgraph = bpy.context.evaluated_depsgraph_get()
probes = [(1.5, 7.2), (1.5, 7.5), (1.9, 7.5), (2.2, 7.5), (2.4, 7.5), (1.2, 7.5), (0.8, 7.5)]
hits = []
for px, py in probes:
    origin = V((px, py, 3.0))
    hit, loc, normal, idx, obj, mat = scene.ray_cast(depsgraph, origin, V((0, 0, -1)))
    if hit:
        hits.append({"probe": [px, py], "hit": True, "z": round(loc.z, 6), "object": obj.name})
        print(f"  ({px}, {py}) -> z {loc.z:.6f}  on '{obj.name}'")
    else:
        hits.append({"probe": [px, py], "hit": False})
        print(f"  ({px}, {py}) -> NO HIT")

report = {"source": str(SRC), "reach_box": REACH, "candidates": cands,
          "candidates_spanning_reach": spans, "downward_ray_casts": hits}
p = OUT / "floor_candidates.json"
p.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {p}")
