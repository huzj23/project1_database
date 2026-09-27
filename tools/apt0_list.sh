#!/usr/bin/env bash
# ===========================================================================
# What is actually in the apt_0 layout we render, and where?
# The bicycle template (frl_apartment_bike_02) appears ONLY in v3_sc3_* configs,
# so the "bicycle on the left" the user saw may be a different prop.  List every
# instance with its world translation (mapped x, -z, y like the stage import) so
# I can see what sits near the trajectory and on which side.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -60
import json, math
base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
d = json.load(open(base + "/configs/scenes/apt_0.scene_instance.json"))
insts = d.get("object_instances", [])
print(f"apt_0 instances: {len(insts)}")
print(f"{'template':38s} {'world (x,y,z) after swap':34s} {'dist to floor centre':>20s}")
# floor region centre from maps.yaml
FC = (0.65, -2.15)
rows = []
for i in insts:
    t = str(i.get("template_name","")).split("/")[-1]
    tr = i.get("translation", [0,0,0])
    # stage import maps (x, y, z) -> (x, -z, y)
    wx, wy, wz = float(tr[0]), -float(tr[2]), float(tr[1])
    dist = math.hypot(wx-FC[0], wy-FC[1])
    rows.append((dist, t, (wx,wy,wz)))
rows.sort()
for dist, t, w in rows[:35]:
    print(f"  {t:38s} ({w[0]:7.3f},{w[1]:7.3f},{w[2]:6.3f})   {dist:8.3f} m")
PY
