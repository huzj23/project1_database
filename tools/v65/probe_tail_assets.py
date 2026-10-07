"""Print the tail objects in full, to see which assets the V6.5 tail actually uses.

The face-to-face clearance computed from `dims` did not match the spacing this project has quoted, so before any such
number is published the inputs have to be checked. The most likely cause is that the tail is NOT made of the same
asset as the trunk: `F46` in the physics manifest is `trivial` (0.0636 x 0.2046 m), while `F01` is `paper`
(0.0157 x 0.1376 m). If the tail mixes assets, then a single "median spacing" is not even a well-defined quantity and
quoting one would be misleading.
"""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
L = json.loads((ROOT / "tmp/v64_node12/layout_v65_tailwest_candidate_b.json").read_text())

print("=== which asset does each domino use? ===")
from collections import Counter
print(Counter(r["asset_key"] for r in L["objects"]))
print()
for r in L["objects"]:
    if r["id"] in ("F01", "F02", "F44", "F45", "F46", "F47", "F48"):
        print(f"{r['id']}: asset={r['asset_key']:<9} dims={[round(d, 5) for d in r['dims']]} "
              f"yaw={r.get('yaw')} pos={[round(v, 5) for v in r['settled_position'][:2]]}")

print("\n=== what does the placement report itself say about spacing? ===")
rep = ROOT / "log/V6.5_placement_report_20261007.md"
if rep.exists():
    for line in rep.read_text().splitlines():
        if any(k in line.lower() for k in ("spacing", "mm", "gap", "间距", "尾")):
            print("  " + line.strip()[:170])
