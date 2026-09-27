#!/usr/bin/env bash
# ===========================================================================
# FINAL hygiene + consistency check.
#  1. no HF token anywhere in the project tree (mentor's explicit rule)
#  2. no stray backup files left in assets/
#  3. our 3 assets' manifests are internally consistent
#  4. the repo still validates end-to-end
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. token leakage scan (whole workspace, excluding caches) ==="
HITS=$(grep -rIl 'hf_[A-Za-z0-9]\{30,\}' "$WS" 2>/dev/null \
        | grep -v '/tmp/' | grep -v '\.git/' | grep -v '__pycache__' || true)
if [ -z "$HITS" ]; then echo "  CLEAN: no hf_ token in any tracked file"; else echo "  LEAK:"; echo "$HITS" | sed 's/^/    /'; fi
echo "  --- env var present in this shell? ---"
[ -n "${HF_TOKEN:-}" ] && echo "  HF_TOKEN set in this shell (transient)" || echo "  HF_TOKEN not set here (good)"

echo
echo "=== 2. strays in assets/ ==="
find assets -type f \( -name '*bak*' -o -name '*.pre_*' \) 2>/dev/null | sed 's/^/  /' || true
echo "  (nothing above = clean)"

echo
echo "=== 3. manifest consistency for our 3 assets ==="
"$PY" - <<'PY'
import sys, yaml
sys.path.insert(0, "src")
from physim.assets import AssetManager
am = AssetManager("configs/assets.yaml", "assets")
for aid in ("special_plush_elephant", "replicad_apartment", "turntable"):
    m = yaml.safe_load(open(f"assets/{'objects' if aid!='replicad_apartment' else 'environments'}/{aid}/asset.yaml"))
    c = m.get("collision") or {}
    print(f"  {aid}:")
    print(f"    id matches dir      : {m.get('id') == aid}")
    print(f"    category valid      : {m.get('category') in ('sphere','cylinder','cube','cone','food','special','environment')} ({m.get('category')})")
    print(f"    license set         : {bool(m.get('license'))} ({m.get('license')})")
    print(f"    source/ documented  : {'source_page' in m or 'source' in m}")
    if c:
        print(f"    collision type      : {c.get('type')}")
        if c.get("triangles") is not None:
            print(f"    tris<=max           : {c['triangles'] <= c.get('max_triangles', 512)} ({c['triangles']}/{c.get('max_triangles')})")
        if c.get("footprint_radius") and c.get("bounding_radius"):
            print(f"    footprint<=bounding : {c['footprint_radius'] <= c['bounding_radius']}")
        if c.get("mesh_sha256"):
            print(f"    mesh_sha256 present : True")
    a = am.get(aid)
    print(f"    loads via manager   : OK")
PY

echo
echo "=== 4. end-to-end regression ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -2 | sed 's/^/  /'

echo
echo "=== 5. remote final state ==="
export HF_TOKEN="${HF_TOKEN:?}"; export HF_HUB_DISABLE_TELEMETRY=1
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json
from huggingface_hub import HfApi, hf_hub_download
api = HfApi(endpoint="https://huggingface.co")
i = api.repo_info(repo_id="physics-video-lab/physics-video-assets", repo_type="dataset")
print(f"private={i.private} sha={i.sha}")
p = hf_hub_download(repo_id="physics-video-lab/physics-video-assets",
                    filename="assets_manifest.json", repo_type="dataset", force_download=True)
d = json.load(open(p, encoding="utf-8"))
print(f"assets={len(d['assets'])} files={sum(len(a['files']) for a in d['assets'])}")
print("ids:", [a["id"] for a in d["assets"]])
PY

echo
echo "=== 6. clean the merged-manifest scratch file (contains no secrets, but tidy) ==="
rm -f "$WS/tmp/merged_manifest.json"
ls "$WS/tmp/hf_backup/" | sed 's/^/  backup kept: /'
