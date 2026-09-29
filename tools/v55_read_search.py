"""V5.5 stage 05: read back the contact pairs and impulse from the last strike search."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"

s = json.loads((OUT / "strike_search.json").read_text(encoding="utf-8"))
print("=" * 96)
print(f"target {s['target']}  striker {s['striker']['instance_id']} "
      f"({s['striker']['asset_id']}, {s['striker']['mass_kg']} kg)")
print("=" * 96)
for r in s["attempts"]:
    print(f"\n#{r['attempt']} near_face={r['near_face_m']*1000:.2f} mm drop={r['drop_m']:.2f} m")
    print(f"  translation {r['target_translation_mm']:.3f} mm  tilt {r['target_tilt_deg']:.2f} deg")
    print(f"  first contact z {r['first_contact_point_m'][2] if r['first_contact_point_m'] else None}")
    print(f"  contact pairs:")
    for k, v in sorted(r["contact_pair_counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:52s} {v:6d}")

impl = OUT / "impulse_proxy.json"
if impl.is_file():
    print("\n" + "=" * 96)
    print("=== impulse_proxy.json ===")
    d = json.loads(impl.read_text(encoding="utf-8"))
    print(json.dumps(d, indent=2)[:2000])
