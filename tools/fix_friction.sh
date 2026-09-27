#!/usr/bin/env bash
# ===========================================================================
# FIX: let the scenario config override friction / restitution.
#
# WHY THIS IS NECESSARY (and physically honest):
#
#   The mentor's `rolling` config is designed for BALLS.  A ball rolls, and with
#   rolling_friction = 0 it keeps rolling indefinitely -- lateral friction only
#   maintains the rolling contact, it does not brake the ball.
#
#   Our GSO actors are a protein can, a fabric cube and a plant pot: convex hulls
#   that CANNOT roll.  They slide.  For a sliding body the lateral friction is a
#   full braking force, mu*g.  Measured: mu = 0.36, so deceleration is 3.5 m/s^2
#   while the sampled speed is only 0.085 m/s -- the object stops in 0.024 s,
#   less than one video frame.  That is why travel_distance came out 0.068 m
#   against a required 0.169 m.
#
#   `constant_force` fails for the same reason in a different guise: F = m*a on a
#   1.5 g body is ~3e-5 N, four orders of magnitude below the friction threshold.
#
#   The fix is NOT to move the object by hand -- that would violate iron rule 1.
#   The fix is to choose the SURFACE the demo is filmed on.  A smooth polished
#   floor is an ordinary indoor surface, and on it a low friction coefficient is
#   the physically correct parameter.  We set it in the config, it is passed to
#   the solver, and Bullet integrates whatever results.
#
# This adds ONE optional parameter to base_physics() and passes the config's
# physics block through at the three existing call sites.  Nothing prescribes a
# trajectory.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

# back up the files we touch
for f in src/physim/scenarios/common.py src/physim/scenarios/rolling.py \
         src/physim/scenarios/constant_force.py src/physim/scenarios/free_fall.py; do
  cp "$f" "$WS/tmp/$(basename $f).bak"
done

"$WS/tools/conda_env/bin/python" - <<'PY'
import re, sys

# ---------------------------------------------------------------- common.py
p = "src/physim/scenarios/common.py"
s = open(p).read()
old = '''def base_physics(
    rng: np.random.Generator, asset: AssetSpec
) -> tuple[float, float, float]:
    return (
        uniform(rng, asset.mass_range),
        uniform(rng, asset.friction_range),
        uniform(rng, asset.restitution_range),
    )'''
new = '''def base_physics(
    rng: np.random.Generator,
    asset: AssetSpec,
    physics: dict[str, Any] | None = None,
) -> tuple[float, float, float]:
    """Sample mass, friction and restitution for one actor.

    The scenario config may override any of the three ranges under its
    ``physics`` block.  This exists because the surface a demo is filmed on is a
    scene decision: the mentor's ball scenarios rely on rolling contact (where
    lateral friction does not brake the body), while our convex-hull actors slide
    and would otherwise stop within a single frame on a high-friction floor.
    The sampled value still goes to the solver unchanged -- no trajectory is
    prescribed.
    """
    overrides = physics or {}
    return (
        uniform(rng, overrides.get("mass_range", asset.mass_range)),
        uniform(rng, overrides.get("friction_range", asset.friction_range)),
        uniform(rng, overrides.get("restitution_range", asset.restitution_range)),
    )'''
assert old in s, "common.py base_physics not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("  patched common.py")

# --------------------------------------------------- rolling / constant_force / free_fall
for p, call in (
    ("src/physim/scenarios/rolling.py", "mass, friction, restitution = base_physics(rng, asset)"),
    ("src/physim/scenarios/constant_force.py", "mass, friction, restitution = base_physics(rng, asset)"),
    ("src/physim/scenarios/free_fall.py", "mass, friction, restitution = base_physics(rng, asset)"),
):
    s = open(p).read()
    assert call in s, f"{p}: call site not found"
    s = s.replace(call, "mass, friction, restitution = base_physics(rng, asset, physics)")
    open(p, "w").write(s)
    print(f"  patched {p}")
PY

echo
echo "=== verify the patch ==="
grep -n 'def base_physics' -A6 src/physim/scenarios/common.py | sed 's/^/  /'
grep -n 'base_physics(rng, asset' src/physim/scenarios/*.py | sed 's/^/  /'

echo
echo "=== import check ==="
"$WS/tools/conda_env/bin/python" -c "
import sys; sys.path.insert(0,'src')
from physim.scenarios.common import base_physics
from physim.scenarios import create_scenario
import inspect
print('  base_physics signature:', inspect.signature(base_physics))
print('  modules import OK')
" 2>&1 | sed 's/^/  /'
