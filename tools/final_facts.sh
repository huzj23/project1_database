#!/usr/bin/env bash
# ===========================================================================
# Final facts before mutating the remote repo:
#   1. size of the dark_wood map set (to judge shipping it inside the asset)
#   2. do the mentor's own assets declare visual.material?  (precedent check)
#   3. is the elephant's visual/ self-contained (OBJ+MTL+texture)?
#   4. BACK UP the remote manifest + README so the mentor's 11 records can be
#      restored/merged if anything goes wrong.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
BK="$WS/tmp/hf_backup"; mkdir -p "$BK"

echo "=== 1. dark_wood map set size ==="
D="$WS/models/pbr_textures/wood_textures/dark_wood.blend/textures"
ls -la "$D" | sed 's/^/  /'
du -sb "$D" | awk '{printf "  TOTAL: %.2f MB\n", $1/1e6}'

echo
echo "=== 2. does ANY mentor asset declare visual.material? ==="
grep -rn 'material:' assets/*/*/asset.yaml 2>/dev/null | sed 's/^/  /' || echo "  none"

echo
echo "=== 3. elephant visual/ self-contained? ==="
ls -la assets/objects/special_plush_elephant/visual/ | sed 's/^/  /'
echo "  --- visual/model.mtl references ---"
cat assets/objects/special_plush_elephant/visual/model.mtl | sed 's/^/  | /'
echo "  --- OBJ references ---"
grep -n 'mtllib\|usemtl' assets/objects/special_plush_elephant/visual/model.obj | head | sed 's/^/  /'

echo
echo "=== 4. BACK UP the remote manifest + README (before any mutation) ==="
export HF_TOKEN="${HF_TOKEN:?}"
export HF_HUB_DISABLE_TELEMETRY=1
"$PY" - <<PY 2>&1 | sed 's/^/  /'
import shutil, json, os
from huggingface_hub import hf_hub_download
REPO = "physics-video-lab/physics-video-assets"
BK = "$BK"
for name in ("assets_manifest.json", "README.md"):
    p = hf_hub_download(repo_id=REPO, filename=name, repo_type="dataset", force_download=True)
    dst = os.path.join(BK, "REMOTE_" + name)
    shutil.copy2(p, dst)
    print(f"backed up {name} -> {dst}  ({os.path.getsize(dst):,} bytes)")
d = json.load(open(os.path.join(BK, "REMOTE_assets_manifest.json")))
print("manifest assets:", [a["id"] for a in d["assets"]])
print("manifest schema_version:", d.get("schema_version"), "repository:", d.get("repository"))
tot = sum(f["bytes"] for a in d["assets"] for f in a["files"])
print(f"manifest describes {sum(len(a['files']) for a in d['assets'])} files, {tot/1e6:.2f} MB")
PY
