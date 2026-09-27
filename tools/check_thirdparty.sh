#!/usr/bin/env bash
# ===========================================================================
# The subagent's rolling config now says `physics_fps: 560` and its comment claims
# "the vendored Kubric wrapper never calls setTimeStep ... before that was fixed".
# That implies a change to third_party/, which AGENTS.md forbids without a
# documented reason -- and the physics backend used to HARD-ASSERT 240 Hz:
#     if sample.physics_fps != 240: raise ValueError(...)
# So establish exactly what changed and whether the other 6 scenarios are affected,
# BEFORE spending 20 minutes on a render.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== is third_party modified? ==="
find third_party -name '*.py' -newermt '-6 hours' 2>/dev/null | sed 's/^/  /' || true
echo "  --- setTimeStep occurrences ---"
grep -rn 'setTimeStep' third_party/ src/ 2>/dev/null | sed 's/^/  /'

echo
echo "=== the physics_fps assert ==="
grep -n 'physics_fps' src/physim/physics/pybullet_backend.py | sed 's/^/  /'

echo
echo "=== physics_fps across ALL scenario configs ==="
for f in configs/scenarios/*.yaml; do
  v=$(grep -E '^\s*physics_fps:' "$f" | head -1 | awk '{print $2}')
  echo "  $(basename $f): physics_fps=${v:-<default>}"
done

echo
echo "=== step_rate wiring in the backend ==="
grep -n 'step_rate\|step_rate\|frame_rate' src/physim/physics/pybullet_backend.py | sed 's/^/  /'

echo
echo "=== git status (is this a repo?) ==="
git status --short 2>/dev/null | head -30 | sed 's/^/  /' || echo "  not a git repo"

echo
echo "=== new tool files the subagent left ==="
ls -la "$WS/tools"/_t1b* "$WS/tools"/*roll* 2>/dev/null | sed 's/^/  /'
