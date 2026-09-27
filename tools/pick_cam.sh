#!/usr/bin/env bash
# ===========================================================================
# (a) turntable render progress
# (b) CHOOSE the new rolling camera ANALYTICALLY, using the prop list I already
#     have, instead of guessing and paying 20 min per render.
#
# The user's complaint: "我不喜欢现在离的这么近的左侧自行车" -- something close on the
# LEFT.  apt_0 has no bicycle, so it is a prop that reads as one; what matters is
# that near-field clutter sits on the left of the old framing.  The old camera was
# at (-0.643, 0.800, 0.458) looking at (-0.528,-0.956,0.084), focal 40.
#
# For each candidate azimuth around the trajectory midpoint, score:
#   * object size on screen (want the can clearly visible)
#   * distance to the nearest prop in frame (want no close clutter)
#   * how much of the close clutter is on the LEFT
# and pick the best.  Only then render one probe frame to confirm.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== turntable progress ==="
cat "$WS/tmp/t3_final_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
pgrep -af generate.py | head -1 | sed 's/^/  /'

echo
echo "=== rolling trajectory + camera candidate scoring ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -45
import sys, json, math, glob
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get("gso_whey_protein_vanilla")
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
p = np.array([s.position for s in res.trajectory])
mid = (p.min(axis=0) + p.max(axis=0)) / 2.0
d = p[-1,:2] - p[0,:2]; d = d/np.linalg.norm(d)
print(f"  trajectory {np.round(p[0],3).tolist()} -> {np.round(p[-1],3).tolist()}")
print(f"  mid={np.round(mid,3).tolist()} travel={np.linalg.norm(p[-1]-p[0]):.3f} m")

base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
props = []
for i in json.load(open(base + "/configs/scenes/apt_0.scene_instance.json")).get("object_instances", []):
    t = str(i.get("template_name","")).split("/")[-1]
    tr = i.get("translation", [0,0,0])
    props.append((t, np.array([float(tr[0]), -float(tr[2]), float(tr[1])])))
print(f"  props: {len(props)}")

OBJ_R = asset.radius
FOCAL = 40.0
SW, SH = 36.0, 36.0*1080/1920
print(f"\n{'azim':>6} {'dist':>6} {'objfrac':>8} {'nearest_prop':>13} {'left_clutter':>13}  best_prop")
rows = []
for az_deg in range(0, 360, 15):
    az = math.radians(az_deg)
    # camera sits on the circle around mid, perpendicular-ish to the motion
    for dist in (1.6, 2.2, 2.8):
        pos = np.array([mid[0] + dist*math.cos(az), mid[1] + dist*math.sin(az), mid[2] + 0.42])
        look = np.array([mid[0], mid[1], mid[2] + 0.05])
        fwd = look - pos; fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        fov_h = 2*math.atan(SW/(2*FOCAL)); fov_v = 2*math.atan(SH/(2*FOCAL))
        # object screen fraction
        vv = mid - pos; z = float(vv @ fwd)
        objfrac = (2*OBJ_R) / (2*z*math.tan(fov_h/2))
        near, left_near = 1e9, 1e9
        best = "-"
        for t, w in props:
            vp = w - pos; zp = float(vp @ fwd)
            if zp <= 0.15: continue
            nx = math.atan2(float(vp @ right), zp)/(fov_h/2)
            ny = math.atan2(float(vp @ up), zp)/(fov_v/2)
            if abs(nx) > 1.0 or abs(ny) > 1.0: continue
            if zp < near: near, best = zp, t
            if nx < -0.25 and zp < left_near: left_near = zp
        rows.append((az_deg, dist, objfrac, near, left_near, best))
# score: object reasonably large, no prop closer than ~1.2 m, left side clear
def score(r):
    az, dist, of, near, lf, _ = r
    if of < 0.10 or of > 0.55: return -1
    s = 0.0
    s += 2.0 if near > 1.6 else (0.5 if near > 1.0 else -3.0)
    s += 2.0 if lf > 2.0 else (0.0 if lf > 1.2 else -2.0)
    return s
rows.sort(key=score, reverse=True)
print(f"{'azim':>6} {'dist':>6} {'objfrac':>8} {'near_prop_m':>12} {'left_near_m':>12}  score  prop")
for r in rows[:14]:
    az, dist, of, near, lf, best = r
    print(f"{az:6d} {dist:6.1f} {of:8.3f} {near:12.2f} {lf:12.2f} {score(r):6.1f}  {best}")
PY
