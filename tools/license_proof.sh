#!/usr/bin/env bash
# ===========================================================================
# Demonstrate EXACTLY what the mentor's license allowlist does, by running his own
# sync_hf_assets.py in list/dry-run mode (which needs no Hub access).
#
# This answers "is our license scope bigger or smaller?" with evidence rather than
# opinion: show what the default gate does to our two assets, then what happens once
# their licenses are named explicitly.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== the gate as written (from the script itself) ==="
grep -n 'DEFAULT_ALLOWED_LICENSES\|forbidden_license_labels' scripts/sync_hf_assets.py | sed 's/^/  /'

echo
echo "=== (1) DEFAULT behaviour: ask to upload our elephant, no license flag ==="
"$PY" scripts/sync_hf_assets.py list --asset-id special_plush_elephant 2>&1 | sed 's/^/  /'

echo
echo "=== (2) DEFAULT behaviour: ask to upload our apartment, no license flag ==="
"$PY" scripts/sync_hf_assets.py list --asset-id replicad_apartment 2>&1 | sed 's/^/  /'

echo
echo "=== (3) elephant WITH its license named explicitly ==="
"$PY" scripts/sync_hf_assets.py list --asset-id special_plush_elephant \
  --allowed-license "CC BY-SA 4.0" 2>&1 | sed 's/^/  /'

echo
echo "=== (4) apartment WITH its license named explicitly ==="
"$PY" scripts/sync_hf_assets.py list --asset-id replicad_apartment \
  --allowed-license "CC BY-NC 4.0" 2>&1 | sed 's/^/  /'

echo
echo "=== (5) BOTH, with both licenses named ==="
"$PY" scripts/sync_hf_assets.py list --asset-id special_plush_elephant \
  --asset-id replicad_apartment --allowed-license "CC BY-SA 4.0" \
  --allowed-license "CC BY-NC 4.0" 2>&1 | sed 's/^/  /'

echo
echo "=== (6) proof that UNKNOWN can never be allowlisted ==="
"$PY" scripts/sync_hf_assets.py list --allowed-license "UNKNOWN" 2>&1 | head -4 | sed 's/^/  /'

echo
echo "=== (7) what the mentor's own assets list as (default gate) ==="
"$PY" scripts/sync_hf_assets.py list 2>&1 | head -20 | sed 's/^/  /'

echo
echo "=== license values recorded in every asset manifest ==="
"$PY" - <<'PY'
import glob, yaml
for p in sorted(glob.glob("assets/*/*/asset.yaml")):
    m = yaml.safe_load(open(p))
    if m.get("id") in ("special_plush_elephant", "replicad_apartment",
                       "turntable", "food_lime", "classroom"):
        print(f"  {m.get('id'):26s} kind={m.get('kind'):12s} license={m.get('license')}")
PY
