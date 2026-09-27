#!/usr/bin/env bash
# ===========================================================================
# Deploy T1: the two new scenario configs + widen the placement rectangle to the
# MEASURED clear floor area (5.1 x 3.7 m = 18.87 m^2), and remove the plush
# elephant from free_fall.
#
# Placement vs collision (now clearly separated):
#   collision  = the scene's own floor mesh, 81.61 m^2   (the patch is DELETED)
#   placement  = bounds_xy, now 5.1 x 3.7 m of raycast-verified clear floor
#                (was 1.7 x 1.7 m pinned for reproducible framing)
#
# The elephant is removed from free_fall per the user: it is material_class soft
# and we have no soft-body adaptation, so it must not appear in constant_force,
# free_fall or projectile.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
MAPS="$REPO/configs/maps.yaml"
cp "$MAPS" "$WS/tmp/maps_pre_clear.bak"

echo "=== 1) widen placement bounds_xy to the measured clear rectangle ==="
"$WS/tools/conda_env/bin/python" - "$MAPS" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
out, in_region = [], False
for ln in lines:
    if "region_id: replicad_apartment_floor_pinned" in ln:
        in_region = True; out.append(ln); continue
    if in_region:
        s = ln.strip(); ind = ln[:len(ln)-len(ln.lstrip())]
        if s.startswith("position:"):
            out.append(ind + "position: [0.6500, -2.1500, 0.0007]"); continue
        if s.startswith("bounds_xy:"):
            out.append(ind + "bounds_xy: [-1.9000, 3.2000, -4.0000, -0.3000]")
            out.append(ind + "# Placement rectangle widened from the old 1.7 x 1.7 m pin to")
            out.append(ind + "# 5.1 x 3.7 m = 18.87 m^2 of raycast-verified clear floor")
            out.append(ind + "# (grid 0.10 m over the floor footprint; a point is clear when the")
            out.append(ind + "# first downward hit is the floor itself, z < 0.05).  62.3% of the")
            out.append(ind + "# 8500 sampled points were clear; this is the largest clear")
            out.append(ind + "# rectangle found.  Collision uses the extracted floor mesh, so")
            out.append(ind + "# bounds_xy now bounds PLACEMENT only.")
            in_region = False; continue
    out.append(ln)
open(p, "w").write("\n".join(out))
print("  bounds_xy updated")
PY

echo
echo "=== 2) remove the plush elephant from free_fall ==="
FF="$REPO/configs/scenarios/free_fall_gso.yaml"
cp "$FF" "$WS/tmp/free_fall_gso_pre.bak"
"$WS/tools/conda_env/bin/python" - "$FF" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
old = re.search(r"  asset_ids:\n(?:    - .*\n)+", s).group(0)
new = ("  # NO plush elephant: material_class soft, and we have no soft-body\n"
       "  # adaptation, so it must not appear in free_fall / constant_force /\n"
       "  # projectile.  Firm objects only.\n"
       "  asset_ids:\n"
       "    - gso_down_to_earth_orchid_pot_ceramic_lime\n"
       "    - gso_ecoforms_plant_container_gp16a_coral\n"
       "    - gso_mad_gab_refresh_card_game\n")
s = s.replace(old, new)
# 81 frames at 16 fps = 5.0625 s, matching the mentor's dataset spec
s = s.replace("  duration_seconds: 1.0\n", "  duration_seconds: 5.0625\n")
s = s.replace("  frame_count: 16\n", "  frame_count: 81\n")
# larger drop so the airborne phase occupies more of the 81 frames
s = s.replace("  drop_height_absolute_range: [0.30, 0.42]\n",
              "  drop_height_absolute_range: [1.60, 2.40]\n")
s = s.replace("  drop_height_object_extent_range: [1.2, 1.8]\n",
              "  drop_height_object_extent_range: [8.0, 14.0]\n")
s = s.replace("  min_drop_height: 0.22\n", "  min_drop_height: 1.40\n")
s = s.replace("  min_drop_distance: 0.25\n", "  min_drop_distance: 1.40\n")
open(p, "w").write(s)
print("  free_fall_gso.yaml updated (81 frames, 1.6-2.4 m drop, no elephant)")
PY

echo
echo "=== 3) deploy the two new configs ==="
cp "$WS/tools/cfg_rolling_gso.yaml" "$REPO/configs/scenarios/rolling_gso.yaml"
cp "$WS/tools/cfg_constant_force_gso.yaml" "$REPO/configs/scenarios/constant_force_gso.yaml"
sed -i 's/\r$//' "$REPO/configs/scenarios/rolling_gso.yaml" "$REPO/configs/scenarios/constant_force_gso.yaml"
ls -la "$REPO/configs/scenarios/" | sed 's/^/  /'

echo
echo "=== 4) validate all configs parse and the region loads ==="
cd "$REPO" && "$WS/tools/conda_env/bin/python" - <<'PY'
import sys, yaml; sys.path.insert(0,"src")
for f in ("rolling_gso","constant_force_gso","free_fall_gso"):
    d = yaml.safe_load(open(f"configs/scenarios/{f}.yaml"))
    t = d["timing"]
    ok = t["duration_seconds"]*t["video_fps"] == t["frame_count"]
    print(f"  {f}: frames={t['frame_count']} fps={t['video_fps']} dur={t['duration_seconds']} consistent={ok}")
    print(f"     assets={d['selection']['asset_ids']}")
from physim.assets import AssetManager
from physim.maps import MapManager
am=AssetManager("configs/assets.yaml","assets"); mm=MapManager("configs/maps.yaml",am)
m=mm.get("replicad_apartment", require_files=True)
for s in m.surfaces:
    x0,x1,y0,y1 = s.bounds_xy
    print(f"  surface {s.surface_id}")
    print(f"    placement {x1-x0:.2f} x {y1-y0:.2f} m = {(x1-x0)*(y1-y0):.2f} m^2")
    print(f"    collision = {'MESH ' + str(s.collision_simulation_path.name) if s.collision_simulation_path else 'BOX (patch!)'}")
PY
