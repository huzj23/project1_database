"""V6.5 -- check that FINAL_REPORT.md's pixel-coverage claim is backed by a key that EXISTS.

`write_final_report.py` renders the coverage line as

    len(cam.get("below_min_px_small") or [])

which prints **0 frames** both when the check genuinely found none AND when the key is absent from
`camera_path.json`. The camera designer printed "subject's LARGEST dimension below 50.0 px: 5 frames" and "UPRIGHT
HEIGHT below 50.0 px: 8 frames" for this very path, so a report line saying 0 is exactly the kind of silently-wrong
reassurance this project has been burned by a dozen times.

This prints the keys the report depends on and, when a key is missing, says so plainly instead of falling back to a
value that reads as a pass.
"""

import json
import sys

OUT = "/data/raw/huzijian/project1_database/outcomes/v65/radio_scurve_domino/v65_20261007_final"
cam = json.load(open(OUT + "/camera_path.json"))

print("camera_path.json keys the final report reads:")
for k in ("min_subject_px", "below_min_px_small", "below_min_px_upright",
          "blocked_frames", "frames", "fps", "res", "fov_deg"):
    if k in cam:
        v = cam[k]
        n = len(v) if isinstance(v, list) else v
        print(f"  {k} = {n}")
    else:
        print(f"  {k} = ** ABSENT **  <-- a report line reading this will print a misleading zero/false")

print("\nall top-level keys:")
for k in sorted(cam):
    v = cam[k]
    if isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")
    elif isinstance(v, dict):
        print(f"  {k}: dict{list(v)[:6]}")
    else:
        print(f"  {k}: {v}")
