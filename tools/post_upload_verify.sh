#!/usr/bin/env bash
# ===========================================================================
# INDEPENDENT post-upload verification: re-read the remote and confirm
#   * all 11 mentor assets still present (nothing destroyed)
#   * our 3 assets present with the expected files
#   * the mentor's own tooling can still LIST/DOWNLOAD/VERIFY the repo
#     (the strongest proof we did not break their workflow)
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?}"; export HF_HUB_DISABLE_TELEMETRY=1

"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json, os
from huggingface_hub import HfApi, hf_hub_download
REPO = "physics-video-lab/physics-video-assets"
api = HfApi(endpoint="https://huggingface.co")
info = api.repo_info(repo_id=REPO, repo_type="dataset")
print(f"repo private={info.private} sha={info.sha} lastModified={info.lastModified}")

p = hf_hub_download(repo_id=REPO, filename="assets_manifest.json",
                    repo_type="dataset", force_download=True)
d = json.load(open(p, encoding="utf-8"))
print(f"manifest schema={d.get('schema_version')} repository={d.get('repository')}")
MENTOR = ['basketball_court','classroom','street','food_apple','food_lime','food_lychee',
          'special_coffee_cup','sphere_baseball','sphere_basketball','sphere_football',
          'sphere_volleyball']
OURS = ['special_plush_elephant','replicad_apartment','turntable']
ids = [a['id'] for a in d['assets']]
print(f"\nassets ({len(ids)}):")
for a in d['assets']:
    tag = "OURS" if a['id'] in OURS else ("MENTOR" if a['id'] in MENTOR else "??")
    sz = sum(f['bytes'] for f in a['files'])
    print(f"  [{tag:6s}] {a['id']:28s} {a['license']:16s} {len(a['files']):3d} files {sz/1e6:8.2f} MB")
print(f"\nmentor assets intact: {all(i in ids for i in MENTOR)}")
print(f"our assets present  : {all(i in ids for i in OURS)}")
print(f"total files described: {sum(len(a['files']) for a in d['assets'])}")
PY

echo
echo "=== the mentor's OWN verify command against the live repo ==="
"$PY" scripts/sync_hf_assets.py verify 2>&1 | tail -5 | sed 's/^/  /'

echo
echo "=== the mentor's OWN list command (default CC0 allowlist) ==="
"$PY" scripts/sync_hf_assets.py list 2>&1 | head -14 | sed 's/^/  /'
