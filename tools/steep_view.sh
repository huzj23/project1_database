#!/usr/bin/env bash
# Last framing attempt: remove the two sources of uncontrolled variation.
#
# 1. The drop point moved between runs, so an azimuth verified clear for one point
#    was not clear for another.  Pin the support region to a small box around the
#    measured best point so the geometry is reproducible.
# 2. A shallow view skims along furniture height and keeps hitting shelving.  A
#    STEEP view (55 deg) looks down over it; the floor becomes the backdrop, which
#    is the clean look we want.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml, math
repo = pathlib.Path(sys.argv[1])

maps = repo / "configs/maps.yaml"
t = maps.read_text()
BX, BY, H = 1.00, -4.30, 0.85
snip = f"""  replicad_apartment:
    environment_asset_id: replicad_apartment
    surface_groups:
      - surface_type: floor
        object_extent_range_m: [0.03, 0.35]
        edge_margin: 0.10
        clearance: 0.4
        collision_thickness: 0.05
        regions:
          - region_id: replicad_apartment_floor_pinned
            cleanliness: verified_clear
            verification: raycast_grid_0p10m_min_clearance_3p40m_pinned_for_reproducible_framing
            position: [{BX:.4f}, {BY:.4f}, 0.0007]
            normal: [0.0, 0.0, 1.0]
            bounds_xy: [{BX - H:.4f}, {BX + H:.4f}, {BY - H:.4f}, {BY + H:.4f}]
"""
t = re.sub(r"\n  replicad_apartment:\n(?:    .*\n|      .*\n|        .*\n|          .*\n|            .*\n)+",
           "\n" + snip, t)
maps.write_text(t)

p = repo / "configs/scenarios/free_fall_gso.yaml"
s = p.read_text()
s = re.sub(r"elevation_degrees:\s*[0-9.]+", "elevation_degrees: 55.0", s)
s = re.sub(r"direction_degrees_range:\s*\[[^\]]*\]", "direction_degrees_range: [0.0, 0.0]", s)
p.write_text(s)

c = yaml.safe_load(open(p))
fr = c["camera"]["framing"]
e = math.radians(fr["elevation_degrees"])
print(f"  region   : pinned to ({BX:.2f},{BY:.2f}) +/- {H} m")
print(f"  elevation: {fr['elevation_degrees']} deg -> camera height {0.0007 + 2.05 * math.sin(e):.2f} m")
print("  direction: pinned to +x (removes the azimuth lottery)")
PY

echo
echo "=== run x0.5 ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
LOG="$WS/log/p1_smoke.log"
rm -rf "$REPO/datasets/free_fall/seed-001000"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$LOG" 2>&1
echo "  exit code: $?"
grep -oE 'ValueError:.*' "$LOG" | tail -1 | sed 's/^/  /'

"$WS/tools/conda_env/bin/python" - "$REPO/datasets/free_fall/seed-001000/x0.5" <<'PY'
import json, os, sys
import numpy as np
D = sys.argv[1]
p = os.path.join(D, "metadata.json")
if not os.path.isfile(p):
    print("  metadata.json missing")
    raise SystemExit
md = json.load(open(p))
cam = np.array((md.get("camera") or {}).get("position"))
look = np.array((md.get("camera") or {}).get("look_at"))
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
print(f"  camera  : ({cam[0]:.2f},{cam[1]:.2f},{cam[2]:.2f})  "
      f"look ({look[0]:.2f},{look[1]:.2f},{look[2]:.2f})")
print(f"  drop xy : ({c[0, 0]:.2f},{c[0, 1]:.2f})")
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
print(f"  frames  : {len(st)}  moving={100 * (v > 0.02).mean():.0f}%  "
      f"valid={(md.get('validation') or {}).get('valid')}")
PY
