"""Read the stage-03 proxy decision record and print its scalar fields."""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
d = json.loads((ROOT / "outcomes/v55/scenes/italian_flat/props/proxy_decision.json")
               .read_text(encoding="utf-8"))
for name in ("bottle_assembly", "glass_a", "glass_b"):
    e = d[name]
    print(f"\n=== {name} ===")
    for k in sorted(e):
        v = e[k]
        if isinstance(v, (list, dict)):
            print(f"  {k}: <{type(v).__name__} len {len(v)}>")
        else:
            print(f"  {k}: {v}")
    print(f"  all keys: {sorted(e.keys())}")
