"""Look for the room floor in the source scene and in the layer report's exclusions."""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
S = ROOT / "outcomes/v55/scenes/italian_flat"
layer = json.loads((S / "layer_report.json").read_text(encoding="utf-8"))

print("=" * 96)
print("=== excluded_backdrop (not in the collision layer) ===")
for e in layer.get("excluded_backdrop") or []:
    if isinstance(e, dict):
        print(f"  {e.get('name'):38s} size {[round(v,4) for v in (e.get('size_m') or [])]} "
              f"aabb_min {[round(v,4) for v in (e.get('aabb_min') or [])]}")
    else:
        print(f"  {e}")

print("\n=== static_collision (IS in the collision layer) ===")
for name, v in (layer.get("static_collision") or {}).items():
    print(f"  {name:38s} size {[round(x,4) for x in v['size_m']]} "
          f"aabb_min {[round(x,4) for x in v['aabb_min']]} "
          f"aabb_max {[round(x,4) for x in v['aabb_max']]} tris {v['triangles']}")

print("\n=== reach_box ===")
print(json.dumps(layer.get("reach_box"), indent=2))

print("\n" + "=" * 96)
print("=== all objects in the layer report whose name suggests a floor/plane/room ===")
KEYS = ("floor", "pavimento", "ground", "plane", "room", "stanza", "wall", "parete")
for key in ("excluded_backdrop", "static_collision", "static_collision_per_object",
            "soft_background", "layers", "dynamic_props"):
    v = layer.get(key)
    if isinstance(v, dict):
        items = list(v.keys())
    elif isinstance(v, list):
        items = [e.get("name") if isinstance(e, dict) else str(e) for e in v]
    else:
        continue
    for n in items:
        if n and any(t in str(n).lower() for t in KEYS):
            print(f"  [{key}] {n}")
