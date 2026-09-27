#!/usr/bin/env bash
# ===========================================================================
# SAFETY REVIEW BEFORE UPLOAD.
#
# upload_assets() performs two WHOLE-FILE overwrites on the remote repo:
#     api.upload_file(card_path -> "README.md")
#     api.upload_file(manifest_path -> "assets_manifest.json")
#
# The repo already holds 11 mentor assets, so I must know whether these calls would
# destroy their records.  Specifically:
#   * does build_remote_manifest() MERGE the remote manifest, or rebuild from scratch?
#   * is the remote README.md the mentor's dataset card (safe to replace) or does it
#     hold the upload/download instructions the user referred to?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== build_remote_manifest() source ==="
sed -n '/^def build_remote_manifest/,/^def /p' scripts/sync_hf_assets.py | head -45 | sed 's/^/  /'

echo
echo "=== does it read the REMOTE manifest first? ==="
grep -n 'assets_manifest\|REMOTE_MANIFEST\|_download_manifest' scripts/sync_hf_assets.py | sed 's/^/  /'

echo
echo "=== DATASET_CARD constant ==="
grep -n '^DATASET_CARD\|^DEFAULT_REPO_ID\|^DEFAULT_ENDPOINT\|^DEFAULT_REVISION' scripts/sync_hf_assets.py | sed 's/^/  /'

echo
echo "=== CLI options (is there a --dry-run?) ==="
"$PY" scripts/sync_hf_assets.py upload --help 2>&1 | sed 's/^/  /'
