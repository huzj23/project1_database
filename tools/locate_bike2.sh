#!/usr/bin/env bash
# ===========================================================================
# LOCATE the bicycle exactly, then probe-render several candidate cameras.
#
# IMPORTANT CORRECTION to my own earlier search: I grepped the apt_0 config for
# bike/bicycle/cycle and concluded "no bicycle in apt_0".  That was WRONG -- the
# camera scoring pass then reported `frl_apartment_bike_02` as the nearest prop.
# The name does contain "bike", so my first search must have looked at the wrong
# file set.  Re-derive it from apt_0 directly and print its world position and
# distance to the floor region, so the camera can be aimed to exclude it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -40
import json, math
import numpy as np
base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
p = base + "/configs/scenes/apt_0.scene_instance.json"
d = json.load(open(p))
insts = d.get("object_instances", [])
print(f"apt_0 instances: {len(insts)}")

hits = []
for i in insts:
    t = str(i.get("template_name", "")).split("/")[-1]
    if "bike" in t.lower() or "bicycle" in t.lower():
        tr = i.get("translation", [0,0,0])
        w = (float(tr[0]), -float(tr[2]), float(tr[1]))
        hits.append((t, w, i.get("rotation")))
print(f"bicycle instances found in apt_0: {len(hits)}")
for t, w, rot in hits:
    print(f"  {t}  world={tuple(round(v,4) for v in w)}  rot={rot}")
    # distances that matter
    floor_centre = (0.65, -2.15)
    print(f"    dist to floor region centre (0.65,-2.15): "
          f"{math.hypot(w[0]-floor_centre[0], w[1]-floor_centre[1]):.3f} m")
    # the OLD rolling camera
    old_cam = np.array([-0.643, 0.800, 0.458])
    print(f"    dist to OLD camera (-0.643,0.800,0.458): "
          f"{np.linalg.norm(np.array(w)-old_cam):.3f} m")

# also list every distinct template that contains any furniture-ish word
words = ("bike","shelf","stand","chair","table","sofa","bed","box","cabinet")
print("\ntemplates containing furniture words:")
seen = {}
for i in insts:
    t = str(i.get("template_name","")).split("/")[-1]
    if any(w in t.lower() for w in words):
        seen[t] = seen.get(t, 0) + 1
for t, n in sorted(seen.items()):
    print(f"  {t:44s} x{n}")
PY
