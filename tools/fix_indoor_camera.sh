#!/usr/bin/env bash
# The smoke sample's physics is correct (fall + bounce + zero penetration,
# validation valid=True), but the RENDER shows the subject against a flat surface:
# the camera landed at x=6.0 while the room only extends to x=4.58, i.e. OUTSIDE
# the apartment looking at an exterior wall.
#
# Cause: the camera framing allows max_distance 8.0 m, which is fine for a big
# open court but far too much indoors.  Tighten the framing envelope so the lens
# stays inside the room, and also raise min_object_frame_fraction so the subject
# cannot be pushed to a speck.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()

# indoor framing envelope
t = re.sub(r"(\n\s*max_distance:\s*)[0-9.]+", r"\g<1>2.60", t)
t = re.sub(r"(\n\s*min_distance:\s*)[0-9.]+", r"\g<1>0.55", t)
t = re.sub(r"(\n\s*min_object_frame_fraction:\s*)[0-9.]+", r"\g<1>0.10", t)
t = re.sub(r"(\n\s*max_object_frame_fraction:\s*)[0-9.]+", r"\g<1>0.40", t)
t = re.sub(r"(\n\s*elevation_degrees:\s*)[0-9.]+", r"\g<1>12.0", t)
p.write_text(t)

import yaml
c = yaml.safe_load(open(p))
fr = c["camera"]["framing"]
print("  camera framing now:")
for k in ("min_distance", "max_distance", "min_object_frame_fraction",
          "max_object_frame_fraction", "elevation_degrees",
          "trajectory_frame_fraction"):
    print(f"    {k:<32} {fr.get(k)}")
print("  camera policy:", c["camera"].get("policy"))
print("  focal_length_mm:", c["camera"].get("focal_length_mm"))
PY
