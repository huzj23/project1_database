#!/usr/bin/env bash
# V5.5 stage 03: decisive test of the LAST server-side route to Blender >= 4.0.
#
# Hidden Alley's .blend header is 400 (Blender 4.0); the only runnable server Blender is
# 3.4.1, which segfaults reading it.  Official Blender 4.x tarballs need glibc >= 2.28 and
# this host is 2.17.
#
# conda-forge builds against a sysroot pinned to glibc 2.17, so IF a conda-forge blender
# package exists, micromamba (a single static binary, no glibc dependency) can install it
# entirely under tools/ in the workspace.  That touches nothing shared.
#
# 01 s.19 permits project runtime deps from inside the workspace; 06 s.4 forbids
# upgrading the shared glibc, which nothing here does.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. does conda-forge publish blender for linux-64? ==="
timeout 300 "$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json, urllib.request

for url in (
    "https://api.anaconda.org/package/conda-forge/blender",
    "https://conda.anaconda.org/conda-forge/linux-64/repodata.json",
):
    print(f"--- {url}")
    try:
        with urllib.request.urlopen(url, timeout=240) as r:
            raw = r.read()
        print(f"    HTTP 200, {len(raw)} bytes")
        if url.endswith("repodata.json"):
            data = json.loads(raw)
            names = set()
            for section in ("packages", "packages.conda"):
                for fn in data.get(section, {}):
                    if fn.startswith("blender-"):
                        names.add(fn)
            print(f"    blender packages: {len(names)}")
            for n in sorted(names)[-15:]:
                print(f"      {n}")
        else:
            data = json.loads(raw)
            print(f"    package record keys: {sorted(data.keys())[:12]}")
    except Exception as exc:
        print(f"    {type(exc).__name__}: {exc}")
PY

echo
echo "=== B. is micromamba obtainable as a static binary? ==="
timeout 200 "$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import urllib.request
url = "https://micro.mamba.pm/api/micromamba/linux-64/latest"
try:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=150) as r:
        print(f"  {url} -> HTTP {r.status}, content-length={r.headers.get('content-length')}")
except Exception as exc:
    print(f"  {type(exc).__name__}: {exc}")
PY

echo
echo "=== C. what Blender versions does the Blender CDN still serve? ==="
timeout 200 "$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import urllib.request
# Blender 3.6 LTS is the newest series built against glibc 2.17 in some builds; 4.0+ is not.
for v in ("3.6.23", "4.0.2", "4.1.1"):
    url = f"https://download.blender.org/release/Blender{v.rsplit('.',1)[0]}/blender-{v}-linux-x64.tar.xz"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"  {v}: HTTP {r.status} content-length={r.headers.get('content-length')}")
    except Exception as exc:
        print(f"  {v}: {type(exc).__name__}: {exc}")
PY
