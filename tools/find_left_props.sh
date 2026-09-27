#!/usr/bin/env bash
# ===========================================================================
# Identify the "bicycle on the left" the user disliked.
#
# apt_0 contains NO bicycle template, so it must be a prop that merely LOOKS like
# one in that framing.  Rather than guess, project every prop's world position into
# the OLD camera (recorded in datasets/rolling/seed-001001/x1/metadata.json) and
# report what was actually in frame, which side, and how close.
#
# Screen-x sign: the camera's right vector; negative = LEFT of frame.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -45
import json, math, glob
import numpy as np

meta = json.load(open("datasets/rolling/seed-001001/x1/metadata.json"))
R = meta["render"]
cam = np.array(R["camera_position"], dtype=float)
focal = float(R["camera_focal_length_mm"])
look = np.array(meta["camera"]["look_at"] if "look_at" in meta.get("camera", {}) else (-0.528, -0.956, 0.084), dtype=float)
print(f"OLD camera pos={np.round(cam,3).tolist()} look={np.round(look,3).tolist()} focal={focal}")

fwd = look - cam; fwd /= np.linalg.norm(fwd)
right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
up = np.cross(right, fwd)
fov_h = 2*math.atan(36.0/(2*focal))
fov_v = 2*math.atan((36.0*(1080/1920))/(2*focal))

base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
d = json.load(open(base + "/configs/scenes/apt_0.scene_instance.json"))

rows = []
for i in d.get("object_instances", []):
    t = str(i.get("template_name","")).split("/")[-1]
    tr = i.get("translation", [0,0,0])
    w = np.array([float(tr[0]), -float(tr[2]), float(tr[1])])
    v = w - cam
    z = float(v @ fwd)
    if z <= 0.05:
        continue
    nx = math.atan2(float(v @ right), z)/(fov_h/2)
    ny = math.atan2(float(v @ up), z)/(fov_v/2)
    if abs(nx) > 1.15 or abs(ny) > 1.15:
        continue
    rows.append((nx, ny, z, t, w))

rows.sort()
print(f"\nprops inside (or just outside) the OLD frame: {len(rows)}")
print(f"{'norm_x':>7} {'norm_y':>7} {'depth':>7}  {'side':>5}  template")
for nx, ny, z, t, w in rows:
    side = "LEFT" if nx < 0 else "right"
    print(f"{nx:+7.3f} {ny:+7.3f} {z:7.3f}  {side:>5}  {t}  at {np.round(w,2).tolist()}")
PY
