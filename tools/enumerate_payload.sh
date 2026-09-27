#!/usr/bin/env bash
# ===========================================================================
# Enumerate EXACTLY what would be uploaded, and diff the dataset card.
#
# Why: build_remote_manifest() rebuilds the manifest from ONLY the selected records,
# so a plain `upload` of our 3 assets would replace the remote manifest and ERASE the
# mentor's 11 asset records.  Before doing anything I need the exact payload and the
# exact card difference.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?}"
export HF_HUB_DISABLE_TELEMETRY=1

echo "=== _payload_files(): what HF receives per asset ==="
sed -n '/^def _payload_files/,/^def /p' scripts/sync_hf_assets.py | head -40 | sed 's/^/  /'

echo
echo "=== exact payload for our 3 assets ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util as u, sys
from pathlib import Path
spec = u.spec_from_file_location("syncmod", "scripts/sync_hf_assets.py")
m = u.module_from_spec(spec); sys.modules["syncmod"] = m; spec.loader.exec_module(m)
root = Path(".").resolve()
recs = m.discover_assets(root)
want = {"special_plush_elephant", "replicad_apartment", "turntable"}
grand = 0
for r in recs:
    if r.asset_id not in want: continue
    files = sorted(m._payload_files(r))
    tot = sum(f.stat().st_size for f in files)
    grand += tot
    print(f"\n{r.asset_id}  license={r.license}  dir={r.relative_directory.as_posix()}")
    print(f"  files={len(files)}  total={tot/1e6:.2f} MB")
    for f in files:
        print(f"    {f.stat().st_size:>12,}  {f.relative_to(root).as_posix()}")
print(f"\nGRAND TOTAL: {grand/1e6:.2f} MB")
PY

echo
echo "=== does the card differ from the remote README? ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import difflib
from huggingface_hub import hf_hub_download
rem = hf_hub_download(repo_id="physics-video-lab/physics-video-assets",
                      filename="README.md", repo_type="dataset", force_download=True)
a = open(rem, encoding="utf-8").read().splitlines()
b = open("docs/HUGGINGFACE_DATASET_CARD.md", encoding="utf-8").read().splitlines()
d = list(difflib.unified_diff(a, b, "REMOTE/README.md", "LOCAL/card", lineterm="", n=2))
print(f"remote lines={len(a)}  local lines={len(b)}  diff hunks={len(d)}")
for ln in d: print("   ", ln)
PY
