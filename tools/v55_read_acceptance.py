"""Read stage 03's final proxy acceptance verdict for the props and the glasses."""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
S = ROOT / "outcomes/v55/scenes/italian_flat"
d = json.loads((S / "proxy_acceptance_final.json").read_text(encoding="utf-8"))

print("=" * 96)
print(f"top-level keys: {sorted(d.keys())}")
for k in ("overall_pass", "pass", "verdict", "all_pass", "summary", "tolerance_m",
          "acceptance", "criteria"):
    if k in d:
        print(f"  {k}: {json.dumps(d[k])[:600]}")

print("\n=== props ===")
for name, e in d.get("props", {}).items():
    print(f"\n  {name}:")
    for k in sorted(e):
        v = e[k]
        if isinstance(v, dict):
            print(f"    {k}: {{{', '.join(f'{kk}={vv}' for kk, vv in list(v.items())[:8])}}}")
        elif isinstance(v, list):
            print(f"    {k}: [{', '.join(str(x) for x in v[:6])}]")
        else:
            print(f"    {k}: {v}")

print("\n" + "=" * 96)
print("=== stage 03 proxy_verification.json (per-prop verdicts) ===")
v = json.loads((S / "proxy_verification.json").read_text(encoding="utf-8"))
print(f"top-level keys: {sorted(v.keys())}")
for name in ("bottle_assembly", "glass_a", "glass_b"):
    if name in v:
        print(f"\n  {name}:")
        print(json.dumps(v[name], indent=2)[:1800])
