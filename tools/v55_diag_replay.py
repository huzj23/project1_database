"""Diagnose why every keyframe came out at the same place.

The replay recorded 62 keys per body yet all 62 object positions were identical. That means the
transform being applied was constant, which can only happen if the relative transform computed from
the trajectory is the identity at every frame -- i.e. if the trajectory rows being read are all the
same, or if the wrong field is being used. This script prints the actual per-frame values so the
cause is identified rather than guessed.
"""

import json
from pathlib import Path

RUN = Path(r"D:\workspace\project1_database\outcomes\v55\italian_flat\box_hits_bottle"
           r"\20260929T110000")
tr = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))
print(f"quaternion_convention: {tr['quaternion_convention']}")
print(f"video_fps: {tr['video_fps']}")

for name, rows in tr["bodies"].items():
    print(f"\n=== {name}: {len(rows)} rows ===")
    print(f"  keys of a row: {sorted(rows[0].keys())}")
    print(f"  {'frame':>6s} {'blender':>8s} {'t_s':>8s}  position")
    for r in rows[:4]:
        print(f"  {r['frame']:6d} {r['blender_frame']:8d} {r['time_s']:8.4f}  "
              f"{[round(v,6) for v in r['position_m']]}")
    print("  ...")
    for r in rows[-3:]:
        print(f"  {r['frame']:6d} {r['blender_frame']:8d} {r['time_s']:8.4f}  "
              f"{[round(v,6) for v in r['position_m']]}")
    ps = [r["position_m"] for r in rows]
    uniq = len({tuple(round(v, 9) for v in p) for p in ps})
    print(f"  distinct positions: {uniq}/{len(rows)}")
    # The travel, which is what the renderer must reproduce.
    import math
    p0 = ps[0]
    far = max(math.dist(p, p0) for p in ps)
    print(f"  max travel from frame 0: {far*1000:.4f} mm")
    zs = [p[2] for p in ps]
    print(f"  z range {min(zs):.6f} .. {max(zs):.6f}")
