#!/usr/bin/env bash
# ===========================================================================
# THE DECISIVE TEST: does a fresh download produce a USABLE asset?
#
# This is the user's actual requirement -- "确保其可用" / "后面直接用就行了". Simulate
# what a teammate does:
#   1. download into a pristine directory (no shared pbr_textures anywhere)
#   2. load every downloaded asset through AssetManager
#   3. render the elephant + apartment from the DOWNLOADED copies only
#
# Also separate the mentor's pre-existing verify failures from anything we caused.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?}"; export HF_HUB_DISABLE_TELEMETRY=1

echo "=== 1. are the verify 'missing' files PRE-EXISTING (mentor assets)? ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json
from huggingface_hub import hf_hub_download
from pathlib import Path
p = hf_hub_download(repo_id="physics-video-lab/physics-video-assets",
                    filename="assets_manifest.json", repo_type="dataset", force_download=True)
d = json.load(open(p, encoding="utf-8"))
OURS = {"special_plush_elephant", "replicad_apartment", "turntable"}
root = Path(".").resolve()
ours_missing, mentor_missing = [], []
for a in d["assets"]:
    for f in a["files"]:
        if not (root / f["path"]).exists():
            (ours_missing if a["id"] in OURS else mentor_missing).append(f["path"])
print(f"  missing files belonging to OUR assets    : {len(ours_missing)}")
for x in ours_missing: print("     ", x)
print(f"  missing files belonging to MENTOR assets : {len(mentor_missing)}")
for x in mentor_missing[:6]: print("     ", x)
print(f"  -> our upload caused none of them: {len(ours_missing) == 0}")
PY

echo
echo "=== 2. FRESH DOWNLOAD into a pristine tree ==="
D="$WS/tmp/fresh_dl"; rm -rf "$D"; mkdir -p "$D"
"$PY" - <<PY 2>&1 | sed 's/^/  /'
from huggingface_hub import snapshot_download
import os
d = snapshot_download(repo_id="physics-video-lab/physics-video-assets",
                      repo_type="dataset", local_dir="$D",
                      allow_patterns=["assets/objects/special_plush_elephant/**",
                                      "assets/environments/replicad_apartment/**",
                                      "assets/objects/turntable/**"],
                      max_workers=8)
print("downloaded to", d)
PY
echo "  --- downloaded tree ---"
find "$D/assets" -type f | sed "s|$D/||" | sort | sed 's/^/    /'
du -sh "$D" | sed 's/^/  total: /'

echo
echo "=== 3. is there ANY pbr_textures near the fresh download? ==="
ls -d "$D/../../models/pbr_textures" 2>/dev/null || echo "  none (as expected)"

echo
echo "=== 4. load the DOWNLOADED assets through AssetManager ==="
cat > /tmp/fresh_load.py <<PY
import sys, os
sys.path.insert(0, "$REPO/src")
from physim.assets import AssetManager
am = AssetManager("$D/assets", "$D/assets")
print("FL registry roots:", am.roots if hasattr(am,'roots') else 'n/a')
for aid in ("special_plush_elephant", "replicad_apartment", "turntable"):
    try:
        a = am.get(aid)
        print(f"FL {aid}: OK category={a.category} visual={os.path.basename(str(a.visual_path))}")
        if a.material:
            print(f"FL    material={a.material.pbr} textures={a.material.textures}")
    except Exception as e:
        print(f"FL {aid}: {type(e).__name__}: {e}")
PY
"$PY" /tmp/fresh_load.py 2>&1 | grep -aE '^FL|Error' | sed 's/^/  /'

echo
echo "=== 5. resolve the turntable material from the DOWNLOADED copy only ==="
"$PY" - <<PY 2>&1 | sed 's/^/  /'
import sys, os
sys.path.insert(0, "$REPO/src")
from physim.assets import AssetManager
from physim.render.materials import find_texture_dir, resolve_pbr_root
D = "$D"
am = AssetManager(f"{D}/assets", f"{D}/assets")
t = am.get("turntable")
print("  shared root exists:", resolve_pbr_root(f"{D}/assets").is_dir())
d = find_texture_dir(f"{D}/assets", "dark_wood", "wood_textures", t.material)
print("  resolved ->", d)
if d:
    print("  files:", sorted(os.listdir(d)))
PY
