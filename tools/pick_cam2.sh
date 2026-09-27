#!/usr/bin/env bash
# ===========================================================================
# Pick the new rolling camera, with a corrected score.
#
# Previous run scored everything -1 because I required objfrac >= 0.10, but the can
# is only 0.121 m across, so at a distance that frames the whole 0.672 m trajectory
# the honest figure is ~0.08 -- comparable to the already-accepted free_fall clips
# (0.049-0.068).  The floor was simply wrong, not the candidates.
#
# What the user actually asked for: the camera was "too close" with close clutter on
# the LEFT.  So the score must reward
#   * a CLEAR left half (no prop nearer than ~2 m on the left),
#   * nothing close anywhere (no prop nearer than ~1.6 m),
#   * motion across the frame (camera roughly perpendicular to the travel),
#   * the object still legible (objfrac in a sane band),
#   * the whole trajectory inside the frame at both ends.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -40
import sys, json, math
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
mv = p[-1,:2] - p[0,:2]; mv /= np.linalg.norm(mv)
print(f"  mid={np.round(mid,3).tolist()} travel={np.linalg.norm(p[-1]-p[0]):.3f} m "
      f"dir={np.round(mv,3).tolist()}")

base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
props = []
for i in json.load(open(base + "/configs/scenes/apt_0.scene_instance.json")).get("object_instances", []):
    t = str(i.get("template_name","")).split("/")[-1]
    tr = i.get("translation", [0,0,0])
    props.append((t, np.array([float(tr[0]), -float(tr[2]), float(tr[1])])))

OBJ_R, FOCAL = asset.radius, 40.0
SW = 36.0; SH = 36.0*1080/1920

def evaluate(az_deg, dist, height):
    az = math.radians(az_deg)
    pos = np.array([mid[0] + dist*math.cos(az), mid[1] + dist*math.sin(az), mid[2] + height])
    look = np.array([mid[0], mid[1], mid[2] + 0.04])
    fwd = look - pos; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fov_h = 2*math.atan(SW/(2*FOCAL)); fov_v = 2*math.atan(SH/(2*FOCAL))
    # object size
    vv = mid - pos; z = float(vv @ fwd)
    if z <= 0.2: return None
    objfrac = (2*OBJ_R)/(2*z*math.tan(fov_h/2))
    # trajectory must fit at BOTH ends with margin
    worst = 0.0
    for pt in (p[0], p[-1], p[len(p)//2]):
        dv = pt - pos; zz = float(dv @ fwd)
        nx = math.atan2(float(dv @ right), zz)/(fov_h/2)
        ny = math.atan2(float(dv @ up), zz)/(fov_v/2)
        worst = max(worst, abs(nx), abs(ny))
    # clutter
    near, left_near, best = 1e9, 1e9, "-"
    for t, w in props:
        vp = w - pos; zp = float(vp @ fwd)
        if zp <= 0.15: continue
        nx = math.atan2(float(vp @ right), zp)/(fov_h/2)
        ny = math.atan2(float(vp @ up), zp)/(fov_v/2)
        if abs(nx) > 1.0 or abs(ny) > 1.0: continue
        if zp < near: near, best = zp, t
        if nx < -0.25 and zp < left_near: left_near = zp
    # perpendicularity: camera direction vs motion
    cam_dir = (pos[:2]-mid[:2]); cam_dir /= np.linalg.norm(cam_dir)
    perp = abs(float(cam_dir @ mv))
    return dict(az=az_deg, dist=dist, h=height, pos=pos, look=look, objfrac=objfrac,
                near=near, left=left_near, best=best, worst=worst, perp=perp)

cands = []
for az in range(0, 360, 10):
    for dist in (1.4, 1.8, 2.2, 2.6):
        for h in (0.35, 0.55, 0.75):
            r = evaluate(az, dist, h)
            if r: cands.append(r)

def score(r):
    if r["worst"] > 0.90: return -99          # trajectory must fit
    if not (0.055 <= r["objfrac"] <= 0.45): return -99
    s = 0.0
    s += 3.0 if r["left"] > 2.5 else (1.0 if r["left"] > 1.6 else -4.0)
    s += 2.0 if r["near"] > 2.0 else (0.5 if r["near"] > 1.4 else -3.0)
    s += 2.0 * (1.0 - r["perp"])              # want perpendicular to motion
    return s

cands.sort(key=score, reverse=True)
print(f"\n{'az':>4} {'dist':>5} {'h':>5} {'objfrac':>8} {'worst':>6} {'perp':>5} "
      f"{'near_m':>7} {'left_m':>7} {'score':>6}  nearest_prop")
for r in cands[:12]:
    print(f"{r['az']:4d} {r['dist']:5.1f} {r['h']:5.2f} {r['objfrac']:8.3f} "
          f"{r['worst']:6.3f} {r['perp']:5.2f} {r['near']:7.2f} {r['left']:7.2f} "
          f"{score(r):6.1f}  {r['best']}")
b = cands[0]
print(f"\n  BEST: pos={np.round(b['pos'],4).tolist()} look={np.round(b['look'],4).tolist()}")
print(f"        objfrac={b['objfrac']:.3f} near={b['near']:.2f} left={b['left']:.2f} "
      f"worst_norm={b['worst']:.3f}")
PY
