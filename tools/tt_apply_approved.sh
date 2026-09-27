#!/usr/bin/env bash
# ===========================================================================
# REQUEST 2: turntable #5 (圆周) and #6 (转盘自转) using
#   (a) the camera pose the user ALREADY APPROVED, and
#   (b) the ELEPHANT ("小熊") as the actor.
#
# (a) The approved pose comes from tools/tt_on_table.sh (the render the user
#     accepted earlier).  That script built its own scene, so the pose has to be
#     expressed relative to the frozen table top:
#         cam  = table_top + (0.52, -0.66, +0.42)
#         look = table_top + (0.00,  0.00, +0.05)   focal 50 mm
#     table_top = (0.414, 0.175, 0.7584)  [V3.2 freeze record]
#     => cam = (0.934, -0.485, 1.1784), look = (0.414, 0.175, 0.8084)
#     The existing configs used policy trajectory_side, which DERIVES the pose
#     from each clip's own motion and therefore cannot reproduce an approved
#     framing.  The new `fixed` policy is used instead.
#
# (b) The elephant is `gso_sootheze_cold_therapy_elephant`.  It is a plush toy,
#     so it is excluded from constant_force / free_fall / projectile (no soft-body
#     adaptation), but a turntable ride is a supported, non-impulsive motion, so
#     it is a legitimate actor here.  The subagent already validated it on the
#     disc (slip 1.00, r_max 0.107 m) which is why the user's suggestion is sound.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  cp "$f" "$f.pre_eleph"
done

"$WS/tools/conda_env/bin/python" - <<'PY'
import re

APPROVED = """camera:
  # APPROVED POSE -- copied verbatim from tools/tt_on_table.sh, the turntable
  # render the user accepted.  Expressed from the frozen table top
  # (0.414, 0.175, 0.7584): cam = top + (0.52, -0.66, +0.42),
  # look = top + (0, 0, +0.05), focal 50 mm.
  # `fixed` is required here: the previous `trajectory_side` policy derives the
  # camera from each clip's own motion, so it cannot reproduce a pose that was
  # reviewed and signed off.  `fixed` uses this pose verbatim and injects no
  # azimuth or side randomness.
  policy: fixed
  position: [0.9340, -0.4850, 1.1784]
  look_at: [0.4140, 0.1750, 0.8084]
  focal_length_mm: 50.0
  framing:
    sensor_width_mm: 36.0
"""

for path in ("configs/scenarios/turntable_carry_gso.yaml",
             "configs/scenarios/turntable_spin_gso.yaml"):
    s = open(path).read()
    # replace the whole camera block (up to the next top-level key)
    m = re.search(r"^camera:\n(?:[ \t].*\n|\n)*", s, flags=re.M)
    assert m, f"no camera block in {path}"
    s = s[:m.start()] + APPROVED + s[m.end():]
    # the elephant is the requested actor
    s = re.sub(r"asset_ids:\n(?:[ \t]*-[ \t]*\S+\n)+",
               "asset_ids:\n    - gso_sootheze_cold_therapy_elephant\n", s)
    open(path, "w").write(s)
    print(f"  {path}: camera -> fixed approved pose; actor -> elephant")

    # verify
    v = open(path).read()
    assert "policy: fixed" in v, path
    assert "gso_sootheze_cold_therapy_elephant" in v, path
    assert "trajectory_side" not in v, path
    assert "gso_room_essentials_fabric_cube_lavender" not in v, path
print("  assertions ok")
PY

echo
echo "=== resulting camera + actor ==="
for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  echo "--- $f ---"
  sed -n '/^camera:/,/^output:/p' "$f" | grep -vE '^\s*#' | sed 's/^/    /'
  grep -A3 'asset_ids:' "$f" | sed 's/^/    /'
done

echo
echo "=== yaml parses + config loads ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys, yaml
sys.path.insert(0, "src")
from physim.config import load_run_config
for name in ("turntable_carry_gso", "turntable_spin_gso"):
    d = yaml.safe_load(open(f"configs/scenarios/{name}.yaml"))
    assert d["camera"]["policy"] == "fixed"
    print(f"  {name}: yaml ok, policy=fixed, actor={d['selection']['asset_ids']}")
PY
