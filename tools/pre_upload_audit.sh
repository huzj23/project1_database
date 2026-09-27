#!/usr/bin/env bash
# ===========================================================================
# 1. FULL README diff (is our card purely additive, or does it drop mentor content?)
# 2. MTL/OBJ naming convention across ALL assets (is the elephant's broken
#    `mtllib visual_geometry.mtl` normal, or a defect?)
# 3. Which assets are actually going to be uploaded, and their stray files.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?}"; export HF_HUB_DISABLE_TELEMETRY=1

echo "=== 1. FULL README diff (remote -> our card) ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import difflib
from huggingface_hub import hf_hub_download
rem = hf_hub_download(repo_id="physics-video-lab/physics-video-assets",
                      filename="README.md", repo_type="dataset", force_download=True)
a = open(rem, encoding="utf-8").read().splitlines()
b = open("docs/HUGGINGFACE_DATASET_CARD.md", encoding="utf-8").read().splitlines()
d = list(difflib.unified_diff(a, b, "REMOTE", "OURS", lineterm="", n=1))
print(f"hunks/lines: {len(d)}")
removed = [l for l in d if l.startswith("-") and not l.startswith("---")]
added   = [l for l in d if l.startswith("+") and not l.startswith("+++")]
print(f"REMOVED lines ({len(removed)}):")
for l in removed: print("   ", l)
print(f"ADDED lines ({len(added)}):")
for l in added: print("   ", l)
PY

echo
echo "=== 2. mtllib naming across every asset's visual OBJ ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import glob, os, re
for obj in sorted(glob.glob("assets/*/*/visual/*.obj")):
    d = os.path.dirname(obj)
    txt = open(obj, errors="ignore").read(2000)
    m = re.search(r'^mtllib\s+(\S+)', txt, re.M)
    ref = m.group(1) if m else None
    present = sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, "*.mtl")))
    ok = "OK " if (ref and os.path.isfile(os.path.join(d, ref))) else ("n/a" if not ref else "BAD")
    print(f"  {ok} {obj}")
    print(f"        mtllib={ref!r}  mtl files present={present}")
PY

echo
echo "=== 3. stray/backup files anywhere in assets/ (would be published) ==="
find assets -type f \( -name '*.bak' -o -name '*bak*' -o -name '*.pre_*' -o -name '*.blend1' -o -name '*.nomtl-bak' -o -name '*.t3dev*' \) 2>/dev/null | sed 's/^/  /'
echo "  (none above = clean)"

echo
echo "=== 4. what our 3 assets would contribute, after strays are excluded ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util as u, sys
from pathlib import Path
spec = u.spec_from_file_location("syncmod", "scripts/sync_hf_assets.py")
m = u.module_from_spec(spec); sys.modules["syncmod"] = m; spec.loader.exec_module(m)
root = Path(".").resolve()
recs = {r.asset_id: r for r in m.discover_assets(root)}
for aid in ("special_plush_elephant", "replicad_apartment", "turntable"):
    r = recs.get(aid)
    if not r:
        print(f"  {aid}: NOT FOUND"); continue
    files = sorted(m._payload_files(r))
    stray = [f for f in files if ".bak" in f.name or ".pre_" in f.name]
    print(f"  {aid}: {len(files)} files, {sum(f.stat().st_size for f in files)/1e6:.2f} MB, strays={[f.name for f in stray]}")
PY
