#!/usr/bin/env bash
# ===========================================================================
# Find the CANONICAL value of configs/server.yaml's scenario_config.
#
# MY runner clobbered it with `sed -i` (unnecessary: the run used
# configs/server_turntable_*.yaml, which carry their own scenario_config, and
# server.yaml is not read on that path).  Restore it to the real historical value
# rather than guessing -- look for any tool that sets it, and any archived copy.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== any tool that WRITES server.yaml's scenario_config ==="
grep -rn "scenario_config" "$WS/tools/"*.sh 2>/dev/null | grep -iE 'sed|re.sub|write' | sed 's/^/  /'

echo
echo "=== archived copies of server.yaml anywhere in the workspace ==="
find "$WS" -name 'server.yaml*' -o -name '*server.yaml.bak*' 2>/dev/null | head -10 | sed 's/^/  /'

echo
echo "=== what scenario_config does server.yaml hold now, and its mtime ==="
stat -c '  %y  %n' configs/server.yaml
grep -n 'scenario_config' configs/server.yaml | sed 's/^/  /'

echo
echo "=== which config did the NON-turntable delivered clips actually use? ==="
for d in datasets/rolling/seed-001001 datasets/constant_force/seed-002001 \
         datasets/free_fall/seed-003001 datasets/damping/seed-007001; do
  f="$d/x1/metadata.json"
  [ -f "$f" ] || continue
  echo "  $d:"
  "$WS/tools/conda_env/bin/python" -c "
import json; m=json.load(open('$f'))
print('      scenario=', m.get('scenario'))
" 2>/dev/null
done

echo
echo "=== the per-scenario configs that exist ==="
ls configs/server*.yaml | sed 's/^/  /'
echo "  --- each one's scenario_config ---"
for f in configs/server*.yaml; do
  printf "    %-38s %s\n" "$f" "$(grep -m1 'scenario_config' $f | sed 's/.*scenario_config: *//')"
done
