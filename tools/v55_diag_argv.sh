#!/usr/bin/env bash
# V5.5 stage 03: diagnose how Blender passes `--` arguments to a --python-expr runner.
# Small and fast: no scene is opened.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh

echo "=== what does sys.argv look like under --python-expr? ==="
"$BLENDER" --background --factory-startup --python-expr "
import sys
print('ARGV=' + repr(sys.argv))
" 2>&1 | grep -E '^ARGV='

echo
echo "=== with a trailing -- --scene hidden_alley ==="
"$BLENDER" --background --factory-startup --python-expr "
import sys
print('ARGV=' + repr(sys.argv))
print('HAS_DD=' + str('--' in sys.argv))
if '--' in sys.argv:
    i = sys.argv.index('--')
    print('AFTER_DD=' + repr(sys.argv[i+1:]))
" -- --scene hidden_alley 2>&1 | grep -E '^(ARGV|HAS_DD|AFTER_DD)='

echo
echo "=== does runpy see Blender's argv when run_path is used? ==="
cat > "$WS/tmp/probe_runpy.py" <<'PYEOF'
import sys
print("PROBE sys.argv =", sys.argv)
sys.argv = ["probe"] + (sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
print("PROBE after fix =", sys.argv)
PYEOF
"$BLENDER" --background --factory-startup --python-expr "
import runpy
runpy.run_path('$WS/tmp/probe_runpy.py', run_name='__main__')
" -- --scene hidden_alley 2>&1 | grep -E '^PROBE'
