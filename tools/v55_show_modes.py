"""Print the layer report's static collision table with the recorded collision modes."""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
d = json.loads((ROOT / "outcomes/v55/scenes/italian_flat/layer_report.json").read_text(encoding="utf-8"))
print("=== static collision objects with recorded collision mode ===")
print(f"  {'name':38s} {'tris':>7s} {'top_z':>9s}  mode")
for name, v in d["static_collision"].items():
    print(f"  {name:38s} {v['triangles']:7d} {v['aabb_max'][2]:9.4f}  "
          f"{v.get('collision_mode', '(not recorded)')}")
    if v.get("role"):
        print(f"      role: {v['role']}")
print(f"\n  total: {len(d['static_collision'])} objects")
print(f"  soft background: {[s['name'] for s in d['soft_background']]}")
print(f"  lights: {len(d['lights_preserved'])}  world: {d['world_preserved']}")
