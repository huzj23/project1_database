"""Pull the three named candidates out of the earlier stage08 shape metric, for comparison.

This is a READ-ONLY convenience: the re-verification must not silently inherit the earlier
conclusion, but it does need to quote it accurately. It prints the earlier screening row for
each of the three named assets so the new physical result can be set beside it.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"D:\workspace\project1_database")
STAGE08 = ROOT / "outcomes/v55/stage08"

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]

KEYS = [
    "asset_id", "source", "has_collision_proxy",
    "standing_h_m", "thickness_m", "width_m", "h_over_t", "w_over_t",
    "base_coverage", "top_coverage", "strike_coverage", "tipping_angle_deg",
    "boxiness", "closedness", "dims_in_own_frame_m",
    "urdf_mass_kg", "urdf_ixx", "box_formula_ixx", "ixx_ratio_urdf_over_box",
    "triangles", "vertices",
    "boxiness_ok", "base_ok", "strike_ok", "tipping_ok", "ratio_ok", "usable_as_domino",
]

for fname in ("box_shape_final.json", "box_shape_check.json",
              "box_shape_diagnosis.json", "box_candidates.json"):
    p = STAGE08 / fname
    if not p.is_file():
        print(f"=== {fname}: MISSING ===")
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = {a.get("asset_id"): a for a in data.get("assets", [])}
    print("=" * 100)
    print(f"=== {fname} ===")
    print(f"  note: {str(data.get('note'))[:160]}")
    if "thresholds" in data:
        print(f"  thresholds: {json.dumps(data['thresholds'])}")
    if "usable_count" in data:
        print(f"  usable_count: {data['usable_count']} of {data.get('measured')}")
        print(f"  usable list : {data.get('usable')}")
    for aid in ASSETS:
        row = rows.get(aid)
        print(f"\n  --- {aid} ---")
        if row is None:
            print("    NOT PRESENT in this file")
            continue
        for k in KEYS:
            if k in row:
                print(f"    {k:26s} {row[k]}")
