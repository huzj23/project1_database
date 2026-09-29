"""Print the layer report's top-level keys and the light/world/no-deletion fields."""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
p = ROOT / "outcomes/v55/scenes/italian_flat/layer_report.json"
d = json.loads(p.read_text(encoding="utf-8"))
print("=== top-level keys ===")
for k in sorted(d):
    v = d[k]
    if isinstance(v, (list, dict)):
        print(f"  {k}: <{type(v).__name__} len {len(v)}>")
    else:
        print(f"  {k}: {v}")

print("\n=== light / world / deletion fields ===")
for k in sorted(d):
    kl = k.lower()
    if any(t in kl for t in ("light", "world", "delet", "lamp", "no_deletion", "remove")):
        print(f"  {k}: {json.dumps(d[k])[:900]}")

print("\n=== all keys containing 'soft' ===")
for k in sorted(d):
    if "soft" in k.lower():
        print(f"  {k}: {json.dumps(d[k])[:400]}")

print("\n=== static_collision ===")
print(json.dumps(d.get("static_collision"), indent=2)[:600])
print("\n=== static_collision_per_object keys ===")
for k, v in (d.get("static_collision_per_object") or {}).items():
    print(f"  {k}: tris={v.get('triangles')} uri={str(v.get('uri'))[-46:]}")
