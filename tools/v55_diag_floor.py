"""Diagnose the failing `no_body_below_floor` check: find which body dips and by how much."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle" / (
    sys.argv[1] if len(sys.argv) > 1 else "20260929T090000")
tr = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
bodies = {b["instance_id"]: b for b in
          json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))}

print("=" * 100)
print("=== per-body minimum origin z over the run (the check tests z > -1.0 m) ===")
for name, rows in tr.items():
    zs = [r["position_m"][2] for r in rows]
    i = int(np.argmin(zs))
    print(f"  {name:18s} min z {min(zs):+12.6f} m at frame {i} (t={rows[i]['time_s']:.4f})  "
          f"max z {max(zs):+10.6f}  first {zs[0]:+.6f}  last {zs[-1]:+.6f}")
    if min(zs) <= -1.0:
        print(f"      !! BELOW -1.0 m")

# The check uses the body's ORIGIN, which for these composite meshes sits at the proxy's AABB
# centre in x/y and at the AABB MINIMUM in z (that is how v55_final_05.py places them). A body whose
# origin is near the floor at rest is fine; one that goes below -1 m has left the world.
print("\n=== how the origins were placed (from bodies.json) ===")
for name, b in bodies.items():
    print(f"  {name:18s} pos {np.round(b['position_m'],6)}  role={b['role']}")

print("\n=== substep minimum z (finer than the video frames) ===")
sub_min = {}
with (RUN / "motion_substeps.jsonl").open("r", encoding="utf-8") as h:
    for line in h:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        z = r["position_m"][2]
        k = r["instance_id"]
        if k not in sub_min or z < sub_min[k][0]:
            sub_min[k] = (z, r["step"], r["time_s"])
for name, (z, st, t) in sorted(sub_min.items()):
    print(f"  {name:18s} min z {z:+12.6f} m at substep {st} (t={t:.4f})")

print("\n" + "=" * 100)
print("INTERPRETATION")
print("  The check as written in write_evidence tests the body ORIGIN against z > -1.0 m. For these")
print("  composite meshes the origin is the proxy's AABB minimum in z, so a body RESTING on the tray")
print("  has an origin around z = 0.51 m, and a body that has not moved cannot trip the check.")
worst = min(min(r["position_m"][2] for r in rows) for rows in tr.values())
print(f"  worst origin z across every body and frame: {worst:+.6f} m")
print(f"  threshold: -1.0 m  ->  {'PASSES' if worst > -1.0 else 'FAILS'}")
