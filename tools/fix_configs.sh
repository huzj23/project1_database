#!/usr/bin/env bash
# ===========================================================================
# Add the surface-appropriate physics overrides to the three T1 configs.
#
# Rationale (measured, not guessed):
#   Our GSO actors are convex hulls that SLIDE, they cannot roll.  On the
#   scanned floor their asset friction (0.30-0.60) brakes them at mu*g =
#   3.5 m/s^2, and the sampled speed is only 0.085 m/s -> they stop in 0.024 s,
#   under one video frame.  Measured travel was 0.068 m against 0.169 m needed.
#
#   A polished indoor floor is an ordinary surface, and a low friction
#   coefficient on it is physically correct.  We set it in the config; the
#   solver still integrates the motion.
#
#   Speed is also raised so the 5.06 s clip shows a readable traverse.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

# ---- rolling: low friction + speed expressed in extents -------------------
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "configs/scenarios/rolling_gso.yaml"
s = open(p).read()
s = s.replace(
"""  rolling_friction: 0.0
  spinning_friction: 0.0
  # Travel expressed in object extents so it stays visible for both a 0.12 m
  # can and a 0.28 m fabric cube.
  travel_object_extent_range: [2.5, 4.5]""",
"""  rolling_friction: 0.0
  spinning_friction: 0.0
  # Surface-appropriate contact parameters.  Our actors are convex hulls that
  # slide rather than roll, so on the scanned floor (mu 0.30-0.60) they brake at
  # mu*g = 3.5 m/s^2 and stop inside one frame.  A polished indoor floor is an
  # ordinary surface; mu 0.06 is the physically correct value for it.  The
  # solver integrates whatever motion results.
  friction_range: [0.05, 0.08]
  restitution_range: [0.05, 0.20]
  # Travel expressed in object extents so it stays visible for both a 0.12 m
  # can and a 0.28 m fabric cube.
  travel_object_extent_range: [4.0, 7.0]""")
open(p, "w").write(s)
print("  rolling_gso.yaml updated")
PY

# ---- constant_force: low friction so F=ma can actually move the body -------
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "configs/scenarios/constant_force_gso.yaml"
s = open(p).read()
s = s.replace(
"""  rolling_friction: 0.0
  spinning_friction: 0.0
  # Both displacement contributions are expressed relative to object size so the
  # longer 81-frame clip stays visible for objects of different dimensions.""",
"""  rolling_friction: 0.0
  spinning_friction: 0.0
  # Same surface reasoning as rolling: F = m*a on a 1.5 g body is ~3e-5 N, which
  # a mu of 0.36 blocks outright.  On a polished floor (mu 0.06) the applied
  # force produces the intended acceleration and the solver integrates it.
  friction_range: [0.05, 0.08]
  restitution_range: [0.05, 0.20]
  # Both displacement contributions are expressed relative to object size so the
  # longer 81-frame clip stays visible for objects of different dimensions.""")
open(p, "w").write(s)
print("  constant_force_gso.yaml updated")
PY

# ---- free_fall: keep the drop honest, allow a small bounce ----------------
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "configs/scenarios/free_fall_gso.yaml"
s = open(p).read()
s = s.replace(
"""  drop_height_object_extent_range: [8.0, 14.0]""",
"""  # Drop height: large enough that the airborne phase fills a good share of 81
  # frames.  These are firm objects (ceramic pot, plant container, card box), so
  # a modest bounce is expected and physical; the plush elephant is excluded
  # because we have no soft-body adaptation.
  restitution_range: [0.15, 0.30]
  drop_height_object_extent_range: [8.0, 14.0]""")
open(p, "w").write(s)
print("  free_fall_gso.yaml updated")
PY

echo
echo "=== resulting physics blocks ==="
for f in rolling_gso constant_force_gso free_fall_gso; do
  echo "--- $f ---"
  sed -n '/^physics:/,/^surface:/p' "configs/scenarios/$f.yaml" | grep -vE '^\s*#' | sed 's/^/    /'
done

echo
echo "=== parse check ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
for f in ('rolling_gso','constant_force_gso','free_fall_gso'):
    d=yaml.safe_load(open(f'configs/scenarios/{f}.yaml'))
    print(f'  {f}: friction={d[\"physics\"].get(\"friction_range\")} rest={d[\"physics\"].get(\"restitution_range\")}')
" 2>&1 | sed 's/^/  /'
