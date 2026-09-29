"""V5.5 stage 05: read back the chosen design and the recorded body start, side by side."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
D = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T040000"

d = json.loads(D.read_text(encoding="utf-8"))
c = d["chosen"]
print("=" * 80)
print("=== design.json top-level scalars ===")
for k in ("floor_z", "rim_z", "bottle_top_z", "drop_clearance_m", "r_max_m",
          "search_attempts", "passing_count", "robust_count", "design_valid"):
    print(f"  {k:24s} {d.get(k)}")
print("\n=== chosen ===")
for k in ("attempt", "orientation", "yaw_rad", "direction", "lever_arm_m", "contact_z_m",
          "radius_at_contact_m", "shoulder_overlap_m", "centre_offset_m",
          "near_face_from_axis_m", "offset_axis_overlap_m"):
    print(f"  {k:24s} {c.get(k)}")
print(f"  half_x_after_yaw_m       {c.get('half_x_after_yaw_m')}")
print(f"  half_y_after_yaw_m       {c.get('half_y_after_yaw_m')}")
print(f"  box_centre_start         {c.get('box_centre_start')}")
print(f"  box_aabb_start           {c.get('box_aabb_start')}")

print("\n=== bodies.json first rows (what the solver actually built) ===")
bj = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
for b in bj:
    print(f"  {b['instance_id']:18s} role={b['role']:8s} "
          f"pos={[round(v,6) for v in b['position_m']]} "
          f"q={[round(v,6) for v in b['quaternion_xyzw']]}")

print("\n=== provenance striker ===")
pv = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))
for k, v in pv["striker"].items():
    print(f"  {k:34s} {v}")
