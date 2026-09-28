#!/usr/bin/env bash
# V5.5 stage 03: can we obtain a Blender >= 4.0 that RUNS on this glibc 2.17 host,
# entirely inside the project workspace?
#
# Two candidate routes:
#   1. PyPI ``bpy`` wheel.  manylinux2014 wheels target glibc 2.17, so a bpy 4.0 cp310
#      wheel could work even though the official 4.2.23 tarball cannot.  Our project
#      python is 3.10, and bpy 4.0 is the last release built for cp310.
#   2. conda-forge ``blender`` package, which carries its own sysroot.
#
# Everything installs UNDER $WS/tools -- the shared OS is untouched.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== 1. what bpy versions exist on PyPI? ==="
timeout 120 "$PY" -m pip index versions bpy 2>&1 | head -8 | sed 's/^/  /'

echo
echo "=== 2. try to fetch a cp310 bpy 4.0 wheel (dry run, into tmp) ==="
mkdir -p "$WS/tmp/bpy_probe"
timeout 600 "$PY" -m pip download --no-deps --only-binary=:all: \
  --dest "$WS/tmp/bpy_probe" 'bpy==4.0.0' 2>&1 | tail -8 | sed 's/^/  /'

echo
echo "=== 3. what did we get? ==="
ls -la "$WS/tmp/bpy_probe" 2>/dev/null | sed 's/^/  /'

echo
echo "=== 4. inspect the wheel's glibc requirement tags ==="
W=$(ls "$WS/tmp/bpy_probe"/*.whl 2>/dev/null | head -1)
if [ -n "$W" ]; then
  echo "  wheel: $(basename "$W")"
  echo "  --- platform tags ---"
  "$PY" - "$W" <<'PY' 2>&1 | sed 's/^/    /'
import sys, zipfile
p = sys.argv[1]
with zipfile.ZipFile(p) as z:
    for n in z.namelist():
        if n.endswith("WHEEL"):
            print(z.read(n).decode())
            break
PY
else
  echo "  no wheel downloaded"
fi

echo
echo "=== 5. conda-forge blender availability (repodata query) ==="
timeout 180 "$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json, urllib.request
url = "https://conda.anaconda.org/conda-forge/linux-64/repodata.json"
try:
    with urllib.request.urlopen(url, timeout=150) as r:
        data = json.load(r)
    pkgs = [k for k in data.get("packages", {}) if k.startswith("blender-")]
    pkgs += [k for k in data.get("packages.conda", {}) if k.startswith("blender-")]
    print(f"blender packages found: {len(pkgs)}")
    for p in sorted(pkgs)[-12:]:
        print("   ", p)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
PY
