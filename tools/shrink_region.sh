#!/usr/bin/env bash
# Root cause of the persistent wall shots:
#
# The support region I derived was 3.8 x 4.5 m but only guaranteed 1.2 m of
# clearance.  The drop point is sampled anywhere inside it, so a draw near the
# region edge leaves the camera (2.05 m away, in a policy-chosen direction) with
# no room -- hence a frame full of wall.
#
# The measured BEST point, (1.00, -4.30), has 3.40 m of clearance.  Shrink the
# region to a box around that point so that
#     (drop-point offset) + (camera stand-off 2.05 m) <= clearance 3.40 m
# holds for every possible draw.  +/-0.8 m keeps the worst case at 2.85 m.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
maps = repo / "configs/maps.yaml"
t = maps.read_text()

BX, BY, HALF = 1.00, -4.30, 0.80
x0, x1 = BX - HALF, BX + HALF
y0, y1 = BY - HALF, BY + HALF
snippet = f"""  replicad_apartment:
    environment_asset_id: replicad_apartment
    surface_groups:
      - surface_type: floor
        object_extent_range_m: [0.03, 0.35]
        edge_margin: 0.20
        clearance: 0.4
        collision_thickness: 0.05
        regions:
          - region_id: replicad_apartment_floor_open_core
            cleanliness: verified_clear
            verification: raycast_grid_0p10m_min_clearance_3p40m_shrunk_to_keep_camera_inside
            position: [{BX:.4f}, {BY:.4f}, 0.0007]
            normal: [0.0, 0.0, 1.0]
            bounds_xy: [{x0:.4f}, {x1:.4f}, {y0:.4f}, {y1:.4f}]
"""
t = re.sub(r"\n  replicad_apartment:\n(?:    .*\n|      .*\n|        .*\n|          .*\n|            .*\n)+",
           "\n" + snippet, t)
maps.write_text(t)

d = yaml.safe_load(open(maps))
reg = d["maps"]["replicad_apartment"]["surface_groups"][0]["regions"][0]
print("  region   :", reg["region_id"])
print("  bounds   :", reg["bounds_xy"])
b = reg["bounds_xy"]
print(f"  size     : {b[1]-b[0]:.2f} x {b[3]-b[2]:.2f} m")
print(f"  worst-case camera offset from best point: "
      f"{max(abs(b[0]-1.0), abs(b[1]-1.0), abs(b[2]+4.3), abs(b[3]+4.3)):.2f} m "
      f"+ standoff 2.05 m  <= clearance 3.40 m")
PY

echo
echo "=== run x0.5 across several seeds to check robustness ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
for seed in 1000 1001 1002; do
  rm -rf "$REPO/datasets/free_fall/seed-00$seed"
  "$BL" --background --factory-startup --python scripts/generate.py -- \
    --config configs/server.yaml --seed $seed --variant x0.5 > "$WS/log/p1_seed$seed.log" 2>&1
  rc=$?
  res=$("$WS/tools/conda_env/bin/python" - "$REPO/datasets/free_fall/seed-00$seed/x0.5" <<'PY'
import json, os, sys
import numpy as np
D = sys.argv[1]
p = os.path.join(D, "metadata.json")
if not os.path.isfile(p):
    print("INCOMPLETE"); raise SystemExit
md = json.load(open(p))
cam = (md.get("camera") or {}).get("position")
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
ctr = (c.max(axis=0) + c.min(axis=0)) / 2
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
# how close is the camera to a wall of the room box?
wx = min(cam[0] + 2.68, 4.58 - cam[0])
wy = min(cam[1] + 8.16, 4.89 - cam[1])
print(f"cam=({cam[0]:.2f},{cam[1]:.2f}) wall_clearance={min(wx,wy):.2f}m "
      f"standoff={np.linalg.norm(np.array(cam)-ctr):.2f}m "
      f"moving={100*(v>0.02).mean():.0f}% valid={(md.get('validation') or {}).get('valid')}")
PY
)
  printf '  seed %s: rc=%s  %s\n' "$seed" "$rc" "$res"
done
