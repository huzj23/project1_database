#!/usr/bin/env bash
# ===========================================================================
# Prepare the upload: read exactly what sync_hf_assets.py does on upload, and check
# whether huggingface_hub is installed (it was NOT, earlier).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== upload_assets() source ==="
sed -n '185,260p' scripts/sync_hf_assets.py | sed 's/^/  /'

echo
echo "=== verify_assets() source ==="
sed -n '/^def verify_assets/,/^def /p' scripts/sync_hf_assets.py | head -40 | sed 's/^/  /'

echo
echo "=== huggingface_hub available? ==="
"$PY" -c "import importlib.util as u; print('  hf_hub:', bool(u.find_spec('huggingface_hub')))" 2>&1
"$PY" -c "import huggingface_hub as h; print('  version:', h.__version__)" 2>&1 | tail -1

echo
echo "=== is the repo a git repo (so we know nothing we do lands in Git)? ==="
ls -d .git 2>/dev/null || echo "  no .git -> nothing can be committed"

echo
echo "=== what would be uploaded (file-level), dry-run ==="
"$PY" scripts/sync_hf_assets.py list --asset-id special_plush_elephant \
  --asset-id replicad_apartment --asset-id turntable \
  --allowed-license "CC BY-SA 4.0" --allowed-license "CC BY-NC 4.0" 2>&1 | sed 's/^/  /'

echo
echo "=== exact payload file list + total size ==="
"$PY" - <<'PY'
import sys
sys.path.insert(0, "scripts")
import importlib.util as u
spec = u.spec_from_file_location("sync", "scripts/sync_hf_assets.py")
m = u.module_from_spec(spec); spec.loader.exec_module(m)
from pathlib import Path
root = Path(".").resolve()
recs = m.discover_assets(root)
want = {"special_plush_elephant", "replicad_apartment", "turntable"}
for r in recs:
    if r.asset_id not in want:
        continue
    files = m._payload_files(r)
    tot = sum(f.stat().st_size for f in files)
    print(f"  {r.asset_id}  license={r.license}  files={len(files)}  {tot/1e6:.2f} MB")
    for f in files:
        print(f"      {f.stat().st_size:>12,}  {f.relative_to(root).as_posix()}")
PY
