#!/usr/bin/env bash
# V5.5 stage 03: Hidden Alley needs Blender >= 4.0 (its .blend header says 400) and the
# only runnable server Blender is 3.4.1.  The project's 4.2.23 binary cannot start on
# this host (needs glibc 2.26/2.27, host has 2.17).
#
# Before declaring a blocker, check the one legitimate route that does not touch the
# shared OS and does not borrow anyone else's environment: a Blender from a conda
# package channel, installed INTO THE PROJECT WORKSPACE, which ships its own sysroot.
#
# 01 section 19 permits project runtime dependencies from inside the workspace.
# 06 section 4 forbids upgrading the shared glibc -- nothing here does that.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. what python environment do we actually have? ==="
echo "  --- tools/conda_env ---"
ls "$WS/tools/conda_env/bin" 2>/dev/null | head -30 | sed 's/^/    /'
echo "  --- is there a conda/micromamba executable anywhere in our tree? ---"
find "$WS/tools" -maxdepth 3 -type f \( -name 'conda' -o -name 'micromamba' -o -name 'mamba' -o -name 'conda.exe' \) 2>/dev/null | sed 's/^/    /'
echo "  --- python version / prefix ---"
"$PY" -c "import sys; print('    exe   :', sys.executable); print('    prefix:', sys.prefix); print('    ver   :', sys.version.split()[0])"

echo
echo "=== B. does tools/conda_env have pip and can it reach the network? ==="
"$PY" -m pip --version 2>&1 | head -2 | sed 's/^/  /'
timeout 30 "$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import urllib.request
for url in ("https://pypi.org/simple/", "https://conda.anaconda.org/conda-forge/noarch/repodata.json"):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            print(f"{url} -> HTTP {r.status}")
    except Exception as exc:
        print(f"{url} -> {type(exc).__name__}: {exc}")
PY

echo
echo "=== C. is a glibc-independent Blender available via pip? (e.g. bpy wheels) ==="
timeout 60 "$PY" -m pip index versions bpy 2>&1 | head -5 | sed 's/^/  /'
echo "  --- what bpy versions exist for cp310 ---"
timeout 90 "$PY" -m pip download --no-deps --dest "$WS/tmp/bpy_probe" bpy==4.2.0 2>&1 | tail -5 | sed 's/^/  /'

echo
echo "=== D. glibc version requirements of the 4.2.23 binary, precisely ==="
B42="$WS/tools/runtime/blender-4.2.23-linux-x64/blender"
echo "  --- highest GLIBC_ symbols the binary needs ---"
strings "$B42" 2>/dev/null | grep -aoE 'GLIBC_2\.[0-9]+' | sort -uV | tail -5 | sed 's/^/    /'
echo "  --- count of the 3.4.1 binary's needs, for contrast ---"
strings "$WS/tools/runtime/blender-3.4.1-linux-x64/blender" 2>/dev/null | grep -aoE 'GLIBC_2\.[0-9]+' | sort -uV | tail -3 | sed 's/^/    /'

echo
echo "=== E. summary of the decision inputs ==="
echo "  host glibc        : $(ldd --version 2>&1 | head -1)"
echo "  server blender    : 3.4.1 (runs) / 4.2.23 (cannot start)"
echo "  hidden alley hdr  : 400 (Blender 4.0)"
echo "  => a Blender >= 4.0 that runs on glibc 2.17 is REQUIRED for Hidden Alley on this host"
