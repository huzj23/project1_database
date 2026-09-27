#!/usr/bin/env bash
# ===========================================================================
# Read the FULL remote README.md and see exactly what --dry-run does, so the upload
# can be made ADDITIVE instead of destructive.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?}"
export HF_HUB_DISABLE_TELEMETRY=1

echo "=== FULL remote README.md ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  | /'
from huggingface_hub import hf_hub_download
p = hf_hub_download(repo_id="physics-video-lab/physics-video-assets",
                    filename="README.md", repo_type="dataset", force_download=True)
print(open(p, encoding="utf-8").read())
PY

echo
echo "=== local DATASET_CARD (what upload would put in its place) ==="
wc -c docs/HUGGINGFACE_DATASET_CARD.md | sed 's/^/  /'
head -30 docs/HUGGINGFACE_DATASET_CARD.md | sed 's/^/  | /'

echo
echo "=== how --dry-run is implemented ==="
grep -n 'dry_run' scripts/sync_hf_assets.py | sed 's/^/  /'
sed -n '/dry_run/,+12p' scripts/sync_hf_assets.py | head -30 | sed 's/^/  /'
