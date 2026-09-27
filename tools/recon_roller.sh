#!/usr/bin/env bash
# ===========================================================================
# REQUEST 1 DECISION: which of our real objects can PLAUSIBLY move at constant
# velocity on the floor?
#
# The user's objection is physical, not cosmetic: "管子怎么能无缘无故地在地面上
# 匀速运动呢?" -- a convex container sliding forever is unmotivated.  The honest fix
# is an object that ROLLS, because rolling explains constant velocity by itself
# (Newton's first law, no rolling resistance).
#
# To roll, the COLLISION geometry must be round.  So measure it, don't guess:
# for each candidate, fit the collision mesh and report how circular its
# cross-section actually is, and how far the COM drops per unit of roll.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== collision files for the candidates ==="
for a in gso_whey_protein_vanilla gso_ecoforms_plant_container_gp16a_coral \
         gso_down_to_earth_orchid_pot_ceramic_lime gso_room_essentials_fabric_cube_lavender \
         gso_mad_gab_refresh_card_game turntable; do
  echo "--- $a ---"
  ls -la assets/objects/$a/collision/ 2>/dev/null | tail -n +2 | sed 's/^/    /'
  grep -nE 'type|cylinder|box|sphere|mesh|radius|length|halfExtents' \
     assets/objects/$a/collision/*.urdf 2>/dev/null | head -6 | sed 's/^/    /'
done

echo
echo "=== circularity of each collision mesh (is it a roller?) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os, math
import numpy as np
try:
    import trimesh
except Exception as e:
    print("  trimesh unavailable:", e); raise SystemExit

for d in sorted(glob.glob("assets/objects/*")):
    aid = os.path.basename(d)
    objs = glob.glob(os.path.join(d, "collision", "*.obj"))
    if not objs:
        print(f"  {aid:46s} no .obj collision")
        continue
    m = trimesh.load(objs[0], force="mesh")
    v = np.asarray(m.vertices, dtype=np.float64)
    if len(v) < 4:
        print(f"  {aid:46s} too few verts"); continue
    ext = v.max(axis=0) - v.min(axis=0)
    order = np.argsort(ext)
    long_ax = order[2]          # spin axis candidate = longest extent
    a, b = order[0], order[1]   # the two short axes form the rolling cross-section
    c = v[:, [a, b]] - v[:, [a, b]].mean(axis=0)
    r = np.linalg.norm(c, axis=1)
    # circularity: if the cross-section is a circle, r is nearly constant
    cv = float(r.std() / max(r.mean(), 1e-12))
    # rolling smoothness: max height drop of the outline per 10 deg of roll
    ang = np.arctan2(c[:, 1], c[:, 0])
    rad = r
    drops = []
    for k in range(72):
        t = math.radians(k * 5.0)
        # support height of the outline as it rolls = max projection onto -z
        h = float((c[:, 0] * math.sin(t) - c[:, 1] * math.cos(t)).max())
        drops.append(h)
    drops = np.asarray(drops)
    wobble = float(drops.max() - drops.min())
    print(f"  {aid:46s} ext={np.round(ext,4)} long={long_ax} "
          f"r_mean={r.mean():.4f} r_cv={cv:.4f} roll_wobble={wobble:.4f}")
PY

echo
echo "=== table_top camera override in maps.yaml (must not fight a fixed pose) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import yaml
m = yaml.safe_load(open("configs/maps.yaml"))
for map_id, spec in (m.get("maps") or {}).items():
    for grp in spec.get("surface_groups", []) or []:
        if grp.get("surface_type") == "table_top":
            for reg in grp.get("regions", []) or []:
                print(f"  {map_id}/{reg.get('region_id')}: camera={reg.get('camera')}")
PY
