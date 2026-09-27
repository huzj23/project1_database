#!/usr/bin/env bash
# ===========================================================================
# Dump the EXACT code blocks needed to make an asset's declared PBR material
# resolvable from inside the asset directory (so the turntable is self-contained
# after an HF download), plus the full README diff.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?}"; export HF_HUB_DISABLE_TELEMETRY=1

echo "=== A. MaterialSpec + AssetSpec.material + _material() ==="
grep -n 'class MaterialSpec' -A 22 src/physim/assets/__init__.py | sed 's/^/  /'
echo "  ----"
grep -n 'def _material' -A 24 src/physim/assets/__init__.py | sed 's/^/  /'

echo
echo "=== B. apply_declared_material full body ==="
sed -n '/^def apply_declared_material/,$p' src/physim/render/materials.py | head -70 | sed 's/^/  /'

echo
echo "=== C. blender_backend call sites ==="
sed -n '200,270p' src/physim/render/blender_backend.py | cat -n | sed 's/^/  /'

echo
echo "=== D. FULL README diff (remote vs our card) ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import difflib
from huggingface_hub import hf_hub_download
rem = hf_hub_download(repo_id="physics-video-lab/physics-video-assets",
                      filename="README.md", repo_type="dataset", force_download=True)
a = open(rem, encoding="utf-8").read().splitlines()
b = open("docs/HUGGINGFACE_DATASET_CARD.md", encoding="utf-8").read().splitlines()
for ln in difflib.unified_diff(a, b, "REMOTE", "LOCAL", lineterm="", n=1):
    print(ln)
PY
