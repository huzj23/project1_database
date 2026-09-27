#!/usr/bin/env bash
# Understand WHY the camera lands where it does.
#
# The trajectory is only 0.46 m across, so a 0.62 frame fraction implies a ~1 m
# stand-off -- yet the solver asked for ~4.5 m.  Read back everything the camera
# recorded (its own report is stored in the sample metadata) instead of guessing.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"

"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import json, os, sys, math
D = sys.argv[1]
md = json.load(open(os.path.join(D, "metadata.json")))
print("=== metadata top-level keys ===")
print(" ", list(md))

def show(k):
    if k in md:
        print(f"\n=== {k} ===")
        print(json.dumps(md[k], indent=2)[:1400])

for k in ("camera", "camera_framing", "framing", "sample", "scenario_sample"):
    show(k)

# reconstruct the geometry
cam = md.get("camera") or {}
pos = cam.get("position")
if pos:
    print(f"\ncamera position: {[round(v,3) for v in pos]}")
    # the object's trajectory centre
    traj = json.load(open(os.path.join(D, "trajectory.json")))
    states = traj if isinstance(traj, list) else traj.get("states", [])
    import numpy as np
    p = np.array([s["position"] for s in states])
    c = (p.max(axis=0) + p.min(axis=0)) / 2
    print(f"trajectory centre: {[round(v,3) for v in c]}")
    print(f"trajectory span  : {[round(v,3) for v in (p.max(axis=0)-p.min(axis=0))]}")
    d = math.dist(pos, c)
    print(f"stand-off        : {d:.3f} m")
    print(f"room x[-2.68,4.58] y[-8.16,4.89]; camera indoors: "
          f"{-2.68 <= pos[0] <= 4.58 and -8.16 <= pos[1] <= 4.89}")
PY
