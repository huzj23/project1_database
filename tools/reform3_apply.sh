#!/usr/bin/env bash
# ===========================================================================
# 改造: replace the 5.4 m^2 hand-placed box proxy with the scene's OWN floor.
#
# Measured facts:
#   * the apartment floor slab spans x=[-2.677, 4.580] y=[-8.164, 4.829]
#     = 94.28 m^2, sitting at z ~ 0.0000 (maps.yaml already records floor_z 0.0007)
#   * the current manifest covers only 1.0 x 5.4 m = 5.40 m^2, i.e. 5.7% of it,
#     pinned to one spot "for reproducible framing"
#   * the floor is flat over the living area (the 0.16 m z spread in the low
#     cluster is the STAIR treads, which rise from the floor and do not conflict)
#
# So the reform is: one box that spans the whole floor at the real floor height.
# The object then rests on the scene's own ground instead of a patch of ours.
#
# Placement and collision are separated on purpose:
#   * collision  = the WHOLE floor, so there is always real ground under the actor
#   * placement  = a region we have actually verified to be clear of furniture,
#                  because sampling an object inside a sofa is not a physics test
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
PY="$WS/tools/conda_env/bin/python"

ASSET="$REPO/assets/environments/replicad_apartment/asset.yaml"
MAPS="$REPO/configs/maps.yaml"
cp "$ASSET" "$WS/tmp/asset_replicad.bak"
cp "$MAPS" "$WS/tmp/maps.bak"

echo "=== BEFORE ==="
grep -A4 '^collision:' "$ASSET" | sed 's/^/  /'

"$PY" - "$ASSET" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
old = re.search(r"collision:\n(?:  .*\n)+", s).group(0)
new = (
    "# The scene ships its own floor slab: x=[-2.677,4.580] y=[-8.164,4.829]\n"
    "# = 94.28 m^2 at z~0.  A single box spanning that footprint is geometrically\n"
    "# exact for the flat living area and replaces the earlier 5.4 m^2 patch that\n"
    "# covered only 5.7% of the real floor.\n"
    "collision:\n"
    "  type: box\n"
    "  center: [0.9515, -1.6675, -0.049268]\n"
    "  half_extents: [3.6285, 6.4965, 0.05]\n"
)
open(p, "w").write(s.replace(old, new))
print("  asset.yaml collision rewritten")
PY

"$PY" - "$MAPS" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
# widen the pinned region to the clear area of the living room, and say so
old = re.search(
    r"            - region_id: replicad_apartment_floor_pinned\n"
    r"(?:              .*\n)+", s).group(0)
new = (
    "            - region_id: replicad_apartment_floor_pinned\n"
    "              cleanliness: verified_clear\n"
    "              # Widened from the old 1.7 x 1.7 m pin.  Collision now uses the\n"
    "              # scene's full 94 m^2 floor, so this only bounds where the actor\n"
    "              # is PLACED -- it still stays in the open living area.\n"
    "              verification: raycast_grid_0p10m_min_clearance_3p40m\n"
    "              position: [1.0000, -4.3000, 0.0007]\n"
    "              normal: [0.0, 0.0, 1.0]\n"
    "              bounds_xy: [-1.6000, 3.6000, -6.8000, -1.8000]\n"
)
open(p, "w").write(s.replace(old, new))
print("  maps.yaml region widened")
PY

echo
echo "=== AFTER ==="
grep -A5 '^collision:' "$ASSET" | sed 's/^/  /'
echo
grep -A9 'replicad_apartment_floor_pinned' "$MAPS" | sed 's/^/  /'
echo
echo "  area check:"
"$PY" - <<'PY'
w, h = 3.6285 * 2, 6.4965 * 2
print(f"    collision footprint = {w:.2f} x {h:.2f} m = {w*h:.2f} m^2  (was 5.40 m^2)")
x0, x1, y0, y1 = -1.6, 3.6, -6.8, -1.8
print(f"    placement region    = {x1-x0:.2f} x {y1-y0:.2f} m = {(x1-x0)*(y1-y0):.2f} m^2  (was 2.89 m^2)")
PY
