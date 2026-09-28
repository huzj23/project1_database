#!/usr/bin/env bash
# V5.5 stage 03: last legitimate route to a server-side Blender >= 4.0 for Hidden Alley.
#
# Official Blender 4.x Linux tarballs need glibc >= 2.28; this host is 2.17.  conda-forge
# however builds against a sysroot pinned to glibc 2.17, so a conda-forge blender package
# may run here.  Query the channel index directly (fast) instead of the 200 MB repodata.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. conda-forge blender files, via the anaconda.org API ==="
timeout 240 "$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json, urllib.request

url = "https://api.anaconda.org/package/conda-forge/blender/files"
try:
    with urllib.request.urlopen(url, timeout=200) as r:
        data = json.load(r)
    print(f"total files: {len(data)}")
    linux = [f for f in data if f.get("attrs", {}).get("subdir") == "linux-64"]
    print(f"linux-64 files: {len(linux)}")
    # Show the newest few versions.
    linux.sort(key=lambda f: f.get("version", ""), reverse=True)
    seen = set()
    for f in linux[:40]:
        v = f.get("version")
        if v in seen:
            continue
        seen.add(v)
        deps = f.get("attrs", {}).get("depends", [])
        gd = [d for d in deps if "sysroot" in d or "libgcc" in d or "glibc" in d]
        print(f"  version {v:10s} basename={f.get('basename','')[:70]}")
        if gd:
            print(f"       deps: {gd}")
        if len(seen) >= 8:
            break
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
PY

echo
echo "=== B. decision summary ==="
cat <<'SUMMARY' | sed 's/^/  /'
  If a conda-forge blender >= 4.0 exists for linux-64, it is built against the
  conda sysroot (glibc 2.17) and can be installed INTO tools/ inside the workspace,
  without touching the shared OS and without borrowing anyone else's environment.
  That would unblock Hidden Alley fully on the server (tmux-compliant).

  If it does not exist, the only remaining route is 06 section 4's designated local
  4.2.23 replay, which requires a local tmux that 01 section 21 says must be reported
  as a separate execution-mode conflict rather than silently replaced by a local
  background run.
SUMMARY
